"""Unit tests for the generic task reminder grace-window eligibility (Issue 1)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.followup_notification_service import generic_task_reminder_eligible

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
GRACE = settings.GENERIC_TASK_REMINDER_GRACE_MINUTES


def test_before_due_not_eligible():
    # Future due_at → wait (do not fire early).
    assert generic_task_reminder_eligible(NOW + timedelta(minutes=5), NOW) is False


def test_at_due_eligible():
    assert generic_task_reminder_eligible(NOW, NOW) is True


def test_inside_grace_window_eligible():
    # Due 10 min ago, grace not yet elapsed → fires (Case 4: downtime recovery).
    assert generic_task_reminder_eligible(NOW - timedelta(minutes=10), NOW) is True


def test_at_grace_boundary_not_eligible():
    # due_at + grace == now → window is half-open [due, due+grace); not eligible.
    assert generic_task_reminder_eligible(NOW - timedelta(minutes=GRACE), NOW) is False


def test_past_grace_not_eligible():
    # Too old → skip (one missed beat, no late spam).
    assert generic_task_reminder_eligible(NOW - timedelta(minutes=GRACE + 5), NOW) is False


def test_none_due_not_eligible():
    assert generic_task_reminder_eligible(None, NOW) is False


def test_naive_due_treated_as_utc():
    naive = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    assert generic_task_reminder_eligible(naive, NOW) is True


def test_window_is_recoverable_across_downtime():
    """Case 4 essence: a tick that would have fired mid-window still fires later
    in the window (unlike the old future-only `0 < minutes_until_due`)."""
    due = NOW - timedelta(minutes=GRACE - 1)  # just inside grace
    assert generic_task_reminder_eligible(due, NOW) is True
    # Old logic (0 < minutes_until_due) would be False here since due is in the past.
    minutes_until_due = (due - NOW).total_seconds() / 60
    assert minutes_until_due < 0  # proves old threshold check would NOT fire
