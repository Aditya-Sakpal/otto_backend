"""
Opt-out handler for follow-up sequences.

Checks and records homeowner opt-outs based on keyword detection
in inbound messages. Opt-out state is stored in the local SQLite
opt_out_log table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

# Standard TCPA/CTIA opt-out keywords (case-insensitive)
OPT_OUT_KEYWORDS = frozenset({"stop", "unsubscribe", "cancel", "end", "quit"})


def detect_opt_out_keyword(message_text: str) -> bool:
    """
    Check if a message body contains a recognized opt-out keyword.

    Uses case-insensitive matching. Checks both exact match (entire
    message is a keyword) and word-boundary match (keyword appears
    as a word in a longer message).

    Args:
        message_text: The inbound SMS body text.

    Returns:
        True if an opt-out keyword is detected.
    """
    if not message_text:
        return False
    normalized = message_text.strip().lower()
    # Exact match (most common: user texts just "STOP")
    if normalized in OPT_OUT_KEYWORDS:
        return True
    # Word-boundary match for multi-word messages
    words = set(normalized.split())
    return bool(words & OPT_OUT_KEYWORDS)


async def is_opted_out(phone: str, local_session: AsyncSession) -> bool:
    """
    Check if a phone number has opted out.

    Args:
        phone: E.164 phone number.
        local_session: Local SQLite session.

    Returns:
        True if the phone has a record in opt_out_log.
    """
    result = await local_session.execute(
        text("SELECT 1 FROM opt_out_log WHERE phone = :phone LIMIT 1"),
        {"phone": phone},
    )
    row = result.first()
    opted_out = row is not None
    logger.debug(
        "Opt-out check",
        phone=phone[-4:],  # log only last 4 digits
        opted_out=opted_out,
    )
    return opted_out


async def write_opt_out(
    phone: str,
    local_session: AsyncSession,
    *,
    lead_id: str | None = None,
    source: str = "inbound_sms",
) -> str:
    """
    Record an opt-out for a phone number.

    Uses INSERT OR IGNORE to handle duplicates idempotently.

    Args:
        phone: E.164 phone number.
        local_session: Local SQLite session.
        lead_id: Optional lead UUID string.
        source: How the opt-out was detected.

    Returns:
        The opt_out_log row ID.
    """
    row_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await local_session.execute(
        text("""
            INSERT OR IGNORE INTO opt_out_log (id, phone, lead_id, opted_out_at, source)
            VALUES (:id, :phone, :lead_id, :opted_out_at, :source)
        """),
        {
            "id": row_id,
            "phone": phone,
            "lead_id": lead_id,
            "opted_out_at": now,
            "source": source,
        },
    )
    await local_session.commit()
    logger.info(
        "Opt-out recorded",
        phone=phone[-4:],
        lead_id=lead_id,
        source=source,
    )
    return row_id
