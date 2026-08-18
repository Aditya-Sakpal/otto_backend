"""
Intent-to-Action: classify inbound customer SMS replies and persist intent on masked_communications.

Also derives a suggested next action (stored under extra_metadata.intent_to_action).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.models.masked_communication import MaskedCommunicationORM
from app.services.lead_phone_resolver import LeadPhoneResolver

logger = get_logger(__name__)

ALLOWED_INTENTS = frozenset(
    {
        "interested",
        "price_objection",
        "timing_issue",
        "not_interested",
        "call_me",
        "unclear",
    }
)

_INTENT_SYSTEM = """You classify short SMS replies from homeowners/leads after a sales follow-up.
Pick exactly one intent label from this list (use the slug exactly):
- interested — wants to move forward, book, yes, sounds good
- price_objection — too expensive, cost, discount, cheaper
- timing_issue — not now, later, busy, call next week/month
- not_interested — stop, no thanks, wrong number, unsubscribe tone
- call_me — prefers a phone call, "call me", ring me
- unclear — cannot tell from the message

Respond with JSON only: {"intent": "<slug>", "confidence": <number between 0 and 1>}.
"""

_api_key = (
    settings.OPENAI_API_KEY.split(",")[0].strip() if settings.OPENAI_API_KEY else ""
)
_client = openai.AsyncOpenAI(api_key=_api_key) if _api_key else None


def suggested_next_action(intent: str) -> dict[str, Any]:
    """Rule-based next-step hint for product/UI (not a second LLM call)."""
    templates: dict[str, dict[str, Any]] = {
        "interested": {
            "action_type": "reply_draft",
            "summary": "Lead is positive; confirm next step or offer times.",
            "reply_draft": (
                "Great to hear! What day works best for a quick visit or estimate?"
            ),
        },
        "price_objection": {
            "action_type": "reply_draft",
            "summary": "Address cost; offer rep callback or financing if applicable.",
            "reply_draft": (
                "Totally understand budget matters. Want me to have someone call "
                "to walk through options and any specials we have?"
            ),
        },
        "timing_issue": {
            "action_type": "reply_draft",
            "summary": "Respect timing; propose a specific follow-up time.",
            "reply_draft": (
                "No problem. What day/time should we check back with you?"
            ),
        },
        "not_interested": {
            "action_type": "pause_follow_up",
            "summary": "Pause automated follow-up; send polite close.",
            "reply_draft": "Thanks for letting us know. We'll stop reaching out.",
        },
        "call_me": {
            "action_type": "rep_call_task",
            "summary": "Create a rep call task; optional short SMS acknowledgment.",
            "reply_draft": "Got it — someone will give you a call shortly.",
        },
        "unclear": {
            "action_type": "reply_draft",
            "summary": "Ask a clarifying question.",
            "reply_draft": "Thanks for texting — what would you like us to help with?",
        },
    }
    return dict(templates.get(intent, templates["unclear"]))


async def classify_inbound_reply(message_body: str) -> tuple[str, float]:
    """
    Returns (intent_label, confidence_score). Falls back to unclear/0.0 if LLM unavailable.
    """
    text_in = (message_body or "").strip()
    if not text_in:
        return "unclear", 0.0

    if not _client:
        logger.warning("OPENAI_API_KEY not set — using unclear intent")
        return "unclear", 0.0

    try:
        response = await _client.chat.completions.create(
            model=settings.INTENT_CLASSIFICATION_MODEL,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": text_in},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        intent = str(data.get("intent", "unclear")).strip().lower()
        if intent not in ALLOWED_INTENTS:
            intent = "unclear"
        conf = float(data.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))
        return intent, conf
    except Exception as e:
        logger.error("Intent classification failed", error=str(e))
        return "unclear", 0.0


async def enrich_masked_communication_intent(
    session: AsyncSession,
    communication_id: UUID,
    *,
    force: bool = False,
) -> bool:
    """
    Load a masked_communications row, classify if inbound SMS with body, update columns.

    Returns True if an update was applied.
    """
    result = await session.execute(
        select(MaskedCommunicationORM).where(MaskedCommunicationORM.id == communication_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return False

    if row.intent_label and not force:
        return False

    body = (row.message_body or "").strip()
    if not body:
        return False

    comm = (row.comm_type or "").lower()
    direction = (row.direction or "").lower()
    if comm != "sms" or direction != "inbound" or not row.is_homeowner_reply:
        return False

    intent, conf = await classify_inbound_reply(body)
    suggestion = suggested_next_action(intent)
    meta = dict(row.extra_metadata or {})
    meta["intent_to_action"] = {
        "suggested_action_type": suggestion.get("action_type"),
        "suggested_action_summary": suggestion.get("summary"),
        "reply_draft": suggestion.get("reply_draft"),
    }

    row.intent_label = intent
    row.confidence_score = conf
    row.extra_metadata = meta
    await session.flush()
    logger.info(
        "masked_communications intent enriched",
        communication_id=str(communication_id),
        intent=intent,
        confidence=conf,
    )
    return True


async def record_twilio_inbound_sms(
    session: AsyncSession,
    *,
    from_number: str,
    to_number: str,
    body: str,
    message_sid: str | None,
) -> UUID | None:
    """
    Resolve proxy session, dedupe by Twilio MessageSid, insert masked_communications,
    classify intent, and persist intent_label / confidence_score.

    The inbound ``To`` is a **proxy number** (not the rep's real number).
    We delegate to :class:`LeadPhoneResolver.resolve_by_proxy` which joins
    ``proxy_sessions`` ↔ ``proxy_numbers`` to recover the ``lead_id``,
    ``company_id``, and ``session_id`` for this conversation.

    Returns new row id, or None if session not found / duplicate / empty body.
    """
    if message_sid:
        existing = await session.execute(
            select(MaskedCommunicationORM.id).where(
                MaskedCommunicationORM.twilio_message_sid == message_sid
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Inbound SMS duplicate MessageSid — skip", message_sid=message_sid)
            return None

    resolver = LeadPhoneResolver(session)
    ctx = await resolver.resolve_by_proxy(from_number, to_number)
    if not ctx:
        logger.warning(
            "No active proxy session for inbound SMS",
            from_number=from_number,
            to_number=to_number,
        )
        return None

    text_body = (body or "").strip()
    intent, conf = await classify_inbound_reply(text_body)
    suggestion = suggested_next_action(intent)
    extra: dict[str, Any] = {
        "intent_to_action": {
            "suggested_action_type": suggestion.get("action_type"),
            "suggested_action_summary": suggestion.get("summary"),
            "reply_draft": suggestion.get("reply_draft"),
        },
        "source": "twilio_inbound_webhook",
    }

    row = MaskedCommunicationORM(
        session_id=ctx.session_id,
        company_id=ctx.company_id,
        lead_id=ctx.lead_id,
        comm_type="sms",
        direction="inbound",
        from_number=from_number,
        to_number=to_number,
        proxy_number=ctx.proxy_number,
        twilio_message_sid=message_sid,
        message_body=text_body or None,
        is_homeowner_reply=True,
        intent_label=intent,
        confidence_score=conf,
        extra_metadata=extra,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Recorded inbound SMS with intent",
        id=str(row.id),
        intent=intent,
        confidence=conf,
        lead_id=str(ctx.lead_id),
    )
    return row.id
