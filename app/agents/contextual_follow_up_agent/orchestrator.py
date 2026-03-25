"""
Orchestrator — main pipeline loop.

scan → assemble → gates → timing → cadence → action routing → generate → execute
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.cadence.scheduler import (
    ScheduleResult,
    compute_next_follow_up,
)
from contextual_follow_up_agent.config.company_config import CompanyConfigStore
from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.context.assembler import assemble_context
from contextual_follow_up_agent.executor.opt_out_handler import is_opted_out
from contextual_follow_up_agent.executor.pending_action import create_rep_nudge
from contextual_follow_up_agent.executor.rep_notifier import notify_rep_of_reply
from contextual_follow_up_agent.executor.twilio_sms import TwilioSMSSender
from contextual_follow_up_agent.intelligence.messages import (
    format_nudge_as_text,
    generate_rep_nudge,
    generate_sms,
)
from contextual_follow_up_agent.intelligence.rep_activity_detector import (
    check_rep_manual_contact,
)
from contextual_follow_up_agent.intelligence.reply_detector import (
    check_for_homeowner_reply,
)
from contextual_follow_up_agent.intelligence.timing import extract_timing
from contextual_follow_up_agent.models.context import AssembledContext
from contextual_follow_up_agent.models.enums import (
    ActionType,
    FollowUpStatus,
    PausedReason,
    QueueType,
)
from contextual_follow_up_agent.models.output import FollowUpAction
from contextual_follow_up_agent.scanners.appointment_ran import scan_appointment_ran
from contextual_follow_up_agent.scanners.qualified_unbooked import scan_qualified_unbooked

logger = get_logger(__name__)

# ── Queue 2 Action Type Thresholds ─────────────────────────────────────
# Named constants for determine_action_types() decision logic.
RECENT_APPOINTMENT_DAYS = 3       # days_since <= this → nudge only
POSITIVE_SENTIMENT_THRESHOLD = 0.5  # sentiment >= this → nudge only
MULTI_ATTEMPT_THRESHOLD = 2       # attempt >= this AND no response → both


def determine_action_types(ctx: AssembledContext) -> list[ActionType]:
    """
    Decide which action types to generate for a Queue 2 lead.

    Queue 1 always returns [SMS_TO_LEAD].
    Queue 2 uses threshold-based logic per user specification.
    """
    if ctx.queue_type == QueueType.QUALIFIED_UNBOOKED.value:
        return [ActionType.SMS_TO_LEAD]

    # Queue 2: Appointment Ran
    days_since = ctx.days_since_event
    sentiment = (
        ctx.analysis.sentiment_score
        if ctx.analysis and ctx.analysis.sentiment_score is not None
        else None
    )
    has_response = ctx.history.has_response
    has_assigned_rep = ctx.lead.assigned_rep_id is not None

    # No assigned rep → SMS only (no one to nudge)
    if not has_assigned_rep:
        return [ActionType.SMS_TO_LEAD]

    # Recent appointment → rep nudge only (give rep time to close naturally)
    if days_since <= RECENT_APPOINTMENT_DAYS:
        return [ActionType.NUDGE_SALES_REP]

    # Multiple attempts with no response → both channels
    if ctx.attempt_number >= MULTI_ATTEMPT_THRESHOLD and not has_response:
        return [ActionType.SMS_TO_LEAD, ActionType.NUDGE_SALES_REP]

    # Older appointment with positive/neutral sentiment → rep nudge only
    if sentiment is not None and sentiment >= POSITIVE_SENTIMENT_THRESHOLD:
        return [ActionType.NUDGE_SALES_REP]

    # Older appointment with negative sentiment → SMS only
    if sentiment is not None and sentiment < POSITIVE_SENTIMENT_THRESHOLD:
        return [ActionType.SMS_TO_LEAD]

    # Default (no sentiment data) → rep nudge only
    return [ActionType.NUDGE_SALES_REP]


async def _log_follow_up(
    local_session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    company_id: uuid.UUID,
    queue_type: str,
    attempt_number: int,
    action_type: str,
    scheduled_at: datetime,
    channel: str,
    message_content: str,
    cadence_override: bool,
    override_reason: str | None,
    status: str,
    shunya_context_used: bool,
    pending_action_id: str | None = None,
    error_message: str | None = None,
    paused_reason: str | None = None,
    paused_at: str | None = None,
) -> str:
    """Write a row to the local follow_up_log."""
    log_id = str(uuid.uuid4())
    await local_session.execute(
        text("""
            INSERT INTO follow_up_log (
                id, lead_id, company_id, queue_type, attempt_number,
                action_type, scheduled_at, sent_at, channel, message_content,
                cadence_override, override_reason, status,
                shunya_context_used, pending_action_id, error_message,
                paused_reason, paused_at
            ) VALUES (
                :id, :lead_id, :company_id, :queue_type, :attempt_number,
                :action_type, :scheduled_at, :sent_at, :channel, :message_content,
                :cadence_override, :override_reason, :status,
                :shunya_context_used, :pending_action_id, :error_message,
                :paused_reason, :paused_at
            )
        """),
        {
            "id": log_id,
            "lead_id": str(lead_id),
            "company_id": str(company_id),
            "queue_type": queue_type,
            "attempt_number": attempt_number,
            "action_type": action_type,
            "scheduled_at": scheduled_at.isoformat(),
            "sent_at": datetime.now(timezone.utc).isoformat() if status == FollowUpStatus.SENT.value else None,
            "channel": channel,
            "message_content": message_content,
            "cadence_override": 1 if cadence_override else 0,
            "override_reason": override_reason,
            "status": status,
            "shunya_context_used": 1 if shunya_context_used else 0,
            "pending_action_id": pending_action_id,
            "error_message": error_message,
            "paused_reason": paused_reason,
            "paused_at": paused_at,
        },
    )
    await local_session.commit()
    return log_id


async def _update_log_status(
    local_session: AsyncSession,
    log_id: str,
    status: str,
    *,
    sent_at: datetime | None = None,
    pending_action_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update a follow_up_log row after execution."""
    await local_session.execute(
        text("""
            UPDATE follow_up_log
            SET status = :status,
                sent_at = :sent_at,
                pending_action_id = :pending_action_id,
                error_message = :error_message,
                updated_at = :updated_at
            WHERE id = :id
        """),
        {
            "id": log_id,
            "status": status,
            "sent_at": sent_at.isoformat() if sent_at else None,
            "pending_action_id": pending_action_id,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await local_session.commit()


async def _insert_follow_up_otto(
    pg_session: AsyncSession,
    *,
    id: str,
    lead_id: uuid.UUID,
    company_id: uuid.UUID,
    message_content: str,
    action_type: str,
    scheduled_at: datetime,
    status: str,
    queue_type: str,
    attempt_number: int,
    sent_at: datetime | None = None,
    error_message: str | None = None,
    assigned_rep_id: uuid.UUID | None = None,
    pending_action_id: str | None = None,
    opening_line: str | None = None,
    objections: list[dict] | None = None,
    key_talking_points: list[str] | None = None,
    close_approach: str | None = None,
) -> None:
    """Insert a row into follow_up_otto (Postgres) for the Follow Up tab."""
    try:
        objections_json = json.dumps(objections) if objections is not None else None
        key_talking_points_json = (
            json.dumps(key_talking_points) if key_talking_points is not None else None
        )

        logger.info(
            "Inserting follow_up_otto row",
            id=id,
            lead_id=str(lead_id),
            company_id=str(company_id),
            action_type=action_type,
            status=status,
            queue_type=queue_type,
            attempt_number=attempt_number,
        )
        await pg_session.execute(
            text("""
                INSERT INTO follow_up_otto (
                    id, lead_id, company_id, message_content, action_type,
                    scheduled_at, sent_at, status, error_message,
                    queue_type, attempt_number, assigned_rep_id, pending_action_id,
                    opening_line, objections, key_talking_points, close_approach
                ) VALUES (
                    :id, :lead_id, :company_id, :message_content, :action_type,
                    :scheduled_at, :sent_at, :status, :error_message,
                    :queue_type, :attempt_number, :assigned_rep_id, :pending_action_id,
                    :opening_line,
                    CAST(:objections AS jsonb),
                    CAST(:key_talking_points AS jsonb),
                    :close_approach
                )
            """),
            {
                "id": id,
                "lead_id": str(lead_id),
                "company_id": str(company_id),
                "message_content": message_content,
                "action_type": action_type,
                "scheduled_at": scheduled_at,
                "sent_at": sent_at,
                "status": status,
                "error_message": error_message,
                "queue_type": queue_type,
                "attempt_number": attempt_number,
                "assigned_rep_id": str(assigned_rep_id) if assigned_rep_id else None,
                "pending_action_id": pending_action_id,
                "opening_line": opening_line,
                "objections": objections_json,
                "key_talking_points": key_talking_points_json,
                "close_approach": close_approach,
            },
        )
        await pg_session.commit()
        logger.info(
            "Inserted follow_up_otto row",
            id=id,
            lead_id=str(lead_id),
            status=status,
        )
    except Exception as e:
        logger.warning("Failed to insert follow_up_otto row", id=id, error=str(e))


async def _update_follow_up_otto(
    pg_session: AsyncSession,
    log_id: str,
    *,
    status: str | None = None,
    sent_at: datetime | None = None,
    pending_action_id: str | None = None,
    error_message: str | None = None,
    external_message_id: str | None = None,
) -> None:
    """Update a follow_up_otto row after send/failure."""
    try:
        updates = ["updated_at = :updated_at"]
        params = {"id": log_id, "updated_at": datetime.now(timezone.utc)}
        if status is not None:
            updates.append("status = :status")
            params["status"] = status
        if sent_at is not None:
            updates.append("sent_at = :sent_at")
            params["sent_at"] = sent_at
        if pending_action_id is not None:
            updates.append("pending_action_id = :pending_action_id")
            params["pending_action_id"] = pending_action_id
        if error_message is not None:
            updates.append("error_message = :error_message")
            params["error_message"] = error_message
        if external_message_id is not None:
            updates.append("external_message_id = :external_message_id")
            params["external_message_id"] = external_message_id
        logger.info(
            "Updating follow_up_otto row",
            id=log_id,
            status=status,
            sent_at=sent_at.isoformat() if sent_at else None,
            pending_action_id=pending_action_id,
            has_error=error_message is not None,
            has_external_id=external_message_id is not None,
        )
        await pg_session.execute(
            text(
                f"UPDATE follow_up_otto SET {', '.join(updates)} WHERE id = :id"
            ),
            params,
        )
        await pg_session.commit()
        logger.info("Updated follow_up_otto row", id=log_id)
    except Exception as e:
        logger.warning("Failed to update follow_up_otto row", id=log_id, error=str(e))


async def process_lead(
    ctx: AssembledContext,
    schedule: ScheduleResult,
    action_types: list[ActionType],
    *,
    claude_client: AsyncAnthropic,
    company_name: str,
    company_config,
    sms_sender: TwilioSMSSender | None,
    pg_session: AsyncSession,
    local_session: AsyncSession,
) -> list[str]:
    """
    Process a single lead: generate messages and optionally execute.

    Returns list of log IDs created.
    """
    log_ids = []

    for action_type in action_types:
        if action_type == ActionType.SMS_TO_LEAD:
            log_id = await _process_sms(
                ctx, schedule, claude_client=claude_client,
                company_name=company_name, company_config=company_config,
                sms_sender=sms_sender, pg_session=pg_session,
                local_session=local_session,
            )
        elif action_type == ActionType.NUDGE_SALES_REP:
            log_id = await _process_nudge(
                ctx, schedule, claude_client=claude_client,
                pg_session=pg_session, local_session=local_session,
            )
        else:
            continue

        if log_id:
            log_ids.append(log_id)

    return log_ids


async def _process_sms(
    ctx: AssembledContext,
    schedule: ScheduleResult,
    *,
    claude_client: AsyncAnthropic,
    company_name: str,
    company_config,
    sms_sender: TwilioSMSSender | None,
    pg_session: AsyncSession,
    local_session: AsyncSession,
) -> str | None:
    """Generate and optionally send an SMS to the homeowner."""
    sms_text = await generate_sms(ctx, company_name, claude_client)
    if not sms_text:
        logger.warning("No SMS generated", lead_id=str(ctx.lead.lead_id))
        return None

    has_context = ctx.analysis is not None and ctx.analysis.has_meaningful_context

    # Log as proposed (review queue)
    log_id = await _log_follow_up(
        local_session,
        lead_id=ctx.lead.lead_id,
        company_id=ctx.lead.company_id,
        queue_type=ctx.queue_type,
        attempt_number=ctx.attempt_number,
        action_type=ActionType.SMS_TO_LEAD.value,
        scheduled_at=schedule.scheduled_for,
        channel="sms",
        message_content=sms_text,
        cadence_override=schedule.cadence_override,
        override_reason=schedule.override_reason,
        status=FollowUpStatus.PROPOSED.value,
        shunya_context_used=has_context,
    )
    await _insert_follow_up_otto(
        pg_session,
        id=log_id,
        lead_id=ctx.lead.lead_id,
        company_id=ctx.lead.company_id,
        message_content=sms_text,
        action_type=ActionType.SMS_TO_LEAD.value,
        scheduled_at=schedule.scheduled_for,
        status=FollowUpStatus.PROPOSED.value,
        queue_type=ctx.queue_type,
        attempt_number=ctx.attempt_number,
        assigned_rep_id=ctx.lead.assigned_rep_id,
    )

    # Execute if auto-execute is on and not dry run
    if settings.AUTO_EXECUTE and not settings.DRY_RUN:
        if not ctx.lead.phone:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.FAILED.value,
                error_message="No phone number on lead",
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.FAILED.value,
                error_message="No phone number on lead",
            )
            return log_id

        if not company_config or not sms_sender:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.FAILED.value,
                error_message="No company config or SMS sender available",
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.FAILED.value,
                error_message="No company config or SMS sender available",
            )
            return log_id

        # Build source_metadata for future masked comms integration
        source_metadata = {
            "source": "contextual-follow-up-agent",
            "follow_up_log_id": log_id,
            "attempt_number": ctx.attempt_number,
            "queue_type": ctx.queue_type,
        }

        sid = await sms_sender.send(
            to=ctx.lead.phone,
            from_=company_config.twilio_from_number,
            body=sms_text,
            source_metadata=source_metadata,
        )

        if sid:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
                external_message_id=sid,
            )
        else:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.FAILED.value,
                error_message="Twilio send failed",
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.FAILED.value,
                error_message="Twilio send failed",
            )

    return log_id


async def _process_nudge(
    ctx: AssembledContext,
    schedule: ScheduleResult,
    *,
    claude_client: AsyncAnthropic,
    pg_session: AsyncSession,
    local_session: AsyncSession,
) -> str | None:
    """Generate and optionally create a rep nudge in pending_actions."""
    nudge = await generate_rep_nudge(ctx, claude_client)
    if not nudge:
        logger.warning("No nudge generated", lead_id=str(ctx.lead.lead_id))
        return None

    nudge_text = format_nudge_as_text(nudge, ctx.lead.contact_name)
    has_context = ctx.analysis is not None and ctx.analysis.has_meaningful_context

    # Log as proposed
    log_id = await _log_follow_up(
        local_session,
        lead_id=ctx.lead.lead_id,
        company_id=ctx.lead.company_id,
        queue_type=ctx.queue_type,
        attempt_number=ctx.attempt_number,
        action_type=ActionType.NUDGE_SALES_REP.value,
        scheduled_at=schedule.scheduled_for,
        channel="pending_action",
        message_content=nudge_text,
        cadence_override=schedule.cadence_override,
        override_reason=schedule.override_reason,
        status=FollowUpStatus.PROPOSED.value,
        shunya_context_used=has_context,
    )
    await _insert_follow_up_otto(
        pg_session,
        id=log_id,
        lead_id=ctx.lead.lead_id,
        company_id=ctx.lead.company_id,
        message_content=nudge_text,
        action_type=ActionType.NUDGE_SALES_REP.value,
        scheduled_at=schedule.scheduled_for,
        status=FollowUpStatus.PROPOSED.value,
        queue_type=ctx.queue_type,
        attempt_number=ctx.attempt_number,
        assigned_rep_id=ctx.lead.assigned_rep_id,
        opening_line=nudge.opening_line,
        objections=[{"objection": o.objection, "suggested_response": o.suggested_response} for o in nudge.objections],
        key_talking_points=nudge.key_talking_points,
        close_approach=nudge.close_approach,
    )

    # Execute if auto-execute is on and not dry run
    if settings.AUTO_EXECUTE and not settings.DRY_RUN:
        if not ctx.lead.assigned_rep_id:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.FAILED.value,
                error_message="No assigned rep for nudge",
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.FAILED.value,
                error_message="No assigned rep for nudge",
            )
            return log_id

        action_id = await create_rep_nudge(
            pg_session,
            company_id=ctx.lead.company_id,
            lead_id=ctx.lead.lead_id,
            appointment_id=ctx.lead.appointment_id,
            owner_id=ctx.lead.assigned_rep_id,
            raw_text=nudge_text,
            nudge=nudge,
            due_at=schedule.scheduled_for,
            attempt_number=ctx.attempt_number,
            queue_type=ctx.queue_type,
        )

        if action_id:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
                pending_action_id=action_id,
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.SENT.value,
                sent_at=datetime.now(timezone.utc),
                pending_action_id=action_id,
            )
        else:
            await _update_log_status(
                local_session, log_id, FollowUpStatus.FAILED.value,
                error_message="pending_action INSERT failed",
            )
            await _update_follow_up_otto(
                pg_session, log_id, status=FollowUpStatus.FAILED.value,
                error_message="pending_action INSERT failed",
            )

    return log_id


async def run(
    *,
    pg_session: AsyncSession,
    local_session: AsyncSession,
    lead_id_filter: str | None = None,
) -> dict:
    """
    Main orchestrator loop.

    Args:
        pg_session: Otto-Backend PG session
        local_session: Local SQLite session
        lead_id_filter: Optional single lead ID to process

    Returns:
        Summary dict with counts.
    """
    claude_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    company_store = CompanyConfigStore()

    sms_sender = None
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        sms_sender = TwilioSMSSender(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    stats = {
        "q1_scanned": 0, "q2_scanned": 0,
        "processed": 0, "skipped_dormant": 0,
        "skipped_not_due": 0, "skipped_no_context": 0,
        "gated_opted_out": 0,
        "gated_homeowner_reply": 0,
        "gated_rep_intervened": 0,
        "actions_created": 0, "errors": 0,
    }

    # Scan both queues
    logger.info("Starting scan", dry_run=settings.DRY_RUN, auto_execute=settings.AUTO_EXECUTE)

    q1_rows = await scan_qualified_unbooked(pg_session)
    q2_rows = await scan_appointment_ran(pg_session)
    stats["q1_scanned"] = len(q1_rows)
    stats["q2_scanned"] = len(q2_rows)

    # Combine into (row, queue_type) pairs
    work_items = [
        (row, QueueType.QUALIFIED_UNBOOKED) for row in q1_rows
    ] + [
        (row, QueueType.APPOINTMENT_RAN) for row in q2_rows
    ]

    now = datetime.now(timezone.utc)

    for row, queue_type in work_items:
        try:
            # Assemble context
            ctx = await assemble_context(row, queue_type, local_session)

            # Optional single-lead filter
            if lead_id_filter and str(ctx.lead.lead_id) != lead_id_filter:
                continue

            lead_log = logger.bind(
                lead_id=str(ctx.lead.lead_id),
                queue=queue_type.value,
                attempt=ctx.attempt_number,
            )

            # Skip if no meaningful Shunya context
            if not ctx.analysis or not ctx.analysis.has_meaningful_context:
                lead_log.info("Skipping — no meaningful Shunya context")
                stats["skipped_no_context"] += 1
                continue

            # ── Intelligence Gates ────────────────────────────────

            # Gate 1: Opt-out check (always active)
            if ctx.lead.phone:
                opted_out = await is_opted_out(ctx.lead.phone, local_session)
                if opted_out:
                    lead_log.warning(
                        "Gate: opted out",
                        gate="opt_out",
                        result=True,
                    )
                    log_id = await _log_follow_up(
                        local_session,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        action_type=ActionType.MARK_DORMANT.value,
                        scheduled_at=now,
                        channel="none",
                        message_content="Sequence stopped — homeowner opted out",
                        cadence_override=False,
                        override_reason=None,
                        status=FollowUpStatus.OPTED_OUT.value,
                        shunya_context_used=False,
                        paused_reason=PausedReason.OPTED_OUT.value,
                        paused_at=now.isoformat(),
                    )
                    await _insert_follow_up_otto(
                        pg_session,
                        id=log_id,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        message_content="Sequence stopped — homeowner opted out",
                        action_type=ActionType.MARK_DORMANT.value,
                        scheduled_at=now,
                        status=FollowUpStatus.OPTED_OUT.value,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        assigned_rep_id=ctx.lead.assigned_rep_id,
                    )
                    stats["gated_opted_out"] += 1
                    continue

            # Gate 2: Homeowner reply detection (only if MASKED_COMMS_ENABLED)
            if settings.MASKED_COMMS_ENABLED:
                last_sent_at = ctx.history.last_attempt_at
                replied = await check_for_homeowner_reply(
                    str(ctx.lead.lead_id), last_sent_at, pg_session,
                )
                if replied:
                    lead_log.info(
                        "Gate: homeowner replied",
                        gate="homeowner_reply",
                        result=True,
                    )
                    # Notify the rep if one is assigned
                    if ctx.lead.assigned_rep_id:
                        await notify_rep_of_reply(
                            pg_session,
                            lead_id=str(ctx.lead.lead_id),
                            rep_id=str(ctx.lead.assigned_rep_id),
                            homeowner_name=ctx.lead.contact_name,
                            queue_type=queue_type.value,
                        )
                    log_id = await _log_follow_up(
                        local_session,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        action_type=ActionType.SMS_TO_LEAD.value,
                        scheduled_at=now,
                        channel="none",
                        message_content="Sequence paused — homeowner replied",
                        cadence_override=False,
                        override_reason=None,
                        status=FollowUpStatus.PAUSED.value,
                        shunya_context_used=False,
                        paused_reason=PausedReason.HOMEOWNER_REPLIED.value,
                        paused_at=now.isoformat(),
                    )
                    await _insert_follow_up_otto(
                        pg_session,
                        id=log_id,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        message_content="Sequence paused — homeowner replied",
                        action_type=ActionType.SMS_TO_LEAD.value,
                        scheduled_at=now,
                        status=FollowUpStatus.PAUSED.value,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        assigned_rep_id=ctx.lead.assigned_rep_id,
                    )
                    stats["gated_homeowner_reply"] += 1
                    continue

            # Gate 3: Rep intervention check (only if MASKED_COMMS_ENABLED)
            if settings.MASKED_COMMS_ENABLED:
                last_sent_at = ctx.history.last_attempt_at
                rep_active = await check_rep_manual_contact(
                    str(ctx.lead.lead_id), last_sent_at, pg_session,
                )
                if rep_active:
                    lead_log.info(
                        "Gate: rep intervened",
                        gate="rep_intervention",
                        result=True,
                    )
                    log_id = await _log_follow_up(
                        local_session,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        action_type=ActionType.SMS_TO_LEAD.value,
                        scheduled_at=now,
                        channel="none",
                        message_content="Sequence paused — rep manually contacted lead",
                        cadence_override=False,
                        override_reason=None,
                        status=FollowUpStatus.PAUSED.value,
                        shunya_context_used=False,
                        paused_reason=PausedReason.REP_INTERVENED.value,
                        paused_at=now.isoformat(),
                    )
                    await _insert_follow_up_otto(
                        pg_session,
                        id=log_id,
                        lead_id=ctx.lead.lead_id,
                        company_id=ctx.lead.company_id,
                        message_content="Sequence paused — rep manually contacted lead",
                        action_type=ActionType.SMS_TO_LEAD.value,
                        scheduled_at=now,
                        status=FollowUpStatus.PAUSED.value,
                        queue_type=queue_type.value,
                        attempt_number=ctx.attempt_number,
                        assigned_rep_id=ctx.lead.assigned_rep_id,
                    )
                    stats["gated_rep_intervened"] += 1
                    continue

            # Gate 4: All clear — proceed with existing logic
            lead_log.debug(
                "All gates passed",
                gate="all_clear",
                masked_comms_enabled=settings.MASKED_COMMS_ENABLED,
            )

            # Timing extraction
            timing_override = await extract_timing(ctx.analysis, claude_client)

            # Cadence scheduling
            schedule = compute_next_follow_up(
                queue_entered_at=ctx.lead.queue_entered_at,
                attempt_number=ctx.attempt_number,
                timing_override=timing_override,
            )

            # Dormant check
            if schedule.is_dormant:
                lead_log.info("Lead is dormant — max attempts reached")
                log_id = await _log_follow_up(
                    local_session,
                    lead_id=ctx.lead.lead_id,
                    company_id=ctx.lead.company_id,
                    queue_type=queue_type.value,
                    attempt_number=ctx.attempt_number,
                    action_type=ActionType.MARK_DORMANT.value,
                    scheduled_at=now,
                    channel="none",
                    message_content="Lead marked dormant — max attempts exceeded",
                    cadence_override=False,
                    override_reason=None,
                    status=FollowUpStatus.DORMANT.value,
                    shunya_context_used=False,
                )
                await _insert_follow_up_otto(
                    pg_session,
                    id=log_id,
                    lead_id=ctx.lead.lead_id,
                    company_id=ctx.lead.company_id,
                    message_content="Lead marked dormant — max attempts exceeded",
                    action_type=ActionType.MARK_DORMANT.value,
                    scheduled_at=now,
                    status=FollowUpStatus.DORMANT.value,
                    queue_type=queue_type.value,
                    attempt_number=ctx.attempt_number,
                    assigned_rep_id=ctx.lead.assigned_rep_id,
                )
                stats["skipped_dormant"] += 1
                continue

            # Not due yet → log as pending, skip generation (no follow_up_otto insert until we process)
            if schedule.scheduled_for > now:
                # When testing a single lead with --lead-id, force due so we can verify follow_up_otto inserts
                if lead_id_filter and str(ctx.lead.lead_id) == lead_id_filter:
                    lead_log.info(
                        "Single-lead test: forcing scheduled_for=now so lead is processed and follow_up_otto is populated",
                        was_scheduled_for=schedule.scheduled_for.isoformat(),
                    )
                    schedule = ScheduleResult(
                        scheduled_for=now,
                        is_dormant=schedule.is_dormant,
                        cadence_override=schedule.cadence_override,
                        override_reason=schedule.override_reason or "test override",
                    )
                else:
                    lead_log.info(
                        "Not due yet — skipping process_lead and follow_up_otto insert",
                        scheduled_for=schedule.scheduled_for.isoformat(),
                    )
                    stats["skipped_not_due"] += 1
                    continue

            # Determine action types
            action_types = determine_action_types(ctx)

            # Get company config for SMS
            company_config = company_store.get(str(ctx.lead.company_id))

            # Process lead
            log_ids = await process_lead(
                ctx, schedule, action_types,
                claude_client=claude_client,
                company_name=ctx.lead.company_name,
                company_config=company_config,
                sms_sender=sms_sender,
                pg_session=pg_session,
                local_session=local_session,
            )

            stats["processed"] += 1
            stats["actions_created"] += len(log_ids)

            lead_log.info(
                "Lead processed",
                actions=len(log_ids),
                action_types=[a.value for a in action_types],
            )

        except Exception as e:
            logger.error(
                "Error processing lead",
                error=str(e),
                lead_id=row.get("lead_id"),
            )
            stats["errors"] += 1

    logger.info("Orchestrator run complete", **stats)
    return stats
