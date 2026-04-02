"""
Rep manual activity detector.

Checks the masked_communications table in Otto-Backend PG to determine
if a sales rep has manually contacted the homeowner since the last
automated follow-up attempt.

When MASKED_COMMS_ENABLED=false or the table does not exist,
this returns False immediately.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)


async def check_rep_manual_contact(
    lead_id: str,
    since_datetime: str | None,
    pg_session: AsyncSession,
) -> bool:
    """
    Check if a rep has manually contacted the homeowner since our last outbound.

    Queries masked_communications for outbound messages NOT from the
    follow-up agent. Gracefully handles the table not existing yet
    (returns False).

    Args:
        lead_id: UUID string of the lead.
        since_datetime: ISO timestamp of the last outbound follow-up.
            If None, no previous outbound exists, so return False.
        pg_session: Otto-Backend PG async session.

    Returns:
        True if rep manual contact was detected.
    """
    if not since_datetime:
        logger.debug(
            "No previous outbound, skipping rep activity check",
            lead_id=lead_id,
            gate="rep_intervention",
        )
        return False

    try:
        result = await pg_session.execute(
            text("""
                SELECT COUNT(*) FROM masked_communications
                WHERE lead_id = CAST(:lead_id AS UUID)
                  AND direction = 'outbound'
                  AND (source_metadata->>'source' IS NULL
                       OR source_metadata->>'source' != 'contextual-follow-up-agent')
                  AND created_at > CAST(:since_datetime AS TIMESTAMPTZ)
            """),
            {"lead_id": lead_id, "since_datetime": since_datetime},
        )
        count = result.scalar()
        rep_active = count is not None and count > 0

        logger.info(
            "Rep activity check",
            lead_id=lead_id,
            gate="rep_intervention",
            result=rep_active,
            since=since_datetime,
        )
        return rep_active

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
                gate="rep_intervention",
            )
            return False
        logger.error(
            "Rep activity check failed",
            lead_id=lead_id,
            gate="rep_intervention",
            error=str(e),
        )
        return False
