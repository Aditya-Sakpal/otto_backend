"""Unit tests for recording-analysis lifecycle state derivation (no DB)."""
import pytest

from app.routes.v1.recordings import (
    RECORDING_STATE_COMPLETED,
    RECORDING_STATE_FAILED,
    RECORDING_STATE_NONE,
    RECORDING_STATE_PROCESSING,
    RECORDING_STATE_UPLOADED,
    derive_recording_state,
    failure_reason_for,
)


# ── derive_recording_state ───────────────────────────────────────────────

@pytest.mark.parametrize("recording_status,analysis_status,expected", [
    # analysis_status is authoritative once set
    (None, "completed", RECORDING_STATE_COMPLETED),
    ("uploaded", "completed", RECORDING_STATE_COMPLETED),
    (None, "failed", RECORDING_STATE_FAILED),
    ("uploaded", "failed", RECORDING_STATE_FAILED),
    (None, "processing", RECORDING_STATE_PROCESSING),
    ("uploaded", "processing", RECORDING_STATE_PROCESSING),
    # pre-analysis window driven by recording_status
    ("uploaded", None, RECORDING_STATE_UPLOADED),
    ("completed", None, RECORDING_STATE_UPLOADED),
    # nothing yet
    (None, None, RECORDING_STATE_NONE),
    ("", "", RECORDING_STATE_NONE),
    # unknown junk collapses safely
    ("weird", "unknown", RECORDING_STATE_NONE),
])
def test_derive_recording_state(recording_status, analysis_status, expected):
    assert derive_recording_state(recording_status, analysis_status) == expected


def test_derive_is_case_insensitive():
    assert derive_recording_state("UPLOADED", "PROCESSING") == RECORDING_STATE_PROCESSING
    assert derive_recording_state(None, "Completed") == RECORDING_STATE_COMPLETED


# ── failure_reason_for ───────────────────────────────────────────────────

def test_failed_has_generic_reason():
    reason = failure_reason_for(RECORDING_STATE_FAILED, None)
    assert reason and "failed" in reason.lower()


def test_uploaded_explains_analysis_not_started():
    reason = failure_reason_for(RECORDING_STATE_UPLOADED, None)
    assert reason and "analysis" in reason.lower()


@pytest.mark.parametrize("state", [
    RECORDING_STATE_COMPLETED, RECORDING_STATE_PROCESSING, RECORDING_STATE_NONE,
])
def test_healthy_states_have_no_reason(state):
    assert failure_reason_for(state, None) is None


def test_explicit_error_from_metadata_preferred_for_failed():
    meta = {"analysis_error": "Shunya timeout after 3 retries"}
    assert failure_reason_for(RECORDING_STATE_FAILED, meta) == "Shunya timeout after 3 retries"


def test_explicit_error_ignored_for_healthy_state():
    meta = {"analysis_error": "stale error"}
    assert failure_reason_for(RECORDING_STATE_COMPLETED, meta) is None
