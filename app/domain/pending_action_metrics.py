"""
Pending action type → executive metrics bucket mapping.

Buckets are mutually exclusive (priority: calls_to_make > appointments_to_schedule > follow_ups_needed).
"""
from __future__ import annotations

from typing import Literal, Optional

MetricsBucket = Literal["calls_to_make", "appointments_to_schedule", "follow_ups_needed"]

# Exact action_type values (lowercase) — aligned with tasks API / Shunya taxonomy
CALLS_TO_MAKE_TYPES = frozenset({
    "call_back",
    "callback",
    "check_in",
})

APPOINTMENTS_TO_SCHEDULE_TYPES = frozenset({
    "book_appointment",
    "reschedule",
    "schedule_appointment",
    "schedule_visit",
    "site_visit",
    "inspection",
    "measurement",
})

FOLLOW_UPS_NEEDED_TYPES = frozenset({
    "follow_up",
    "follow_up_call",
    "send_quote",
    "send_estimate",
    "send_contract",
    "send_info",
    "send_photos",
    "send_details",
    "send_invoice",
    "custom",
    "verify_details",
    "rehash",
})


def classify_pending_action_type(action_type: Optional[str]) -> Optional[MetricsBucket]:
    """Return metrics bucket for an action_type, or None if uncategorized."""
    if not action_type:
        return None
    normalized = action_type.strip().lower()
    if not normalized:
        return None

    if normalized in CALLS_TO_MAKE_TYPES or "call_back" in normalized:
        return "calls_to_make"

    if (
        normalized in APPOINTMENTS_TO_SCHEDULE_TYPES
        or "schedule" in normalized
        or normalized.startswith("book_appointment")
    ):
        return "appointments_to_schedule"

    if (
        normalized in FOLLOW_UPS_NEEDED_TYPES
        or normalized.startswith("follow_up")
        or "follow_up" in normalized
    ):
        return "follow_ups_needed"

    return None
