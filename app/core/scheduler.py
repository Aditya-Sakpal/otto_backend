"""
Background scheduler for periodic tasks.

Uses APScheduler to run periodic jobs like checking for follow-up notifications.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.followup_notification_service import check_follow_ups

logger = get_logger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


async def _check_followups_job():
    """
    Scheduled job to check for pending follow-ups.
    
    Creates a database session and runs the follow-up check.
    """
    logger.debug("Running follow-up check job")
    
    try:
        async with AsyncSessionLocal() as session:
            notifications_sent = await check_follow_ups(session)
            if notifications_sent > 0:
                logger.info(
                    "Follow-up check completed",
                    notifications_sent=notifications_sent
                )
    except Exception as e:
        logger.error("Follow-up check job failed", error=str(e))


def start_scheduler() -> AsyncIOScheduler:
    """
    Start the background scheduler.
    
    Initializes APScheduler and adds periodic jobs.
    
    Returns:
        The scheduler instance
    """
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already running")
        return scheduler
    
    scheduler = AsyncIOScheduler()
    
    # Add follow-up check job - runs every 1 minute
    scheduler.add_job(
        _check_followups_job,
        trigger=IntervalTrigger(minutes=1),
        id="check_followups",
        name="Check pending follow-up calls",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )
    
    scheduler.start()
    logger.info("Background scheduler started")
    
    return scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Background scheduler stopped")
