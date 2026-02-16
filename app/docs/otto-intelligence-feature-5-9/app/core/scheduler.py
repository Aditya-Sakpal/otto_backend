"""
Background Scheduler for Otto Intelligence Service

Uses APScheduler for scheduled background tasks without Celery.
Handles weekly insights generation and other periodic tasks.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import get_settings
from ..tasks.insight_tasks import generate_weekly_insights_background
from ..tasks.coaching_tasks import check_coaching_follow_ups, calculate_weekly_coach_effectiveness

settings = get_settings()
logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get the scheduler instance, creating it if necessary."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine multiple pending runs into one
                "max_instances": 1,  # Only one instance of each job at a time
                "misfire_grace_time": 3600,  # Allow jobs to run up to 1 hour late
            }
        )
    return _scheduler


async def trigger_weekly_insights_job():
    """
    Scheduled job to trigger weekly insights generation.
    Runs every Sunday at 00:00 UTC.
    """
    logger.info("Triggering scheduled weekly insights generation")
    
    try:
        # Calculate last week's date range
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday() + 7)  # Last Monday
        week_end = week_start + timedelta(days=6)  # Last Sunday
        
        # Generate job ID as pure UUID
        job_id = str(uuid.uuid4())
        
        # Prepare request data
        request_data = {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "company_ids": [],  # All companies
            "options": {
                "insight_types": ["company", "customer", "objection"],
                "force_regenerate": False
            }
        }
        
        logger.info(f"Starting scheduled insight generation job: {job_id}")
        logger.info(f"Week range: {week_start} to {week_end}")
        
        # Run the insight generation task
        result = await generate_weekly_insights_background(job_id, request_data)
        
        logger.info(f"Scheduled insight generation completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Scheduled insight generation failed: {str(e)}", exc_info=True)
        raise


def setup_scheduled_jobs(scheduler: AsyncIOScheduler):
    """Configure all scheduled jobs."""
    
    # Weekly insights generation - Every Sunday at 00:00 UTC
    scheduler.add_job(
        trigger_weekly_insights_job,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=0,
            minute=0,
            timezone="UTC"
        ),
        id="weekly_insights_generation",
        name="Weekly Insights Generation",
        replace_existing=True
    )
    logger.info("Scheduled job registered: Weekly Insights Generation (Sundays 00:00 UTC)")
    
    # Daily coaching follow-up check - Every day at 01:00 UTC
    # Per Q20: Automatic impact measurement on follow-up end
    scheduler.add_job(
        check_coaching_follow_ups,
        trigger=CronTrigger(
            hour=1,
            minute=0,
            timezone="UTC"
        ),
        id="daily_coaching_follow_up",
        name="Daily Coaching Follow-up Check",
        replace_existing=True
    )
    logger.info("Scheduled job registered: Daily Coaching Follow-up Check (Daily 01:00 UTC)")
    
    # Weekly coach effectiveness calculation - Every Monday at 02:00 UTC
    scheduler.add_job(
        calculate_weekly_coach_effectiveness,
        trigger=CronTrigger(
            day_of_week="mon",
            hour=2,
            minute=0,
            timezone="UTC"
        ),
        id="weekly_coach_effectiveness",
        name="Weekly Coach Effectiveness Calculation",
        replace_existing=True
    )
    logger.info("Scheduled job registered: Weekly Coach Effectiveness (Mondays 02:00 UTC)")


async def start_scheduler():
    """Start the background scheduler."""
    scheduler = get_scheduler()
    
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return scheduler
    
    # Setup all scheduled jobs
    setup_scheduled_jobs(scheduler)
    
    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started successfully")
    
    # Log all registered jobs
    jobs = scheduler.get_jobs()
    logger.info(f"Registered {len(jobs)} scheduled job(s):")
    for job in jobs:
        logger.info(f"  - {job.name} (ID: {job.id}, Next run: {job.next_run_time})")
    
    return scheduler


async def stop_scheduler():
    """Stop the background scheduler gracefully."""
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Background scheduler stopped")
    
    _scheduler = None


async def trigger_insights_now():
    """
    Manually trigger insight generation (for testing or on-demand runs).
    Returns the job ID that was started.
    """
    logger.info("Manual trigger of weekly insights generation")
    
    # Run in background without blocking - Generate job ID as pure UUID
    job_id = str(uuid.uuid4())
    
    # Calculate current week's date range
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())  # This Monday
    week_end = week_start + timedelta(days=6)  # This Sunday
    
    request_data = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "company_ids": [],
        "options": {
            "insight_types": ["company", "customer", "objection"],
            "force_regenerate": True
        }
    }
    
    # Create task to run in background
    asyncio.create_task(generate_weekly_insights_background(job_id, request_data))
    
    return job_id


def get_scheduler_status():
    """Get the current status of the scheduler and its jobs."""
    scheduler = get_scheduler()
    
    jobs_info = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
    
    return {
        "running": scheduler.running,
        "jobs_count": len(jobs_info),
        "jobs": jobs_info
    }


async def trigger_coaching_check_now():
    """
    Manually trigger coaching follow-up check (for testing).
    Returns status of the check.
    """
    logger.info("Manual trigger of coaching follow-up check")
    
    try:
        await check_coaching_follow_ups()
        return {"status": "completed", "message": "Coaching follow-up check completed"}
    except Exception as e:
        logger.error(f"Manual coaching check failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
