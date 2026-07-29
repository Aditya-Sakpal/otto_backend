"""
Context assembler.

Takes raw scanner rows and assembles full AssembledContext objects
by joining with follow-up history from local SQLite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.models.context import (
    AnalysisContext,
    AssembledContext,
    FollowUpHistory,
    FollowUpHistoryEntry,
    LeadProfile,
)
from contextual_follow_up_agent.models.enums import QueueType

logger = get_logger(__name__)


def _build_lead_profile_q1(row: dict) -> LeadProfile:
    """Build LeadProfile from a Queue 1 scanner row."""
    return LeadProfile(
        lead_id=row["lead_id"],
        company_id=row["company_id"],
        company_name=row["company_name"],
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        phone=row.get("primary_phone"),
        address=row.get("address"),
        city=row.get("city"),
        state=row.get("state"),
        postal_code=row.get("postal_code"),
        property_snapshot=row.get("property_snapshot"),
        pipeline_stage=row["pipeline_stage"],
        lead_status=row["lead_status"],
        assigned_rep_id=row.get("assigned_rep_id"),
        queue_entered_at=row["lead_created_at"],
    )


def _build_lead_profile_q2(row: dict) -> LeadProfile:
    """Build LeadProfile from a Queue 2 scanner row."""
    return LeadProfile(
        lead_id=row["lead_id"],
        company_id=row["company_id"],
        company_name=row["company_name"],
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        phone=row.get("primary_phone"),
        address=row.get("address"),
        city=row.get("city"),
        state=row.get("state"),
        postal_code=row.get("postal_code"),
        property_snapshot=row.get("property_snapshot"),
        pipeline_stage=row["pipeline_stage"],
        lead_status=row["lead_status"],
        assigned_rep_id=row.get("assigned_rep_id"),
        queue_entered_at=row["scheduled_start"],
        appointment_id=row.get("appointment_id"),
    )


def _build_analysis_q1(row: dict) -> AnalysisContext | None:
    """Build AnalysisContext from Queue 1 call_analyses data."""
    if not row.get("summary"):
        return None
    return AnalysisContext(
        summary=row.get("summary"),
        key_points=row.get("key_points"),
        action_items=row.get("action_items"),
        next_steps=row.get("next_steps"),
        pending_actions=row.get("pending_actions"),
        objections=row.get("objections"),
        objection_texts=row.get("objection_texts"),
        objections_total_count=row.get("objections_total_count") or 0,
        sentiment_score=row.get("sentiment_score"),
        qualification_status=row.get("qualification_status"),
        booking_status=row.get("booking_status"),
        service_requested=row.get("service_requested"),
        property_details=row.get("property_details"),
        follow_up_required=row.get("follow_up_required"),
        follow_up_reason=row.get("follow_up_reason"),
        bant_need=row.get("bant_need_score"),
        bant_budget=row.get("bant_budget_score"),
        bant_timeline=row.get("bant_timeline_score"),
        bant_authority=row.get("bant_authority_score"),
        overall_score=row.get("qualification_overall_score"),
    )


def _build_analysis_q2(row: dict) -> AnalysisContext | None:
    """Build AnalysisContext from Queue 2 appointment + call_analyses data."""
    appt_summary = row.get("appt_summary")
    call_summary = row.get("call_summary")
    if not appt_summary and not call_summary:
        return None

    # Prefer appointment-level analysis, fall back to call-level
    summary = appt_summary or call_summary
    objection_texts = row.get("appt_objection_texts") or row.get("call_objection_texts")
    pending_actions = row.get("appt_pending_actions") or row.get("call_pending_actions")
    sentiment = row.get("appt_sentiment") or row.get("call_sentiment")

    return AnalysisContext(
        summary=summary,
        key_points=row.get("appt_key_points"),
        action_items=row.get("appt_action_items"),
        next_steps=row.get("appt_next_steps"),
        pending_actions=pending_actions if isinstance(pending_actions, list) else None,
        objections=row.get("appt_objections"),
        objection_texts=objection_texts,
        objections_total_count=len(objection_texts) if objection_texts else 0,
        sentiment_score=sentiment,
        service_requested=row.get("service_requested"),
        property_details=row.get("property_details"),
        bant_need=row.get("bant_need_score"),
        bant_budget=row.get("bant_budget_score"),
        bant_timeline=row.get("bant_timeline_score"),
        bant_authority=row.get("bant_authority_score"),
        overall_score=row.get("qualification_overall_score"),
    )


async def _get_follow_up_history(
    local_session: AsyncSession,
    lead_id: UUID,
    queue_type: str,
) -> FollowUpHistory:
    """Query local SQLite for previous follow-up attempts."""
    result = await local_session.execute(
        text("""
            SELECT attempt_number, action_type, scheduled_at, sent_at,
                   message_content, status
            FROM follow_up_log
            WHERE lead_id = :lead_id AND queue_type = :queue_type
            ORDER BY attempt_number ASC
        """),
        {"lead_id": str(lead_id), "queue_type": queue_type},
    )
    rows = result.mappings().all()
    entries = [
        FollowUpHistoryEntry(
            attempt_number=r["attempt_number"],
            action_type=r["action_type"],
            scheduled_at=r["scheduled_at"],
            sent_at=r.get("sent_at"),
            message_content=r["message_content"],
            status=r["status"],
        )
        for r in rows
    ]
    return FollowUpHistory(entries=entries)


async def assemble_context(
    row: dict,
    queue_type: QueueType,
    local_session: AsyncSession,
) -> AssembledContext:
    """
    Assemble full context for a single lead.

    Args:
        row: Raw scanner row dict
        queue_type: Which queue this lead came from
        local_session: Local SQLite session for follow-up history
    """
    if queue_type == QueueType.QUALIFIED_UNBOOKED:
        lead = _build_lead_profile_q1(row)
        analysis = _build_analysis_q1(row)
    else:
        lead = _build_lead_profile_q2(row)
        analysis = _build_analysis_q2(row)

    history = await _get_follow_up_history(
        local_session, lead.lead_id, queue_type.value
    )

    # Compute attempt number: count unique attempt_numbers already logged
    # Each attempt can have multiple action_types (sms + nudge), so deduplicate
    existing_attempts = set(e.attempt_number for e in history.entries)
    attempt_number = (max(existing_attempts) + 1) if existing_attempts else 1

    # Days since event
    now = datetime.now(timezone.utc)
    event_time = lead.queue_entered_at
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    days_since = (now - event_time).days

    return AssembledContext(
        lead=lead,
        analysis=analysis,
        history=history,
        queue_type=queue_type.value,
        attempt_number=attempt_number,
        days_since_event=days_since,
    )
