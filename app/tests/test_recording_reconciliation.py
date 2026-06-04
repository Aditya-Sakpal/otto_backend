"""Unit tests for stuck-recording reconciliation decision logic (no DB/network)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.recording_reconciliation_service import (
    ACTION_COMPLETE,
    ACTION_FAIL,
    ACTION_WAIT,
    decide_reconcile_action,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _recent():
    # Processing started recently (well within the max window).
    return NOW - timedelta(minutes=10)


def _ancient():
    # Past the hard MAX_PROCESSING_HOURS ceiling.
    return NOW - timedelta(hours=settings.RECORDING_MAX_PROCESSING_HOURS + 1)


# ── Shunya reports completed ─────────────────────────────────────────────
def test_completed_job_completes():
    action, reason = decide_reconcile_action(
        job_status="completed", processing_since=_recent(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_COMPLETE
    assert reason is None


def test_completed_is_case_insensitive():
    action, _ = decide_reconcile_action(
        job_status="COMPLETED", processing_since=_recent(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_COMPLETE


# ── Shunya reports failed ────────────────────────────────────────────────
def test_failed_job_fails_with_reason():
    action, reason = decide_reconcile_action(
        job_status="failed", processing_since=_recent(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_FAIL
    assert reason and "failed" in reason.lower()


# ── Still running ────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["running", "queued", "unknown", None, ""])
def test_in_flight_waits(status):
    action, reason = decide_reconcile_action(
        job_status=status, processing_since=_recent(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_WAIT
    assert reason is None


# ── Hard timeout ceiling ─────────────────────────────────────────────────
def test_running_but_past_ceiling_times_out():
    action, reason = decide_reconcile_action(
        job_status="running", processing_since=_ancient(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_FAIL
    assert "timed out" in reason.lower()


def test_completed_wins_even_if_past_ceiling():
    # If Shunya says completed, recover it regardless of age.
    action, _ = decide_reconcile_action(
        job_status="completed", processing_since=_ancient(), now=NOW, poll_succeeded=True
    )
    assert action == ACTION_COMPLETE


# ── Poll failure (Shunya unreachable) ────────────────────────────────────
def test_poll_failure_waits_when_recent():
    action, reason = decide_reconcile_action(
        job_status=None, processing_since=_recent(), now=NOW, poll_succeeded=False
    )
    assert action == ACTION_WAIT
    assert reason is None


def test_poll_failure_times_out_when_ancient():
    action, reason = decide_reconcile_action(
        job_status=None, processing_since=_ancient(), now=NOW, poll_succeeded=False
    )
    assert action == ACTION_FAIL
    assert "timed out" in reason.lower()


def test_no_processing_since_never_times_out_on_wait():
    # Missing timestamp shouldn't force a timeout; treat as still-waiting.
    action, _ = decide_reconcile_action(
        job_status="running", processing_since=None, now=NOW, poll_succeeded=True
    )
    assert action == ACTION_WAIT
