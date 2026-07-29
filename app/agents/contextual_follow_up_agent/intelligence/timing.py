"""
Timing extraction using Claude API.

Extracts explicit temporal references from Shunya analysis to override
the default cadence schedule.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from anthropic import AsyncAnthropic

from contextual_follow_up_agent.cadence.scheduler import TimingOverride
from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.intelligence.prompts import (
    TIMING_EXTRACTION_SYSTEM,
    TIMING_EXTRACTION_USER,
)
from contextual_follow_up_agent.models.context import AnalysisContext

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 256


def _format_pending_actions(actions: list[dict] | None) -> str:
    """Format pending_actions JSON into readable text."""
    if not actions:
        return "None"
    lines = []
    for a in actions:
        action = a.get("action_item") or a.get("raw_text", "unknown")
        due = a.get("due_at", "no date")
        lines.append(f"- {action} (due: {due})")
    return "\n".join(lines) if lines else "None"


def _format_list(items: list[str] | None) -> str:
    """Format a list of strings into readable text."""
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


async def extract_timing(
    analysis: AnalysisContext,
    client: AsyncAnthropic,
) -> TimingOverride | None:
    """
    Use Claude to extract explicit timing signals from Shunya analysis.

    Returns TimingOverride if a clear temporal reference is found,
    None otherwise.
    """
    if not analysis.summary and not analysis.pending_actions:
        return None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    user_prompt = TIMING_EXTRACTION_USER.format(
        today=today,
        summary=analysis.summary or "No summary available",
        next_steps=_format_list(analysis.next_steps),
        action_items=_format_list(analysis.action_items),
        pending_actions=_format_pending_actions(analysis.pending_actions),
    )

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=TIMING_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()
        parsed = _parse_json_response(raw_text)

        if not parsed.get("has_override"):
            return None

        override_date_str = parsed.get("override_date")
        if not override_date_str:
            return None

        override_date = datetime.strptime(override_date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        # Reject dates in the past
        if override_date <= datetime.now(timezone.utc):
            logger.info("Timing override date is in the past, ignoring", date=override_date_str)
            return None

        return TimingOverride(
            override_date=override_date,
            reason=parsed.get("reason", "Timing signal detected"),
            confidence=float(parsed.get("confidence", 0.0)),
        )

    except Exception as e:
        logger.error("Timing extraction failed", error=str(e))
        return None


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
        logger.warning("Failed to parse timing JSON response", raw_text=raw_text[:200])
        return {}
