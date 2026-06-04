"""Unit tests for missed-call recovery dashboard assembly (pure, no DB)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.missed_call_recovery_service import build_missed_call_dashboard

UTC = ZoneInfo("UTC")
TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 6, 1, 16, 0, tzinfo=UTC)  # noon EDT


def _row(status="pending", due_offset_min=10, updated_at=None, call=None):
    return SimpleNamespace(
        id=uuid4(), call_id=uuid4(), lead_id=uuid4(),
        raw_text="Give +15551230000 a call back", status=status,
        due_at=NOW + timedelta(minutes=due_offset_min),
        created_at=NOW - timedelta(minutes=5),
        updated_at=updated_at,
        call=call,
    )


def _dash(pending=None, completed=None, now=NOW):
    return build_missed_call_dashboard(
        company_id=uuid4(), owner_id=uuid4(),
        pending_rows=pending or [], completed_rows=completed or [],
        now_utc=now, tz=TZ,
    )


# ── Case 1: pending callback in pending section ──────────────────────────
def test_pending_appears_in_pending():
    d = _dash(pending=[_row(status="pending", due_offset_min=10)])
    assert len(d.pending_callbacks) == 1
    assert d.pending_count == 1
    it = d.pending_callbacks[0]
    assert it.minutes_until_due == 10
    assert it.urgency_tier == "due_now"
    assert it.overdue is False
    assert it.completed_at is None


# ── Case 2: completed callback in completed section ──────────────────────
def test_completed_appears_in_completed():
    upd = NOW - timedelta(minutes=30)
    d = _dash(completed=[_row(status="completed", updated_at=upd)])
    assert len(d.completed_callbacks) == 1
    it = d.completed_callbacks[0]
    assert it.completed_at == upd
    assert it.minutes_until_due is None   # countdown not shown for completed
    assert it.overdue is False


# ── Case 3: overdue callback increments overdue_count ────────────────────
def test_overdue_increments_count():
    d = _dash(pending=[
        _row(status="pending", due_offset_min=-20),  # overdue
        _row(status="pending", due_offset_min=10),    # not overdue
    ])
    assert d.overdue_count == 1
    overdue_items = [it for it in d.pending_callbacks if it.overdue]
    assert len(overdue_items) == 1
    assert overdue_items[0].minutes_until_due == -20


# ── Case 4: counts match underlying data ─────────────────────────────────
def test_counts_match():
    pending = [_row(due_offset_min=-5), _row(due_offset_min=5), _row(due_offset_min=100)]
    completed = [_row(status="completed", updated_at=NOW - timedelta(hours=1))]
    d = _dash(pending=pending, completed=completed)
    assert d.pending_count == 3 == len(d.pending_callbacks)
    assert d.overdue_count == 1
    assert len(d.completed_callbacks) == 1


# ── completed_today_count uses local calendar day ────────────────────────
def test_completed_today_count_local_day():
    today = _row(status="completed", updated_at=NOW - timedelta(hours=1))      # same EDT day
    yesterday = _row(status="completed", updated_at=NOW - timedelta(hours=20))  # prior EDT day
    d = _dash(completed=[today, yesterday])
    assert d.completed_today_count == 1


# ── Case 7: empty dashboard → valid response ─────────────────────────────
def test_empty_dashboard_valid():
    d = _dash()
    assert d.pending_callbacks == []
    assert d.completed_callbacks == []
    assert d.pending_count == 0
    assert d.overdue_count == 0
    assert d.completed_today_count == 0


# ── caller info reused from linked call's contact ────────────────────────
def test_source_call_populated_from_call():
    contact = SimpleNamespace(first_name="Jane", last_name="Doe", primary_phone="+15551230000")
    call = SimpleNamespace(id=uuid4(), contact_card=contact,
                           answered_at=None, created_at=NOW - timedelta(minutes=10))
    d = _dash(pending=[_row(call=call)])
    sc = d.pending_callbacks[0].source_call
    assert sc is not None
    assert sc.customer_name == "Jane Doe"
    assert sc.customer_phone == "+15551230000"


# ── Issue 2: unassigned (owner_id IS NULL) section ───────────────────────

def _dash_u(pending=None, unassigned=None):
    from app.services.missed_call_recovery_service import build_missed_call_dashboard
    return build_missed_call_dashboard(
        company_id=uuid4(), owner_id=uuid4(),
        pending_rows=pending or [], completed_rows=[], unassigned_rows=unassigned or [],
        now_utc=NOW, tz=TZ,
    )


def test_unassigned_section_populated():
    d = _dash_u(unassigned=[_row(due_offset_min=10), _row(due_offset_min=-20)])
    assert len(d.unassigned_callbacks) == 2
    assert d.unassigned_count == 2
    assert d.unassigned_overdue_count == 1  # one is overdue


def test_assigned_and_unassigned_counts_separate():
    # Assigned counts must NOT include unassigned (meaning preserved).
    d = _dash_u(pending=[_row(due_offset_min=5)], unassigned=[_row(due_offset_min=-30)])
    assert d.pending_count == 1
    assert d.overdue_count == 0           # the assigned one is not overdue
    assert d.unassigned_count == 1
    assert d.unassigned_overdue_count == 1


def test_no_unassigned_when_none():
    d = _dash_u(pending=[_row()])
    assert d.unassigned_callbacks == []
    assert d.unassigned_count == 0
    assert d.unassigned_overdue_count == 0
