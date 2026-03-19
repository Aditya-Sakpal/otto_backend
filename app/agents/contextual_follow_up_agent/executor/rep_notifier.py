"""
Rep notifier for homeowner replies.

When a homeowner replies to an automated follow-up, we insert a
pending_action in Otto-Backend PG so the rep gets a real-time
notification via the existing FollowUpNotificationService.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

INSERT_REPLY_NOTIFICATION = text("""
    INSERT INTO pending_actions (
        id, company_id, lead_id, action_type,
        raw_text, status, due_at, priority, owner_id,
        source, extra_metadata, created_at
    ) VALUES (
        :id, :company_id, :lead_id, :action_type,
        :raw_text, :status, :due_at, :priority, :owner_id,
        :source, :extra_metadata, :created_at
    )
""")


async def notify_rep_of_reply(
    pg_session: AsyncSession,
    *,
    lead_id: str,
    rep_id: str,
    homeowner_name: str,
    queue_type: str,
) -> str | None:
    """
    Insert a pending_action notifying the rep that the homeowner replied.

    Args:
        pg_session: Otto-Backend PG session.
        lead_id: UUID string.
        rep_id: Rep UUID string (owner_id).
        homeowner_name: Homeowner display name for the notification text.
        queue_type: Which queue this lead belongs to.

    Returns:
        The pending_action ID on success, None on failure.
    """
    action_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    raw_text = (
        f"{homeowner_name} replied to your follow-up message. "
        f"Time to take over \u2014 check your masked comms thread in the app."
    )

    extra_metadata = {
        "agent": "contextual-follow-up",
        "queue_type": queue_type,
        "lead_id": lead_id,
        "notification_type": "homeowner_replied",
    }

    try:
        await pg_session.execute(
            INSERT_REPLY_NOTIFICATION,
            {
                "id": action_id,
                "company_id": None,  # Not available at gate level; rep lookup is by owner_id
                "lead_id": lead_id,
                "action_type": "homeowner_replied",
                "raw_text": raw_text,
                "status": "pending",
                "due_at": now + timedelta(minutes=30),
                "priority": 1,
                "owner_id": rep_id,
                "source": "system",
                "extra_metadata": json.dumps(extra_metadata),
                "created_at": now,
            },
        )
        await pg_session.commit()

        logger.info(
            "Rep notified of homeowner reply",
            action_id=action_id,
            lead_id=lead_id,
            owner_id=rep_id,
        )
        return action_id

    except Exception as e:
        await pg_session.rollback()
        logger.error(
            "Failed to notify rep of homeowner reply",
            error=str(e),
            lead_id=lead_id,
        )
        return None
