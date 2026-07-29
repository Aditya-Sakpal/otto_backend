"""Unit tests for appointment reminder time math and eligibility.

Pure-logic tests (no DB) covering compute_reminder_due_times, eligibility, and
row construction.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.services import appointment_reminder_service as ars
from app.services.appointment_reminder_service import (
    KIND_DAY_BEFORE,
    KIND_MORNING_OF,
    KIND_ONE_HOUR_BEFORE,
    compute_reminder_due_times,
    _build_reminder_row,
    _is_eligible,
)

UTC = ZoneInfo("UTC")
LOCAL = ZoneInfo(settings.APPOINTMENT_REMINDER_TZ)


def _appt(scheduled_start, outcome="pending", assigned_rep_id=None):
    return SimpleNamespace(
        id=uuid4(),
        company_id=uuid4(),
        lead_id=uuid4(),
        contact_card_id=uuid4(),
        scheduled_start=scheduled_start,
        outcome=outcome,
        assigned_rep_id=assigned_rep_id,
        location_address="123 Main St",
    )


def test_due_times_all_three_for_appointment_more_than_a_day_out():
    # Appointment ~26h out, mid-afternoon local time → all three kinds future.
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    start_local = datetime(2026, 6, 2, 14, 0, tzinfo=LOCAL)
    start = start_local.astimezone(UTC)

    due = compute_reminder_due_times(start, now_utc=now)

    assert due[KIND_ONE_HOUR_BEFORE] == start - timedelta(hours=1)

    # day_before at configured hour, local day before appointment
    db_local = due[KIND_DAY_BEFORE].astimezone(LOCAL)
    assert db_local.hour == settings.APPOINTMENT_DAY_BEFORE_REMINDER_HOUR
    assert db_local.date() == (start_local - timedelta(days=1)).date()

    # morning_of at configured hour, on appointment local day
    mo_local = due[KIND_MORNING_OF].astimezone(LOCAL)
    assert mo_local.hour == settings.APPOINTMENT_MORNING_REMINDER_HOUR
    assert mo_local.date() == start_local.date()


def test_past_kinds_are_dropped():
    # "Now" is the morning of the appointment, after the morning-reminder hour,
    # so day_before and morning_of are already past → only one_hour_before survives.
    start_local = datetime(2026, 6, 2, 14, 0, tzinfo=LOCAL)
    start = start_local.astimezone(UTC)
    now_local = datetime(2026, 6, 2, 11, 0, tzinfo=LOCAL)  # after 8 AM, before 1pm
    now = now_local.astimezone(UTC)

    due = compute_reminder_due_times(start, now_utc=now)

    assert due[KIND_DAY_BEFORE] is None
    assert due[KIND_MORNING_OF] is None
    assert due[KIND_ONE_HOUR_BEFORE] is not None


def test_same_day_appointment_skips_day_before():
    start_local = datetime(2026, 6, 2, 23, 0, tzinfo=LOCAL)
    start = start_local.astimezone(UTC)
    now_local = datetime(2026, 6, 2, 7, 0, tzinfo=LOCAL)  # before morning hour
    now = now_local.astimezone(UTC)

    due = compute_reminder_due_times(start, now_utc=now)

    assert due[KIND_DAY_BEFORE] is None
    assert due[KIND_MORNING_OF] is not None
    assert due[KIND_ONE_HOUR_BEFORE] is not None


def test_due_times_stored_as_utc():
    start = datetime(2026, 6, 2, 18, 0, tzinfo=UTC)
    now = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    due = compute_reminder_due_times(start, now_utc=now)
    for dt in due.values():
        if dt is not None:
            assert dt.tzinfo is not None
            assert dt.utcoffset() == timedelta(0)


def test_dst_boundary_day_before_uses_local_hour():
    # US DST starts 2026-03-08. Appointment on 2026-03-09; day-before is 03-08.
    start_local = datetime(2026, 3, 9, 15, 0, tzinfo=LOCAL)
    start = start_local.astimezone(UTC)
    now = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    due = compute_reminder_due_times(start, now_utc=now)
    db_local = due[KIND_DAY_BEFORE].astimezone(LOCAL)
    assert db_local.hour == settings.APPOINTMENT_DAY_BEFORE_REMINDER_HOUR


def test_eligibility_rules():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    future = now + timedelta(days=1)
    past = now - timedelta(hours=1)

    assert _is_eligible(_appt(future, outcome="pending"), now)[0] is True
    assert _is_eligible(_appt(future, outcome=None), now)[0] is True
    assert _is_eligible(_appt(future, outcome="won"), now)[0] is False
    assert _is_eligible(_appt(future, outcome="rescheduled"), now)[0] is False
    assert _is_eligible(_appt(past, outcome="pending"), now)[0] is False


def test_build_reminder_row_sets_metadata_and_owner():
    rep_id = uuid4()
    start = datetime(2026, 6, 2, 18, 0, tzinfo=UTC)
    appt = _appt(start, assigned_rep_id=rep_id)
    due = start - timedelta(hours=1)

    row = _build_reminder_row(appt, KIND_ONE_HOUR_BEFORE, due)

    assert row.action_type == ars.ACTION_TYPE
    assert row.source == ars.SOURCE
    assert row.owner_id == rep_id
    assert row.appointment_id == appt.id
    assert row.due_at == due
    assert row.extra_metadata["reminder_kind"] == KIND_ONE_HOUR_BEFORE
    assert row.priority == 1  # one_hour_before is highest priority


def test_naive_scheduled_start_treated_as_utc():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    naive_start = datetime(2026, 6, 3, 18, 0)  # no tzinfo
    due = compute_reminder_due_times(naive_start, now_utc=now)
    assert due[KIND_ONE_HOUR_BEFORE] == naive_start.replace(tzinfo=UTC) - timedelta(hours=1)
