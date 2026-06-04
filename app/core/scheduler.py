"""
Background scheduler for periodic tasks.

Uses APScheduler to run periodic jobs:
- Follow-up notification checks (every 1 minute)
- Coaching cycle management (daily at 1:00 AM UTC)
- Smart nudge evaluation (daily at 2:00 AM UTC)
- Appointment reminder reconciliation (daily at 3:00 AM UTC)
- Nudge cleanup (daily at 4:00 AM UTC)
- Rehash opportunity reconciliation (daily at 5:00 AM UTC)
- Contextual follow-up drafting, propose-only (daily at 6:00 AM UTC)
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.debug_runtime import emit_debug_log
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
    # #region agent log
    emit_debug_log(
        hypothesis_id="H13",
        location="scheduler.py:35",
        message="Follow-up scheduler job started",
        data={},
    )
    # #endregion

    try:
        async with AsyncSessionLocal() as session:
            notifications_sent = await check_follow_ups(session)
            # #region agent log
            emit_debug_log(
                hypothesis_id="H3",
                location="scheduler.py:39",
                message="Follow-up scheduler job executed",
                data={"notificationsSent": notifications_sent},
            )
            # #endregion
            # Persist appointment-reminder notified_at/status writes (the standalone
            # session context does not auto-commit).
            await session.commit()
            if notifications_sent > 0:
                logger.info(
                    "Follow-up check completed",
                    notifications_sent=notifications_sent
                )
    except Exception as e:
        # #region agent log
        emit_debug_log(
            hypothesis_id="H13",
            location="scheduler.py:54",
            message="Follow-up scheduler job failed",
            data={"error": str(e)},
        )
        # #endregion
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


async def _reconcile_appointment_reminders_job():
    """
    Daily job (3:00 AM UTC): backfill/repair appointment reminder rows.

    Scans pending appointments in the next 14 days and re-syncs reminders for any
    that are missing expected rows. Catches GHL/cron misses, app restarts during a
    write, and pre-existing appointments created before this feature shipped.
    """
    logger.debug("Running appointment reminder reconciliation job")

    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select, or_

        from app.infrastructure.database.models.appointment import AppointmentORM
        from app.services.appointment_reminder_service import sync_appointment_reminders

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=14)

        async with AsyncSessionLocal() as session:
            query = (
                select(AppointmentORM)
                .where(AppointmentORM.scheduled_start > now)
                .where(AppointmentORM.scheduled_start <= horizon)
                .where(
                    or_(
                        AppointmentORM.outcome.is_(None),
                        AppointmentORM.outcome == "pending",
                    )
                )
            )
            result = await session.execute(query)
            appointments = result.scalars().all()
            # #region agent log
            emit_debug_log(
                hypothesis_id="H4",
                location="scheduler.py:151",
                message="Appointment reminder reconciliation candidate scan",
                data={
                    "appointmentsScanned": len(appointments),
                    "utcNow": now.isoformat(),
                    "horizon": horizon.isoformat(),
                },
            )
            # #endregion

            synced = 0
            for appt in appointments:
                try:
                    await sync_appointment_reminders(session, appt)
                    synced += 1
                except Exception as e:
                    logger.error(
                        "Failed to reconcile appointment reminders",
                        appointment_id=str(appt.id),
                        error=str(e),
                    )
            await session.commit()

            logger.info(
                "Appointment reminder reconciliation completed",
                appointments_scanned=len(appointments),
                appointments_synced=synced,
            )
    except Exception as e:
        logger.error("Appointment reminder reconciliation job failed", error=str(e))


async def _reconcile_rehash_job():
    """
    Daily job (5:00 AM UTC): scan for missed-revenue opportunities and
    materialize/reconcile them as `rehash` pending_actions.
    """
    logger.debug("Running rehash reconciliation job")

    try:
        from app.services.rehash_service import scan_and_sync_rehash

        async with AsyncSessionLocal() as session:
            result = await scan_and_sync_rehash(session)
            await session.commit()
            logger.info(
                "Rehash reconciliation completed",
                scanned=result.scanned,
                created=result.created,
                cancelled=result.cancelled,
                skipped=result.skipped,
            )
    except Exception as e:
        logger.error("Rehash reconciliation job failed", error=str(e))


async def _contextual_follow_up_job():
    """
    Daily job (6:00 AM UTC): run the contextual follow-up agent in PROPOSE-ONLY mode.

    Scans the gone-quiet (qualified_unbooked) and appointment-ran queues, drafts
    SMS-to-lead messages + rep nudges with Claude, and writes FollowUpOttoORM rows
    as status='proposed' for manual review — never auto-sends. The agent self-dedupes
    via cadence + opt-out/reply/intervention gating, so a daily run is safe.

    Graceful no-op when disabled (CONTEXTUAL_FOLLOWUP_ENABLED=False) or when the
    drafting model key (ANTHROPIC_API_KEY) is not configured.
    """
    logger.debug("Running contextual follow-up agent job")

    if not settings.CONTEXTUAL_FOLLOWUP_ENABLED:
        logger.info("Contextual follow-up agent skipped — disabled by setting")
        return

    # The agent package lives under app/agents; make it importable the same way
    # the approve-and-send route does (app/routes/v1/follow_up.py).
    import sys
    from pathlib import Path

    agents_root = str(Path(__file__).resolve().parents[1] / "agents")
    if agents_root not in sys.path:
        sys.path.insert(0, agents_root)

    try:
        from contextual_follow_up_agent.config.settings import settings as fu_settings
        from contextual_follow_up_agent.db.local import init_local_db, get_local_session
        from contextual_follow_up_agent.orchestrator import run as run_follow_up_agent

        # Graceful no-op without a drafting model key.
        if not fu_settings.ANTHROPIC_API_KEY:
            logger.info("Contextual follow-up agent skipped — ANTHROPIC_API_KEY not set")
            return

        # Force PROPOSE-ONLY for the scheduled batch regardless of .env: process_lead
        # always writes status='proposed' first, and a send is gated on
        # (AUTO_EXECUTE and not DRY_RUN), so these two guarantee no auto-send.
        fu_settings.DRY_RUN = True
        fu_settings.AUTO_EXECUTE = False

        await init_local_db()
        local_session = await get_local_session()

        async with AsyncSessionLocal() as pg_session, local_session:
            stats = await run_follow_up_agent(
                pg_session=pg_session,
                local_session=local_session,
                lead_id_filter=None,
            )
            await pg_session.commit()

        logger.info("Contextual follow-up agent completed", **(stats or {}))
    except Exception as e:
        logger.error("Contextual follow-up agent job failed", error=str(e))


async def _reconcile_stuck_recordings_job():
    """
    Recurring job: recover recordings stuck in analysis_status='processing'.

    Polls the Shunya job we already track (appointment.shunya_job_id) for
    recordings that have been processing longer than the stuck threshold, and
    drives them to completed (re-persisting recovered analysis) or failed. Runs
    on a short interval because recording recovery is user-facing.
    """
    logger.debug("Running stuck-recording reconciliation job")

    try:
        from app.services.recording_reconciliation_service import reconcile_stuck_recordings

        async with AsyncSessionLocal() as session:
            result = await reconcile_stuck_recordings(session)
            await session.commit()
            if result.completed or result.failed or result.scanned:
                logger.info(
                    "Stuck-recording reconciliation completed",
                    scanned=result.scanned,
                    completed=result.completed,
                    failed=result.failed,
                    waiting=result.waiting,
                    errors=result.errors,
                )
    except Exception as e:
        logger.error("Stuck-recording reconciliation job failed", error=str(e))


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

    # ── NEW: Appointment reminder reconciliation (daily at 3:00 AM UTC) ──
    # Backfills/repairs reminder rows for upcoming pending appointments
    scheduler.add_job(
        _reconcile_appointment_reminders_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="reconcile_appointment_reminders",
        name="Reconcile appointment reminder pending actions",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Rehash reconciliation (daily at 5:00 AM UTC) ──
    # Materializes missed-revenue opportunities as `rehash` pending actions
    scheduler.add_job(
        _reconcile_rehash_job,
        trigger=CronTrigger(hour=5, minute=0),
        id="reconcile_rehash",
        name="Reconcile rehash opportunity pending actions",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Contextual follow-up agent (daily at 6:00 AM UTC) ──
    # Proactively drafts SMS-to-lead + rep nudges as 'proposed' for manual review
    scheduler.add_job(
        _contextual_follow_up_job,
        trigger=CronTrigger(hour=6, minute=0),
        id="contextual_follow_up",
        name="Draft proactive contextual follow-ups (propose-only)",
        replace_existing=True,
        max_instances=1,
    )

    # ── NEW: Stuck-recording reconciliation (every N minutes) ──
    # Recovers recordings stuck in 'processing' (lost webhook / Shunya failure)
    scheduler.add_job(
        _reconcile_stuck_recordings_job,
        trigger=IntervalTrigger(minutes=settings.RECORDING_RECONCILE_INTERVAL_MINUTES),
        id="reconcile_stuck_recordings",
        name="Recover stuck recording analysis jobs",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Background scheduler started with 8 jobs")

    return scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Background scheduler stopped")
