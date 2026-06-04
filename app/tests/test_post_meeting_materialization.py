"""Unit tests for post-meeting action materialization helpers (pure, no DB)."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.recording_reconciliation_service import (
    ai_action_dedup_key,
    extract_pending_actions,
    is_rep_owned_action,
    map_ai_action_type,
    parse_ai_due_at,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


# ── map_ai_action_type ───────────────────────────────────────────────────
@pytest.mark.parametrize("ai_type", [
    "send_proposal", "schedule_appointment", "follow_up", "other", "unknown", "", None,
])
def test_all_types_map_to_followup_family(ai_type):
    # Everything maps into follow_up* so it surfaces in Action Center + Guidance.
    assert map_ai_action_type(ai_type).startswith("follow_up")


def test_map_is_case_insensitive():
    assert map_ai_action_type("SEND_PROPOSAL") == "follow_up"


# ── is_rep_owned_action ──────────────────────────────────────────────────
@pytest.mark.parametrize("owner,expected", [
    ("Sales Rep", True), ("sales rep", True), ("Rep", True), ("Other", True), (None, True),
    ("Customer", False), ("customer", False), ("Homeowner", False), ("Client", False),
])
def test_rep_ownership_filter(owner, expected):
    assert is_rep_owned_action(owner) is expected


# ── parse_ai_due_at ──────────────────────────────────────────────────────
def test_parses_iso_due():
    assert parse_ai_due_at("2026-06-03T15:00:00Z", NOW) == datetime(2026, 6, 3, 15, 0, tzinfo=UTC)


def test_naive_iso_treated_as_utc():
    assert parse_ai_due_at("2026-06-03T15:00:00", NOW).tzinfo is not None


@pytest.mark.parametrize("bad", [None, "", "tomorrow afternoon", "not a date", 12345])
def test_unparseable_defaults_to_24h(bad):
    assert parse_ai_due_at(bad, NOW) == NOW + timedelta(hours=24)


def test_datetime_passthrough():
    dt = datetime(2026, 6, 5, 9, 0, tzinfo=UTC)
    assert parse_ai_due_at(dt, NOW) == dt


# ── ai_action_dedup_key ──────────────────────────────────────────────────
def test_dedup_key_stable_and_normalized():
    aid = uuid4()
    k1 = ai_action_dedup_key(aid, "Send the proposal")
    k2 = ai_action_dedup_key(aid, "  send the proposal  ")  # whitespace + case
    assert k1 == k2


def test_dedup_key_differs_by_text_and_appointment():
    aid = uuid4()
    assert ai_action_dedup_key(aid, "A") != ai_action_dedup_key(aid, "B")
    assert ai_action_dedup_key(uuid4(), "A") != ai_action_dedup_key(uuid4(), "A")


# ── extract_pending_actions ──────────────────────────────────────────────
def test_extracts_list():
    data = {"summary": {"pending_actions": [
        {"type": "send_proposal", "raw_text": "x"},
        {"type": "follow_up", "raw_text": "y"},
    ]}}
    assert len(extract_pending_actions(data)) == 2


def test_tolerates_single_dict():
    data = {"summary": {"pending_actions": {"type": "follow_up", "raw_text": "x"}}}
    assert len(extract_pending_actions(data)) == 1


def test_filters_non_dict_entries():
    data = {"summary": {"pending_actions": [{"raw_text": "x"}, "junk", None, 5]}}
    assert len(extract_pending_actions(data)) == 1


@pytest.mark.parametrize("data", [
    {}, {"summary": {}}, {"summary": {"pending_actions": None}},
    {"summary": "notadict"}, {"summary": {"pending_actions": "x"}},
])
def test_empty_or_malformed_returns_empty(data):
    assert extract_pending_actions(data) == []
