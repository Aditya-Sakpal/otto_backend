"""
Unit tests for the appointment data-quality helpers.

These encode the audit's decision rules for Pipeline → Appointments List View
issues #38 (impossible times) and #40 (generic state-only locations). Keeping
them green in CI prevents regressions when the helpers are touched later
(e.g., adjusting the business-hours window for a new tenant).
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from app.services.appointment_quality import (
    DEFAULT_BUSINESS_HOURS_END,
    DEFAULT_BUSINESS_HOURS_START,
    check_location_quality,
    check_time_quality,
    merge_quality_metadata,
)


# ── #38: time quality ────────────────────────────────────────────────────────


def test_business_hours_time_returns_none():
    # 14:30 UTC sits inside the default 06:00-21:00 window.
    dt = datetime(2026, 4, 16, 14, 30, tzinfo=timezone.utc)
    assert check_time_quality(dt) is None


def test_one_am_is_low_confidence():
    # The audit's flagship example: a 1 AM appointment must not pass silently.
    dt = datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)
    assert check_time_quality(dt) == "low_confidence"


@pytest.mark.parametrize("hour", [3, 4, 5])
def test_other_overnight_times_flagged(hour):
    dt = datetime(2026, 4, 16, hour, 0, tzinfo=timezone.utc)
    assert check_time_quality(dt) == "low_confidence"


def test_naive_datetime_is_treated_as_utc():
    # Codebase convention: naive timestamps default to UTC. The helper must
    # not blow up and should still apply the business-hours check.
    naive = datetime(2026, 4, 16, 2, 0)
    assert check_time_quality(naive) == "low_confidence"


def test_none_input_returns_none():
    assert check_time_quality(None) is None


def test_business_hours_window_boundaries():
    start_dt = datetime(2026, 4, 16, DEFAULT_BUSINESS_HOURS_START.hour, 0, tzinfo=timezone.utc)
    end_dt = datetime(
        2026,
        4,
        16,
        DEFAULT_BUSINESS_HOURS_END.hour,
        0,
        tzinfo=timezone.utc,
    )
    assert check_time_quality(start_dt) is None
    assert check_time_quality(end_dt) is None


def test_custom_business_hours_window():
    # Some trades may want a wider window; the helper accepts overrides.
    dt = datetime(2026, 4, 16, 5, 30, tzinfo=timezone.utc)
    assert (
        check_time_quality(dt, business_hours_start=time(5, 0)) is None
    )


# ── #40: location quality ────────────────────────────────────────────────────


def test_generic_state_only_address_is_low_quality():
    """Audit example: 'AZ, US' must NOT be returned as a usable address."""
    address, quality = check_location_quality(
        raw_address="AZ, US",
        structured_address=None,
    )
    assert address is None
    assert quality == "low"


def test_real_street_address_passes():
    address, quality = check_location_quality(
        raw_address="123 Main St, Phoenix, AZ 85001",
        structured_address=None,
    )
    assert address == "123 Main St, Phoenix, AZ 85001"
    assert quality == "ok"


def test_structured_address_with_line1_passes():
    address, quality = check_location_quality(
        raw_address=None,
        structured_address={
            "line1": "456 Cactus Rd",
            "city": "Tempe",
            "state": "AZ",
            "postal_code": "85281",
            "country": "US",
        },
    )
    assert address.startswith("456 Cactus Rd")
    assert "Tempe" in address
    assert quality == "ok"


def test_structured_address_without_line1_is_low_quality():
    address, quality = check_location_quality(
        raw_address=None,
        structured_address={
            "city": "Phoenix",
            "state": "AZ",
            "country": "US",
        },
    )
    assert address is None
    assert quality == "low"


def test_contact_card_fallback_with_real_address():
    address, quality = check_location_quality(
        raw_address=None,
        structured_address=None,
        contact_address_parts=("789 Oak Ave", "Mesa", "AZ", "85201"),
    )
    assert address.startswith("789 Oak Ave")
    assert quality == "ok"


def test_contact_card_fallback_state_only_is_low_quality():
    address, quality = check_location_quality(
        raw_address=None,
        structured_address=None,
        contact_address_parts=(None, None, "AZ", None),
    )
    assert address is None
    assert quality == "low"


def test_no_inputs_returns_low_quality():
    address, quality = check_location_quality(
        raw_address=None,
        structured_address=None,
        contact_address_parts=None,
    )
    assert address is None
    assert quality == "low"


def test_raw_address_preferred_over_structured_when_specific():
    address, quality = check_location_quality(
        raw_address="100 Elm St, Chandler, AZ",
        structured_address={"city": "Other City", "state": "TX", "country": "US"},
    )
    assert address.startswith("100 Elm St")
    assert quality == "ok"


# ── merge_quality_metadata ───────────────────────────────────────────────────


def test_merge_adds_flags():
    merged = merge_quality_metadata(
        {"created_from_call": "abc"},
        time_quality="low_confidence",
        location_quality="low",
    )
    assert merged == {
        "created_from_call": "abc",
        "time_quality": "low_confidence",
        "location_quality": "low",
    }


def test_merge_drops_flags_when_none():
    """Repeated ingests should not leave stale flags on a now-clean appointment."""
    existing = {
        "time_quality": "low_confidence",
        "location_quality": "low",
        "created_from_call": "abc",
    }
    merged = merge_quality_metadata(existing, time_quality=None, location_quality=None)
    assert merged == {"created_from_call": "abc"}


def test_merge_returns_none_for_empty_result():
    merged = merge_quality_metadata(None, time_quality=None, location_quality=None)
    assert merged is None


def test_merge_does_not_mutate_input():
    src = {"time_quality": "low_confidence"}
    merge_quality_metadata(src, time_quality=None, location_quality="low")
    assert src == {"time_quality": "low_confidence"}
