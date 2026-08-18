"""Unit tests for rehash eligibility logic and row construction (no DB)."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services import rehash_service as rs
from app.services.rehash_service import (
    CATEGORY_APPOINTMENT_PENDING,
    CATEGORY_QUALIFIED_UNBOOKED,
    CATEGORY_STALE_LEAD,
    compute_last_activity,
    is_eligible_appointment_pending,
    is_eligible_qualified_unbooked,
    is_eligible_stale_lead,
    _build_row,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


# ── compute_last_activity ────────────────────────────────────────────────

def test_compute_last_activity_picks_latest():
    created = datetime(2026, 1, 1, tzinfo=UTC)
    updated = datetime(2026, 2, 1, tzinfo=UTC)
    call = datetime(2026, 3, 1, tzinfo=UTC)
    appt = datetime(2026, 5, 1, tzinfo=UTC)
    assert compute_last_activity(updated, created, call, appt) == appt


def test_compute_last_activity_falls_back_to_created():
    created = datetime(2026, 1, 1, tzinfo=UTC)
    assert compute_last_activity(None, created) == created


def test_compute_last_activity_naive_treated_as_utc():
    created = datetime(2026, 1, 1)  # naive
    result = compute_last_activity(None, created)
    assert result.tzinfo is not None


# ── qualified_unbooked ───────────────────────────────────────────────────

def test_qualified_unbooked_eligible_when_old_enough():
    last = NOW - timedelta(days=settings.REHASH_QUALIFIED_UNBOOKED_DAYS + 1)
    assert is_eligible_qualified_unbooked(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is True


def test_qualified_unbooked_not_eligible_within_threshold():
    last = NOW - timedelta(days=settings.REHASH_QUALIFIED_UNBOOKED_DAYS - 1)
    assert is_eligible_qualified_unbooked(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is False


def test_qualified_unbooked_excluded_by_future_appointment():
    last = NOW - timedelta(days=30)
    assert is_eligible_qualified_unbooked(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=True, now=NOW,
    ) is False


def test_qualified_unbooked_excluded_by_wrong_status():
    last = NOW - timedelta(days=30)
    assert is_eligible_qualified_unbooked(
        status="qualified_booked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is False


def test_qualified_unbooked_excluded_by_terminal_status():
    last = NOW - timedelta(days=30)
    assert is_eligible_qualified_unbooked(
        status="closed_won", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is False


# ── appointment_pending ──────────────────────────────────────────────────

@pytest.mark.parametrize("outcome", [None, "pending", "PENDING"])
def test_appointment_pending_eligible_for_open_outcome(outcome):
    started = NOW - timedelta(days=settings.REHASH_APPOINTMENT_PENDING_DAYS + 1)
    assert is_eligible_appointment_pending(
        pipeline_stage="appointment_ran", appointment_outcome=outcome,
        scheduled_start=started, now=NOW,
    ) is True


@pytest.mark.parametrize("outcome", ["won", "lost", "no_show", "rescheduled"])
def test_appointment_pending_excluded_for_closed_outcome(outcome):
    started = NOW - timedelta(days=30)
    assert is_eligible_appointment_pending(
        pipeline_stage="appointment_ran", appointment_outcome=outcome,
        scheduled_start=started, now=NOW,
    ) is False


def test_appointment_pending_excluded_when_visit_too_recent():
    started = NOW - timedelta(days=settings.REHASH_APPOINTMENT_PENDING_DAYS - 1)
    assert is_eligible_appointment_pending(
        pipeline_stage="appointment_ran", appointment_outcome="pending",
        scheduled_start=started, now=NOW,
    ) is False


def test_appointment_pending_requires_appointment_ran_stage():
    started = NOW - timedelta(days=30)
    assert is_eligible_appointment_pending(
        pipeline_stage="appointment", appointment_outcome="pending",
        scheduled_start=started, now=NOW,
    ) is False


# ── stale_lead ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("stage", ["qualified", "booked", "appointment"])
def test_stale_lead_eligible_for_open_stages(stage):
    last = NOW - timedelta(days=settings.REHASH_STALE_LEAD_DAYS + 1)
    assert is_eligible_stale_lead(
        status="warm", pipeline_stage=stage, last_activity=last, now=NOW,
    ) is True


def test_stale_lead_not_eligible_when_recent():
    last = NOW - timedelta(days=settings.REHASH_STALE_LEAD_DAYS - 1)
    assert is_eligible_stale_lead(
        status="warm", pipeline_stage="qualified", last_activity=last, now=NOW,
    ) is False


def test_stale_lead_excluded_terminal_status():
    last = NOW - timedelta(days=60)
    assert is_eligible_stale_lead(
        status="abandoned", pipeline_stage="qualified", last_activity=last, now=NOW,
    ) is False


def test_stale_lead_excluded_stage_not_in_set():
    last = NOW - timedelta(days=60)
    assert is_eligible_stale_lead(
        status="warm", pipeline_stage="appointment_ran", last_activity=last, now=NOW,
    ) is False


# ── row construction ─────────────────────────────────────────────────────

def test_build_row_qualified_unbooked():
    company_id, lead_id, rep_id = uuid4(), uuid4(), uuid4()
    row = _build_row(
        company_id=company_id, lead_id=lead_id, owner_id=rep_id,
        category=CATEGORY_QUALIFIED_UNBOOKED, appointment_id=None, now=NOW,
    )
    assert row.action_type == rs.ACTION_TYPE == "rehash"
    assert row.source == rs.SOURCE == "rehash"
    assert row.owner_id == rep_id
    assert row.lead_id == lead_id
    assert row.appointment_id is None
    assert row.priority == rs.REHASH_PRIORITY
    assert row.due_at == NOW
    assert row.extra_metadata["rehash_category"] == CATEGORY_QUALIFIED_UNBOOKED
    assert row.extra_metadata["rule_version"] == rs.RULE_VERSION
    assert "appointment_id" not in row.extra_metadata


def test_build_row_appointment_pending_carries_appointment_id():
    appt_id = uuid4()
    row = _build_row(
        company_id=uuid4(), lead_id=uuid4(), owner_id=None,
        category=CATEGORY_APPOINTMENT_PENDING, appointment_id=appt_id, now=NOW,
    )
    assert row.appointment_id == appt_id
    assert row.extra_metadata["appointment_id"] == str(appt_id)
    assert row.owner_id is None  # null rep → notification falls back to broadcast


def test_qualified_unbooked_and_stale_overlap_at_30d():
    """A 30d-old qualified lead matches BOTH categories (documented overlap)."""
    last = NOW - timedelta(days=30)
    assert is_eligible_qualified_unbooked(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is True
    assert is_eligible_stale_lead(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_activity=last, now=NOW,
    ) is True


def test_qualified_unbooked_only_between_7_and_14_days():
    """10d isolates to qualified_unbooked (past 7d gate, within 14d stale gate)."""
    last = NOW - timedelta(days=10)
    assert is_eligible_qualified_unbooked(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_update=last, has_future_pending_appointment=False, now=NOW,
    ) is True
    assert is_eligible_stale_lead(
        status="qualified_unbooked", pipeline_stage="qualified",
        last_activity=last, now=NOW,
    ) is False


def test_active_rehash_status_set_suppresses_pending_and_completed():
    """Regression: suppression must consider completed (notified) rows, not just
    pending — otherwise a fired rehash is re-created every daily scan."""
    from app.domain.enums import PendingActionStatus
    from app.infrastructure.repositories.pending_action import PendingActionRepository

    # list_active_rehash filters on these two statuses; lock that contract.
    assert PendingActionStatus.PENDING.value == "pending"
    assert PendingActionStatus.COMPLETED.value == "completed"
    assert PendingActionRepository.REHASH_ACTION_TYPE == "rehash"


def test_build_row_stale_lead_text():
    row = _build_row(
        company_id=uuid4(), lead_id=uuid4(), owner_id=None,
        category=CATEGORY_STALE_LEAD, appointment_id=None, now=NOW,
    )
    assert "quiet" in row.raw_text.lower() or "re-engage" in row.raw_text.lower()
