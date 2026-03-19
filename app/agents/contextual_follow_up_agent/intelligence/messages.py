"""
Message generation using Claude API.

Generates:
1. SMS text for homeowners (<160 chars)
2. Structured rep nudge for sales reps (Queue 2 only)
"""
from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.intelligence.prompts import (
    REP_NUDGE_SYSTEM,
    REP_NUDGE_USER,
    SMS_GENERATION_SYSTEM,
    SMS_GENERATION_USER,
)
from contextual_follow_up_agent.models.context import AssembledContext
from contextual_follow_up_agent.models.output import ObjectionResponse, RepNudge

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"
SMS_MAX_TOKENS = 100
NUDGE_MAX_TOKENS = 600


async def generate_sms(
    ctx: AssembledContext,
    company_name: str,
    client: AsyncAnthropic,
) -> str | None:
    """
    Generate an SMS follow-up message for a homeowner.

    Returns the SMS text (<160 chars) or None on failure.
    """
    if not ctx.analysis or not ctx.analysis.has_meaningful_context:
        logger.info("Skipping SMS generation — no meaningful Shunya context",
                     lead_id=str(ctx.lead.lead_id))
        return None

    previous_messages = "None"
    if ctx.history.entries:
        sms_entries = [e for e in ctx.history.entries if e.action_type == "sms_to_lead"]
        if sms_entries:
            previous_messages = "\n".join(
                f"- Attempt {e.attempt_number}: {e.message_content}" for e in sms_entries
            )

    system_prompt = SMS_GENERATION_SYSTEM.format(company_name=company_name)
    user_prompt = SMS_GENERATION_USER.format(
        lead_name=ctx.lead.contact_name,
        service_requested=ctx.analysis.service_requested or "home services",
        days_since=ctx.days_since_event,
        attempt_number=ctx.attempt_number,
        summary=ctx.analysis.summary or "No summary available",
        primary_objection=ctx.analysis.primary_objection or "None noted",
        previous_messages=previous_messages,
    )

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=SMS_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        sms_text = response.content[0].text.strip().strip('"')

        # Enforce 160 char limit
        if len(sms_text) > 160:
            logger.warning("SMS exceeded 160 chars, truncating",
                           length=len(sms_text), lead_id=str(ctx.lead.lead_id))
            sms_text = sms_text[:157] + "..."

        return sms_text

    except Exception as e:
        logger.error("SMS generation failed", error=str(e),
                     lead_id=str(ctx.lead.lead_id))
        return None


async def generate_rep_nudge(
    ctx: AssembledContext,
    client: AsyncAnthropic,
) -> RepNudge | None:
    """
    Generate a structured call agenda for a sales rep.

    Returns RepNudge or None on failure.
    """
    if not ctx.analysis or not ctx.analysis.has_meaningful_context:
        logger.info("Skipping nudge generation — no meaningful Shunya context",
                     lead_id=str(ctx.lead.lead_id))
        return None

    objections_text = "None noted"
    if ctx.analysis.objection_texts:
        objections_text = "\n".join(
            f"- {obj}" for obj in ctx.analysis.objection_texts
        )

    key_points_text = "None"
    if ctx.analysis.key_points:
        key_points_text = "\n".join(
            f"- {kp}" for kp in ctx.analysis.key_points
        )

    previous_attempts = "None"
    if ctx.history.entries:
        nudge_entries = [e for e in ctx.history.entries if e.action_type == "nudge_sales_rep"]
        if nudge_entries:
            previous_attempts = "\n".join(
                f"- Attempt {e.attempt_number}: {e.status}" for e in nudge_entries
            )

    user_prompt = REP_NUDGE_USER.format(
        lead_name=ctx.lead.contact_name,
        service_requested=ctx.analysis.service_requested or "home services",
        days_since=ctx.days_since_event,
        attempt_number=ctx.attempt_number,
        summary=ctx.analysis.summary or "No summary available",
        objections=objections_text,
        sentiment=ctx.analysis.sentiment_score if ctx.analysis.sentiment_score is not None else "unknown",
        key_points=key_points_text,
        previous_attempts=previous_attempts,
    )

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=NUDGE_MAX_TOKENS,
            system=REP_NUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()
        parsed = _parse_json_response(raw_text)

        if not parsed:
            return None

        objection_responses = [
            ObjectionResponse(
                objection=obj.get("objection", ""),
                suggested_response=obj.get("suggested_response", ""),
            )
            for obj in parsed.get("objections", [])
        ]

        return RepNudge(
            opening_line=parsed.get("opening_line", ""),
            objections=objection_responses,
            close_approach=parsed.get("close_approach", ""),
            key_talking_points=parsed.get("key_talking_points", []),
        )

    except Exception as e:
        logger.error("Rep nudge generation failed", error=str(e),
                     lead_id=str(ctx.lead.lead_id))
        return None


def format_nudge_as_text(nudge: RepNudge, lead_name: str) -> str:
    """Format a RepNudge into human-readable text for pending_action.raw_text."""
    lines = [
        f"Follow-up call agenda for {lead_name}:",
        "",
        f"Opening: {nudge.opening_line}",
    ]

    if nudge.objections:
        lines.append("")
        lines.append("Objections to address:")
        for obj in nudge.objections:
            lines.append(f"  - \"{obj.objection}\"")
            lines.append(f"    Response: {obj.suggested_response}")

    if nudge.key_talking_points:
        lines.append("")
        lines.append("Key talking points:")
        for tp in nudge.key_talking_points:
            lines.append(f"  - {tp}")

    lines.append("")
    lines.append(f"Close: {nudge.close_approach}")

    return "\n".join(lines)


def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from Claude response, handling markdown fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if len(lines) > 2 else lines[1:])
        text = text.strip().rstrip("`")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse nudge JSON response", raw_text=raw_text[:200])
        return {}
