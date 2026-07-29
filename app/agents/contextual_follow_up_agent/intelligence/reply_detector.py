"""
Homeowner reply detector.

Checks the masked_communications table in Otto-Backend PG to determine
if a homeowner has replied to a follow-up message since the last
outbound attempt.

When MASKED_COMMS_ENABLED=false or the table does not exist,
this returns False immediately.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)


async def check_for_homeowner_reply(
    lead_id: str,
    since_datetime: str | None,
    pg_session: AsyncSession,
) -> bool:
    """
    Check if the homeowner has replied since our last outbound message.

    Queries masked_communications for inbound messages from the homeowner
    after since_datetime. Gracefully handles the table not existing yet
    (returns False).

    Args:
        lead_id: UUID string of the lead.
        since_datetime: ISO timestamp of the last outbound follow-up.
            If None, no previous outbound exists, so return False.
        pg_session: Otto-Backend PG async session.

    Returns:
        True if a homeowner reply was found.
    """
    if not since_datetime:
        logger.debug(
            "No previous outbound, skipping reply check",
            lead_id=lead_id,
            gate="homeowner_reply",
        )
        return False

    try:
        result = await pg_session.execute(
            text("""
                SELECT COUNT(*) FROM masked_communications
                WHERE lead_id = CAST(:lead_id AS UUID)
                  AND is_homeowner_reply = TRUE
                  AND created_at > CAST(:since_datetime AS TIMESTAMPTZ)
            """),
            {"lead_id": lead_id, "since_datetime": since_datetime},
        )
        count = result.scalar()
        replied = count is not None and count > 0

        logger.info(
            "Homeowner reply check",
            lead_id=lead_id,
            gate="homeowner_reply",
            result=replied,
            since=since_datetime,
        )
        return replied

    except Exception as e:
        error_msg = str(e).lower()
        if "masked_communications" in error_msg and (
            "does not exist" in error_msg
            or "undefined table" in error_msg
            or "relation" in error_msg
        ):
            logger.debug(
                "masked_communications table not found, skipping",
                lead_id=lead_id,
                gate="homeowner_reply",
            )
            return False
        logger.error(
            "Homeowner reply check failed",
            lead_id=lead_id,
            gate="homeowner_reply",
            error=str(e),
        )
        return False
