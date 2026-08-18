"""
Recording reconciliation service (Phase 2 — Fix #3).

Closes the recording pipeline's open loop: an appointment recording advances to
analysis_status='completed' only when Shunya's job-complete webhook arrives. If
the webhook is lost, Shunya fails, or the summary fetch fails, the appointment
sits in 'processing' forever. This service polls the Shunya job we already track
(appointment.shunya_job_id) on a schedule and drives the recording to a terminal
state, recovering completed analyses and failing genuinely-dead ones.

Two responsibilities:
  - apply_appointment_analysis(): the single shared persistence path used by BOTH
    the job-complete webhook and reconciliation (so a recovered 'completed' job is
    persisted identically to a webhook-delivered one).
  - reconcile_stuck_recordings(): poll + transition the stuck batch.

Reuses: existing APScheduler, AppointmentORM columns, Shunya client
(get_call_processing_status / get_call_summary). No new tables, bus, or Celery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.debug_runtime import emit_debug_log
from app.core.logging import get_logger
from app.domain.enums import PendingActionStatus
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.repositories.pending_action import PendingActionRepository

logger = get_logger(__name__)

UTC = timezone.utc

# Canonical analysis_status values (free strings in the DB).
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Reconciliation decision outcomes (what to do with a polled job).
ACTION_COMPLETE = "complete"      # Shunya done → persist analysis, mark completed
ACTION_FAIL = "fail"              # Shunya failed or timed out → mark failed
ACTION_WAIT = "wait"             # still running / transient error → leave processing

# ── Post-meeting action materialization ───────────────────────────────────
# Shunya summary.pending_actions[].type → PendingAction.action_type.
# Everything maps into the follow_up* family so materialized tasks surface in
# BOTH Action Center (whitelist: follow_up*) and Follow-up Guidance (family:
# follow_up*). The original AI type is preserved in extra_metadata.ai_action_type.
_AI_ACTION_TYPE_MAP = {
    "send_proposal": "follow_up",
    "schedule_appointment": "follow_up",
    "follow_up": "follow_up",
    "other": "follow_up",
}
# Shunya owner values that are NOT the sales rep → skip (not a rep task).
_NON_REP_OWNERS = {"customer", "client", "homeowner"}
_POST_MEETING_PRIORITY = 2
_POST_MEETING_SOURCE = "ai_analysis"


def map_ai_action_type(ai_type: Optional[str]) -> str:
    """Map a Shunya pending_action type into a surfaced PendingAction type."""
    return _AI_ACTION_TYPE_MAP.get((ai_type or "").strip().lower(), "follow_up")


def is_rep_owned_action(ai_owner: Optional[str]) -> bool:
    """True if the AI action is the rep's to do (skip customer-owned actions)."""
    return (ai_owner or "").strip().lower() not in _NON_REP_OWNERS


def parse_ai_due_at(raw_due, now: datetime) -> datetime:
    """Parse a Shunya due_at into UTC; default to now+24h when absent/unparseable."""
    default = now + timedelta(hours=24)
    if not raw_due:
        return default
    if isinstance(raw_due, datetime):
        return raw_due.replace(tzinfo=UTC) if raw_due.tzinfo is None else raw_due.astimezone(UTC)
    if isinstance(raw_due, str):
        try:
            dt = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        except (ValueError, TypeError):
            return default
    return default


def ai_action_dedup_key(appointment_id, raw_text: Optional[str]) -> str:
    """Stable key for one (appointment, action) — drives idempotency on replay."""
    import hashlib
    norm = (raw_text or "").strip().lower()
    return hashlib.sha1(f"{appointment_id}::{norm}".encode("utf-8")).hexdigest()


def extract_pending_actions(complete_summary_data: dict) -> list[dict]:
    """Pull the Shunya summary.pending_actions LIST (the actionable post-meeting items).

    Note: Shunya emits this as a list of dicts; tolerate a bare dict too.
    """
    summary_section = complete_summary_data.get("summary", {})
    if not isinstance(summary_section, dict):
        return []
    items = summary_section.get("pending_actions")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]


@dataclass
class ReconcileResult:
    """Outcome of a reconcile_stuck_recordings run."""
    scanned: int = 0
    completed: int = 0
    failed: int = 0
    waiting: int = 0
    errors: int = 0
    details: list[dict] = field(default_factory=list)


# ── Pure decision logic (unit-testable, no I/O) ───────────────────────────

def decide_reconcile_action(
    *,
    job_status: Optional[str],
    processing_since: Optional[datetime],
    now: datetime,
    poll_succeeded: bool,
) -> tuple[str, Optional[str]]:
    """Decide what to do with a stuck recording given a poll result.

    Returns (action, reason). `reason` is a human-readable failure reason when
    action == ACTION_FAIL, else None.

    Precedence:
      1. Poll failed (Shunya unreachable) → WAIT (retry next run), unless the hard
         processing ceiling has passed, in which case FAIL (timed out).
      2. Shunya 'completed' → COMPLETE.
      3. Shunya 'failed' → FAIL with Shunya's status.
      4. Shunya 'queued'/'running'/unknown → WAIT, unless past the ceiling → FAIL.
    """
    max_age = timedelta(hours=settings.RECORDING_MAX_PROCESSING_HOURS)
    timed_out = processing_since is not None and (now - _aware(processing_since)) > max_age

    if not poll_succeeded:
        if timed_out:
            return ACTION_FAIL, "Analysis timed out (exceeded max processing window; Shunya unreachable)."
        return ACTION_WAIT, None

    status = (job_status or "").strip().lower()
    if status == STATUS_COMPLETED:
        return ACTION_COMPLETE, None
    if status == STATUS_FAILED:
        return ACTION_FAIL, "Shunya reported the analysis job as failed."
    # queued / running / unknown
    if timed_out:
        return ACTION_FAIL, "Analysis timed out (exceeded max processing window)."
    return ACTION_WAIT, None


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


# ── Shared persistence path (webhook + reconciliation) ────────────────────

async def apply_appointment_analysis(
    session: AsyncSession,
    appointment: AppointmentORM,
    complete_summary_data: dict[str, Any],
    transcript: Optional[str] = None,
) -> bool:
    """Persist Shunya analysis onto an appointment and mark it completed.

    The single source of truth for appointment analysis persistence — called by
    the job-complete webhook AND by reconciliation when it recovers a completed
    job. Mutates the ORM appointment, creates a follow-up pending action if Shunya
    flagged one (idempotent), and flushes. Caller owns the commit.

    Returns True if a follow-up pending action was (or already) required.
    """
    summary_section = complete_summary_data.get("summary", {})
    qualification = complete_summary_data.get("qualification", {})
    compliance = complete_summary_data.get("compliance", {})
    objection_section = complete_summary_data.get("objections", {})

    if isinstance(summary_section, dict):
        appointment.summary = summary_section.get("summary")
        appointment.key_points = summary_section.get("key_points", [])
        appointment.action_items = summary_section.get("action_items", [])
        appointment.next_steps = summary_section.get("next_steps", [])
        # Shunya emits pending_actions as a LIST; persist it under a list-safe
        # shape so it is not silently dropped (the JSON column accepts either).
        pending_actions = summary_section.get("pending_actions")
        if isinstance(pending_actions, list):
            appointment.pending_actions_data = {"actions": pending_actions}
        elif isinstance(pending_actions, dict):
            appointment.pending_actions_data = pending_actions
        else:
            appointment.pending_actions_data = None
        appointment.sentiment_score = summary_section.get("sentiment_score")
        # #region agent log
        emit_debug_log(
            hypothesis_id="H8",
            location="recording_reconciliation_service.py:210",
            message="Applied appointment summary payload",
            data={
                "appointmentId": str(appointment.id),
                "hasSummary": bool(appointment.summary),
                "actionItemsCount": len(appointment.action_items or []),
                "nextStepsCount": len(appointment.next_steps or []),
                "hasPendingActionsData": bool(appointment.pending_actions_data),
            },
        )
        # #endregion

    if isinstance(objection_section, dict):
        raw_objections = objection_section.get("objections", [])
        appointment.objection_texts = [
            o.get("text", "") if isinstance(o, dict) else str(o) for o in raw_objections
        ]
        appointment.objections = [
            o.get("category_text", "") if isinstance(o, dict) else str(o) for o in raw_objections
        ]
        appointment.objections_total_count = objection_section.get("total_count", len(raw_objections))
    elif isinstance(objection_section, list):
        appointment.objections = [
            o.get("category_text", "") if isinstance(o, dict) else str(o) for o in objection_section
        ]
        appointment.objections_total_count = len(objection_section)

    if isinstance(compliance, dict):
        appointment.sop_stages_completed = compliance.get("stages_completed", [])
        appointment.sop_stages_missed = compliance.get("stages_missed", [])
        appointment.sop_stages_total = compliance.get("stages_total")
        appointment.sop_compliance_score = compliance.get("compliance_score")
        appointment.sop_compliance_rate = compliance.get("compliance_rate")
        appointment.sop_compliance_confidence = compliance.get("confidence")
        appointment.sop_compliance_issues = compliance.get("issues", [])
        appointment.sop_compliance_positive_behaviors = compliance.get("positive_behaviors", [])
        appointment.compliance_target_role = compliance.get("target_role")

    follow_up_required = False
    follow_up_reason = None
    if isinstance(qualification, dict):
        appointment.qualification_status = qualification.get("qualification_status")
        appointment.booking_status = qualification.get("booking_status")
        follow_up_required = qualification.get("follow_up_required", False)
        follow_up_reason = qualification.get("follow_up_reason")

    if transcript:
        appointment.transcript = transcript

    # Clear any prior failure marker now that analysis succeeded.
    meta = dict(appointment.extra_metadata or {})
    meta.pop("analysis_error", None)
    appointment.extra_metadata = meta or None

    appointment.analysis_status = STATUS_COMPLETED
    if hasattr(appointment, "mark_updated"):
        appointment.mark_updated()

    await session.flush()

    if follow_up_required:
        try:
            pending_repo = PendingActionRepository(session)
            already_exists = await pending_repo.exists_pending_appointment_follow_up(
                appointment.id, source=None
            )
            if already_exists:
                logger.info(
                    "Skipped duplicate appointment follow-up pending action",
                    appointment_id=str(appointment.id),
                )
            else:
                now_utc = datetime.now(UTC)
                session.add(PendingActionORM(
                    company_id=appointment.company_id,
                    lead_id=appointment.lead_id,
                    call_id=appointment.interaction_id,
                    appointment_id=appointment.id,
                    action_type="follow_up",
                    raw_text=follow_up_reason or "Follow up required based on appointment analysis",
                    status=PendingActionStatus.PENDING.value,
                    due_at=now_utc + timedelta(hours=24),
                    priority=2,
                    owner_id=appointment.assigned_rep_id,
                    source="ai_analysis",
                    extra_metadata={
                        "appointment_id": str(appointment.id),
                        "follow_up_reason": follow_up_reason,
                    },
                ))
                await session.flush()
                logger.info(
                    "Created follow-up pending action from appointment analysis",
                    appointment_id=str(appointment.id),
                )
        except Exception as pa_err:
            logger.warning(f"Failed to create follow-up pending action: {pa_err}")

    # Materialize Shunya's structured post-meeting actions into rep tasks so they
    # appear in Action Center + Follow-up Guidance (idempotent on replay).
    await materialize_post_meeting_actions(session, appointment, complete_summary_data)

    return follow_up_required


async def materialize_post_meeting_actions(
    session: AsyncSession,
    appointment: AppointmentORM,
    complete_summary_data: dict,
) -> int:
    """Turn Shunya's summary.pending_actions into actionable PendingAction rows.

    One rep-owned task per distinct action, owned by the appointment's assigned
    rep, mapped into the follow_up* family so it surfaces in Action Center and
    Follow-up Guidance. Idempotent via extra_metadata.ai_dedup_key — safe for
    webhook + reconciliation replay. Per-entry failures are non-fatal. Returns
    the count created.
    """
    actions = extract_pending_actions(complete_summary_data)
    if not actions:
        return 0

    repo = PendingActionRepository(session)
    now_utc = datetime.now(UTC)
    created = 0

    for item in actions:
        try:
            if not is_rep_owned_action(item.get("owner")):
                continue
            raw_text = (item.get("raw_text") or item.get("action") or "").strip()
            if not raw_text:
                continue

            dedup_key = ai_action_dedup_key(appointment.id, raw_text)
            if await repo.exists_appointment_ai_action(appointment.id, dedup_key):
                continue

            action_type = map_ai_action_type(item.get("type"))
            due_at = parse_ai_due_at(item.get("due_at"), now_utc)

            session.add(PendingActionORM(
                company_id=appointment.company_id,
                lead_id=appointment.lead_id,
                call_id=appointment.interaction_id,
                appointment_id=appointment.id,
                action_type=action_type,
                raw_text=raw_text,
                status=PendingActionStatus.PENDING.value,
                due_at=due_at,
                priority=_POST_MEETING_PRIORITY,
                owner_id=appointment.assigned_rep_id,
                source=_POST_MEETING_SOURCE,
                extra_metadata={
                    "appointment_id": str(appointment.id),
                    "ai_dedup_key": dedup_key,
                    "ai_action_type": item.get("type"),
                    "contact_method": item.get("contact_method"),
                    "confidence": item.get("confidence"),
                    "materialized_from": "post_meeting_analysis",
                },
            ))
            await session.flush()
            created += 1
        except Exception as item_err:
            logger.warning(
                "Failed to materialize a post-meeting action",
                appointment_id=str(appointment.id),
                error=str(item_err),
            )

    if created:
        logger.info(
            "Materialized post-meeting actions",
            appointment_id=str(appointment.id),
            created=created,
        )
    return created


async def _mark_failed(
    session: AsyncSession, appointment: AppointmentORM, reason: str
) -> None:
    """Mark an appointment's analysis failed and stash the reason for surfacing."""
    appointment.analysis_status = STATUS_FAILED
    meta = dict(appointment.extra_metadata or {})
    meta["analysis_error"] = reason
    appointment.extra_metadata = meta
    if hasattr(appointment, "mark_updated"):
        appointment.mark_updated()
    await session.flush()


def _bump_attempts(appointment: AppointmentORM) -> int:
    meta = dict(appointment.extra_metadata or {})
    attempts = int(meta.get("reconcile_attempts", 0)) + 1
    meta["reconcile_attempts"] = attempts
    meta["last_reconcile_at"] = datetime.now(UTC).isoformat()
    appointment.extra_metadata = meta
    return attempts


# ── Orchestrator ──────────────────────────────────────────────────────────

async def reconcile_stuck_recordings(
    session: AsyncSession,
    *,
    shoonya_client=None,
    now: Optional[datetime] = None,
) -> ReconcileResult:
    """Poll and transition recordings stuck in 'processing'.

    Selects appointments in analysis_status='processing' with a shunya_job_id that
    have been stuck longer than RECORDING_STUCK_THRESHOLD_MINUTES, polls Shunya for
    each, and drives them to completed/failed/wait. Caller owns the commit.

    shoonya_client is injectable for testing; defaults to the real client.
    """
    result = ReconcileResult()
    now = _aware(now) if now else datetime.now(UTC)

    if shoonya_client is None:
        from app.infrastructure.integrations.shoonya import get_shoonya_client
        shoonya_client = get_shoonya_client()

    stuck_before = now - timedelta(minutes=settings.RECORDING_STUCK_THRESHOLD_MINUTES)

    query = (
        select(AppointmentORM)
        .where(
            and_(
                AppointmentORM.analysis_status == STATUS_PROCESSING,
                AppointmentORM.shunya_job_id.isnot(None),
                or_(
                    AppointmentORM.updated_at.is_(None),
                    AppointmentORM.updated_at < stuck_before,
                ),
            )
        )
        .order_by(AppointmentORM.updated_at.asc().nulls_first())
        .limit(settings.RECORDING_RECONCILE_BATCH_LIMIT)
    )
    rows = (await session.execute(query)).scalars().all()
    result.scanned = len(rows)

    for appt in rows:
        try:
            processing_since = appt.updated_at or appt.created_at
            job_status = None
            summary_data = None
            poll_succeeded = True

            try:
                status_resp = await shoonya_client.get_call_processing_status(
                    appt.shunya_job_id, str(appt.company_id)
                )
                job_status = (status_resp or {}).get("status")
            except Exception as poll_err:
                poll_succeeded = False
                logger.warning(
                    "Reconcile poll failed",
                    appointment_id=str(appt.id),
                    job_id=appt.shunya_job_id,
                    error=str(poll_err),
                )

            action, reason = decide_reconcile_action(
                job_status=job_status,
                processing_since=processing_since,
                now=now,
                poll_succeeded=poll_succeeded,
            )
            # #region agent log
            emit_debug_log(
                hypothesis_id="H9",
                location="recording_reconciliation_service.py:480",
                message="Stuck recording reconcile decision",
                data={
                    "appointmentId": str(appt.id),
                    "jobStatus": job_status,
                    "pollSucceeded": poll_succeeded,
                    "decision": action,
                    "reason": reason,
                },
            )
            # #endregion

            _bump_attempts(appt)

            if action == ACTION_COMPLETE:
                # Fetch the full summary, then persist via the shared path.
                summary_data = await shoonya_client.get_call_summary(
                    str(appt.id), str(appt.company_id), include_chunks=False
                )
                transcript = (summary_data or {}).get("transcript")
                await apply_appointment_analysis(session, appt, summary_data or {}, transcript)
                result.completed += 1
                result.details.append({"appointment_id": str(appt.id), "action": "completed"})

            elif action == ACTION_FAIL:
                await _mark_failed(session, appt, reason or "Analysis failed.")
                result.failed += 1
                result.details.append({"appointment_id": str(appt.id), "action": "failed", "reason": reason})

            else:  # ACTION_WAIT
                await session.flush()  # persist the attempt bump
                result.waiting += 1
                result.details.append({"appointment_id": str(appt.id), "action": "wait"})

        except Exception as e:
            result.errors += 1
            logger.error(
                "Failed to reconcile stuck recording",
                appointment_id=str(appt.id),
                error=str(e),
            )

    logger.info(
        "Stuck-recording reconciliation complete",
        scanned=result.scanned,
        completed=result.completed,
        failed=result.failed,
        waiting=result.waiting,
        errors=result.errors,
    )
    return result
