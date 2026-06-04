"""Unit tests for Action Center ranking helpers (pure, no DB)."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.domain.schemas.tasks import ActionCenterItem
from app.services.pending_action_service import (
    ACTION_CENTER_TIER_ORDER,
    compute_urgency_tier,
    compute_value_score,
    normalize_action_family,
    _sort_key,
)

UTC = ZoneInfo("UTC")
TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 6, 1, 16, 0, tzinfo=UTC)  # noon EDT


# ── normalize_action_family ──────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("call_back", "call_back"),
    ("callback", "call_back"),
    ("CALL_BACK", "call_back"),
    ("appointment_reminder", "appointment_reminder"),
    ("rehash", "rehash"),
    ("follow_up", "follow_up"),
    ("follow_up_call", "follow_up"),
    ("follow_up_anything", "follow_up"),
    ("send_quote", None),
    ("book_appointment", None),
    ("", None),
    (None, None),
])
def test_normalize_action_family(raw, expected):
    assert normalize_action_family(raw) == expected


def test_whitelist_excludes_send_quote():
    assert normalize_action_family("send_quote") is None


# ── compute_value_score ──────────────────────────────────────────────────

def test_value_score_ordering_across_families():
    call_back = compute_value_score("call_back", None)
    one_hour = compute_value_score("appointment_reminder", {"reminder_kind": "one_hour_before"})
    follow_up = compute_value_score("follow_up", None)
    appt_no_kind = compute_value_score("appointment_reminder", None)
    morning = compute_value_score("appointment_reminder", {"reminder_kind": "morning_of"})
    assert call_back > one_hour > follow_up > appt_no_kind > morning


def test_reminder_kind_ordering():
    one_hour = compute_value_score("appointment_reminder", {"reminder_kind": "one_hour_before"})
    morning = compute_value_score("appointment_reminder", {"reminder_kind": "morning_of"})
    day_before = compute_value_score("appointment_reminder", {"reminder_kind": "day_before"})
    assert one_hour > morning
    assert morning == day_before  # same tier per plan


def test_rehash_category_ordering():
    appt_pending = compute_value_score("rehash", {"rehash_category": "appointment_pending"})
    qualified = compute_value_score("rehash", {"rehash_category": "qualified_unbooked"})
    stale = compute_value_score("rehash", {"rehash_category": "stale_lead"})
    unknown = compute_value_score("rehash", {"rehash_category": "whatever"})
    assert appt_pending > qualified > stale > unknown


# ── compute_urgency_tier ─────────────────────────────────────────────────

def test_tier_overdue():
    tier, mins = compute_urgency_tier(NOW - timedelta(minutes=30), NOW, TZ)
    assert tier == "overdue"
    assert mins == -30


def test_tier_due_now():
    tier, mins = compute_urgency_tier(NOW + timedelta(minutes=10), NOW, TZ)
    assert tier == "due_now"


def test_tier_due_soon():
    tier, _ = compute_urgency_tier(NOW + timedelta(minutes=90), NOW, TZ)
    assert tier == "due_soon"


def test_tier_later_today():
    # +6h is same local calendar day (noon EDT → 6 PM EDT)
    tier, _ = compute_urgency_tier(NOW + timedelta(hours=6), NOW, TZ)
    assert tier == "later_today"


def test_tier_upcoming():
    tier, _ = compute_urgency_tier(NOW + timedelta(days=2), NOW, TZ)
    assert tier == "upcoming"


def test_tier_no_due_date():
    tier, mins = compute_urgency_tier(None, NOW, TZ)
    assert tier == "no_due_date"
    assert mins is None


def test_naive_due_at_treated_as_utc():
    tier, mins = compute_urgency_tier(
        (NOW + timedelta(minutes=10)).replace(tzinfo=None), NOW, TZ
    )
    assert tier == "due_now"


# ── global sort / next ───────────────────────────────────────────────────

def _item(action_type, due_at, meta=None, created_at=None):
    family = normalize_action_family(action_type)
    tier, mins = compute_urgency_tier(due_at, NOW, TZ)
    score = compute_value_score(action_type, meta)
    if tier == "overdue":
        score += 5
    return ActionCenterItem(
        id=uuid4(),
        company_id=uuid4(),
        action_type=action_type,
        status="pending",
        due_at=due_at,
        created_at=created_at or NOW,
        urgency_tier=tier,
        value_score=score,
        minutes_until_due=mins,
        action_family=family,
        display_title="x",
    )


def test_overdue_callback_ranks_above_due_soon_rehash():
    callback = _item("call_back", NOW - timedelta(minutes=5))
    rehash = _item("rehash", NOW + timedelta(minutes=90), {"rehash_category": "qualified_unbooked"})
    ordered = sorted([rehash, callback], key=_sort_key)
    assert ordered[0] is callback  # overdue tier wins regardless of value


def test_three_reminders_same_tier_ordered_by_kind():
    due = NOW + timedelta(minutes=10)  # all due_now
    one_hour = _item("appointment_reminder", due, {"reminder_kind": "one_hour_before"})
    morning = _item("appointment_reminder", due, {"reminder_kind": "morning_of"})
    day_before = _item("appointment_reminder", due, {"reminder_kind": "day_before"})
    ordered = sorted([day_before, morning, one_hour], key=_sort_key)
    assert ordered[0] is one_hour
    # morning vs day_before tie on score → stable by due/created (both equal here)


def test_no_due_date_sorts_after_timed_tiers():
    timed = _item("follow_up", NOW + timedelta(minutes=30))
    no_due = _item("call_back", None)  # higher value but no due date
    ordered = sorted([no_due, timed], key=_sort_key)
    assert ordered[0] is timed
    assert ordered[1] is no_due


def test_tier_order_constant_is_complete():
    assert ACTION_CENTER_TIER_ORDER == [
        "overdue", "due_now", "due_soon", "later_today", "upcoming", "no_due_date"
    ]
