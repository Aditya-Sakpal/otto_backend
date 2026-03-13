"""
Background scheduler for periodic tasks.

Uses APScheduler to run periodic jobs:
- Follow-up notification checks (every 1 minute)
- Coaching cycle management (daily at 1:00 AM UTC)
- Smart nudge evaluation (daily at 2:00 AM UTC)
- Nudge cleanup (daily at 4:00 AM UTC)
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

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


async def _coaching_cycle_manager_job():
    """
    Daily job (1:00 AM UTC): Auto-complete expired 7-day coaching cycles
    and create next cycles with updated baselines.
    """
    logger.debug("Running coaching cycle manager job")

    try:
        from app.services.coaching_cycle_service import CoachingCycleService

        async with AsyncSessionLocal() as session:
            service = CoachingCycleService(session)
            processed = await service.process_expired_cycles()
            if processed > 0:
                logger.info(
                    "Coaching cycle manager completed",
                    cycles_processed=processed,
                )
    except Exception as e:
        logger.error("Coaching cycle manager job failed", error=str(e))


async def _daily_nudge_evaluation_job():
    """
    Daily job (2:00 AM UTC): Evaluate all reps with active coaching sessions
    and generate smart nudges for managers.
    """
    logger.debug("Running daily nudge evaluation job")

    try:
        from app.services.smart_nudge_service import SmartNudgeService

        async with AsyncSessionLocal() as session:
            service = SmartNudgeService(session)
            total = await service.evaluate_all_companies()
            logger.info(
                "Daily nudge evaluation completed",
                nudges_generated=total,
            )
    except Exception as e:
        logger.error("Daily nudge evaluation job failed", error=str(e))


async def _nudge_cleanup_job():
    """
    Daily job (4:00 AM UTC): Delete expired nudges and their read records.
    """
    logger.debug("Running nudge cleanup job")

    try:
        from app.services.smart_nudge_service import SmartNudgeService

        async with AsyncSessionLocal() as session:
            service = SmartNudgeService(session)
            deleted = await service.cleanup_expired()
            if deleted > 0:
                logger.info(
                    "Nudge cleanup completed",
                    nudges_deleted=deleted,
                )
    except Exception as e:
        logger.error("Nudge cleanup job failed", error=str(e))


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

    # ── Existing: Follow-up check (every 1 minute) ──
    scheduler.add_job(
        _check_followups_job,
        trigger=IntervalTrigger(minutes=1),
        id="check_followups",
        name="Check pending follow-up calls",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Coaching cycle manager (daily at 1:00 AM UTC) ──
    # Completes expired 7-day cycles, creates next cycles, generates cycle-end nudges
    scheduler.add_job(
        _coaching_cycle_manager_job,
        trigger=CronTrigger(hour=1, minute=0),
        id="coaching_cycle_manager",
        name="Auto-complete and restart 7-day coaching cycles",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Daily nudge evaluation (daily at 2:00 AM UTC) ──
    # Evaluates all active reps, generates intra-cycle nudges
    scheduler.add_job(
        _daily_nudge_evaluation_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_nudge_evaluation",
        name="Evaluate rep performance and generate smart nudges",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Nudge cleanup (daily at 4:00 AM UTC) ──
    # Deletes expired nudges and their read records
    scheduler.add_job(
        _nudge_cleanup_job,
        trigger=CronTrigger(hour=4, minute=0),
        id="nudge_cleanup",
        name="Clean up expired nudges",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Background scheduler started with 4 jobs")

    return scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Background scheduler stopped")
