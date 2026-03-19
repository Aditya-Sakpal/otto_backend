"""
Pending action executor.

Writes rep nudges to the pending_actions table in Otto-Backend PG.
The existing FollowUpNotificationService picks these up and sends
WebSocket notifications to the rep at 15/5 min before due_at.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.models.output import RepNudge

logger = get_logger(__name__)

INSERT_PENDING_ACTION = text("""
    INSERT INTO pending_actions (
        id, company_id, lead_id, appointment_id, action_type,
        raw_text, status, due_at, priority, owner_id,
        assigned_by_id, source, extra_metadata, created_at
    ) VALUES (
        :id, :company_id, :lead_id, :appointment_id, :action_type,
        :raw_text, :status, :due_at, :priority, :owner_id,
        :assigned_by_id, :source, :extra_metadata, :created_at
    )
""")


async def create_rep_nudge(
    pg_session: AsyncSession,
    *,
    company_id: uuid.UUID,
    lead_id: uuid.UUID,
    appointment_id: uuid.UUID | None,
    owner_id: uuid.UUID,
    raw_text: str,
    nudge: RepNudge,
    due_at: datetime,
    attempt_number: int,
    queue_type: str,
) -> str | None:
    """
    Insert a rep nudge into the pending_actions table.

    Returns the pending_action ID on success, None on failure.
    """
    action_id = str(uuid.uuid4())

    # Priority: 1 (high) for attempt 1, 2 for attempt 2, 3 for attempt 3
    priority = min(attempt_number, 5)

    extra_metadata = {
        "agent": "contextual-follow-up",
        "attempt": attempt_number,
        "queue_type": queue_type,
        "nudge": nudge.model_dump(),
    }

    try:
        await pg_session.execute(
            INSERT_PENDING_ACTION,
            {
                "id": action_id,
                "company_id": str(company_id),
                "lead_id": str(lead_id),
                "appointment_id": str(appointment_id) if appointment_id else None,
                "action_type": "follow_up_call",
                "raw_text": raw_text,
                "status": "pending",
                "due_at": due_at,
                "priority": priority,
                "owner_id": str(owner_id),
                "assigned_by_id": None,
                "source": "system",
                "extra_metadata": json.dumps(extra_metadata),
                "created_at": datetime.utcnow(),
            },
        )
        await pg_session.commit()

        logger.info(
            "Rep nudge created in pending_actions",
            action_id=action_id,
            lead_id=str(lead_id),
            owner_id=str(owner_id),
            due_at=str(due_at),
        )
        return action_id

    except Exception as e:
        await pg_session.rollback()
        logger.error(
            "Failed to create pending_action",
            error=str(e),
            lead_id=str(lead_id),
        )
        return None
