"""Unit tests for pending action metrics bucket classification."""
import pytest

from app.domain.pending_action_metrics import classify_pending_action_type


@pytest.mark.parametrize(
    "action_type,expected",
    [
        ("call_back", "calls_to_make"),
        ("callback", "calls_to_make"),
        ("check_in", "calls_to_make"),
        ("schedule_appointment", "appointments_to_schedule"),
        ("book_appointment", "appointments_to_schedule"),
        ("reschedule", "appointments_to_schedule"),
        ("site_visit", "appointments_to_schedule"),
        ("rehash", "follow_ups_needed"),
        ("follow_up", "follow_ups_needed"),
        ("follow_up_call", "follow_ups_needed"),
        ("send_quote", "follow_ups_needed"),
        ("send_estimate", "follow_ups_needed"),
        ("custom", "follow_ups_needed"),
        ("verify_details", "follow_ups_needed"),
    ],
)
def test_classify_pending_action_type(action_type: str, expected: str):
    assert classify_pending_action_type(action_type) == expected


def test_classify_mutually_exclusive_priority():
    """call_back wins over follow_up substring edge cases."""
    assert classify_pending_action_type("call_back") == "calls_to_make"


def test_classify_uncategorized():
    assert classify_pending_action_type("unknown_type") is None
    assert classify_pending_action_type(None) is None
