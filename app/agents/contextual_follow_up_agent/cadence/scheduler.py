"""
Cadence scheduler.

Computes when the next follow-up should fire based on:
1. Baseline cadence: +3d, +7d after that, +14d after that
2. Timing overrides from Shunya analysis (explicit temporal references)
3. Max attempts → dormant
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from contextual_follow_up_agent.config.settings import settings


@dataclass
class ScheduleResult:
    """Result of cadence scheduling for one lead."""

    scheduled_for: datetime | None  # None if dormant
    is_dormant: bool
    cadence_override: bool
    override_reason: str | None


@dataclass
class TimingOverride:
    """A timing override extracted from Shunya analysis by Claude."""

    override_date: datetime
    reason: str
    confidence: float


def compute_next_follow_up(
    queue_entered_at: datetime,
    attempt_number: int,
    timing_override: TimingOverride | None = None,
) -> ScheduleResult:
    """
    Compute when to schedule the next follow-up.

    Args:
        queue_entered_at: When the lead entered the queue
            (created_at for Q1, scheduled_start for Q2)
        attempt_number: Which attempt this is (1, 2, or 3)
        timing_override: Optional override from Claude timing extraction

    Returns:
        ScheduleResult with scheduled date or dormant flag
    """
    max_attempts = settings.MAX_ATTEMPTS

    # Past max attempts → dormant
    if attempt_number > max_attempts:
        return ScheduleResult(
            scheduled_for=None,
            is_dormant=True,
            cadence_override=False,
            override_reason=None,
        )

    # If timing override exists with sufficient confidence, use it
    if timing_override and timing_override.confidence >= settings.TIMING_OVERRIDE_MIN_CONFIDENCE:
        override_dt = timing_override.override_date
        if override_dt.tzinfo is None:
            override_dt = override_dt.replace(tzinfo=timezone.utc)
        return ScheduleResult(
            scheduled_for=override_dt,
            is_dormant=False,
            cadence_override=True,
            override_reason=timing_override.reason,
        )

    # Baseline cadence: cumulative days from queue entry
    cadence_days = [
        settings.CADENCE_ATTEMPT_1_DAYS,
        settings.CADENCE_ATTEMPT_2_DAYS,
        settings.CADENCE_ATTEMPT_3_DAYS,
    ]
    # Cumulative: attempt 1 = +3, attempt 2 = +3+7=+10, attempt 3 = +3+7+14=+24
    cumulative_days = sum(cadence_days[:attempt_number])

    if queue_entered_at.tzinfo is None:
        queue_entered_at = queue_entered_at.replace(tzinfo=timezone.utc)

    scheduled = queue_entered_at + timedelta(days=cumulative_days)

    return ScheduleResult(
        scheduled_for=scheduled,
        is_dormant=False,
        cadence_override=False,
        override_reason=None,
    )
