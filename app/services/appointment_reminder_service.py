"""
Appointment reminder service.

Materializes up to three reminder rows (day-before, morning-of, one-hour-before)
as PendingAction records for each upcoming appointment. Delivery is handled by the
existing 1-minute follow-up notification job (see followup_notification_service.py).

No new tables, services, or event buses — reminders are plain pending_actions rows
with action_type/source == "appointment_reminder" and a reminder_kind in
extra_metadata.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.debug_runtime import emit_debug_log
from app.core.logging import get_logger
from app.domain.enums import PendingActionStatus
from app.domain.models.pending_action import PendingAction
from app.infrastructure.repositories.pending_action import PendingActionRepository

logger = get_logger(__name__)

UTC = ZoneInfo("UTC")

ACTION_TYPE = PendingActionRepository.APPOINTMENT_REMINDER_ACTION_TYPE  # "appointment_reminder"
SOURCE = PendingActionRepository.APPOINTMENT_REMINDER_SOURCE  # "appointment_reminder"

# Reminder kinds and their priorities (lower number used elsewhere = higher urgency)
KIND_DAY_BEFORE = "day_before"
KIND_MORNING_OF = "morning_of"
KIND_ONE_HOUR_BEFORE = "one_hour_before"

_PRIORITY = {
    KIND_DAY_BEFORE: 2,
    KIND_MORNING_OF: 2,
    KIND_ONE_HOUR_BEFORE: 1,
}

# Outcomes that keep reminders alive. Anything else cancels them.
_ELIGIBLE_OUTCOMES = {None, "", "pending", PendingActionStatus.PENDING.value}


@dataclass
class SyncResult:
    """Outcome of a sync_appointment_reminders call."""
    created: list[str] = field(default_factory=list)
    cancelled: int = 0
    skipped: bool = False
    reason: Optional[str] = None


def _to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    DB datetimes are stored TZ-aware UTC, but naive values are treated as UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def compute_reminder_due_times(
    scheduled_start: datetime,
    *,
    now_utc: Optional[datetime] = None,
) -> dict[str, Optional[datetime]]:
    """Compute UTC due_at for each reminder kind.

    Returns a dict mapping kind -> due_at (UTC, tz-aware) or None when that kind
    is not applicable (already in the past relative to now).

    - day_before: APPOINTMENT_DAY_BEFORE_REMINDER_HOUR local time on the calendar
      day before the appointment.
    - morning_of: APPOINTMENT_MORNING_REMINDER_HOUR local time on the appointment day.
    - one_hour_before: scheduled_start - 1 hour.
    """
    now_utc = _to_utc(now_utc) if now_utc else datetime.now(UTC)
    start_utc = _to_utc(scheduled_start)

    local_tz = ZoneInfo(settings.APPOINTMENT_REMINDER_TZ)
    start_local = start_utc.astimezone(local_tz)

    def _local_at(day_local_date, hour: int) -> datetime:
        local_dt = datetime(
            day_local_date.year,
            day_local_date.month,
            day_local_date.day,
            hour,
            0,
            0,
            tzinfo=local_tz,
        )
        return local_dt.astimezone(UTC)

    day_before_local_date = (start_local - timedelta(days=1)).date()
    due = {
        KIND_DAY_BEFORE: _local_at(
            day_before_local_date, settings.APPOINTMENT_DAY_BEFORE_REMINDER_HOUR
        ),
        KIND_MORNING_OF: _local_at(
            start_local.date(), settings.APPOINTMENT_MORNING_REMINDER_HOUR
        ),
        KIND_ONE_HOUR_BEFORE: start_utc - timedelta(hours=1),
    }

    # Drop any kind whose due_at is already in the past.
    return {kind: dt if dt > now_utc else None for kind, dt in due.items()}


def _get(appointment: Any, attr: str) -> Any:
    """Read an attribute from either a domain model or an ORM object."""
    return getattr(appointment, attr, None)


def _outcome_value(appointment: Any) -> Optional[str]:
    outcome = _get(appointment, "outcome")
    if outcome is None:
        return None
    return outcome.value if hasattr(outcome, "value") else str(outcome)


def _is_eligible(appointment: Any, now_utc: datetime) -> tuple[bool, Optional[str]]:
    """Return (eligible, reason_if_not)."""
    scheduled_start = _get(appointment, "scheduled_start")
    if scheduled_start is None:
        return False, "no_scheduled_start"
    if _to_utc(scheduled_start) <= now_utc:
        return False, "scheduled_start_in_past"
    if _outcome_value(appointment) not in _ELIGIBLE_OUTCOMES:
        return False, "outcome_not_pending"
    return True, None


def _build_reminder_row(
    appointment: Any,
    kind: str,
    due_at: datetime,
) -> PendingAction:
    """Build (but do not persist) a PendingAction reminder row."""
    scheduled_start = _to_utc(_get(appointment, "scheduled_start"))
    return PendingAction(
        company_id=_get(appointment, "company_id"),
        lead_id=_get(appointment, "lead_id"),
        appointment_id=_get(appointment, "id"),
        action_type=ACTION_TYPE,
        raw_text=_reminder_text(kind, scheduled_start),
        status=PendingActionStatus.PENDING,
        due_at=due_at,
        priority=_PRIORITY[kind],
        owner_id=_get(appointment, "assigned_rep_id"),
        source=SOURCE,
        extra_metadata={
            "reminder_kind": kind,
            "scheduled_start": scheduled_start.isoformat(),
        },
    )


def _reminder_text(kind: str, scheduled_start: datetime) -> str:
    local_tz = ZoneInfo(settings.APPOINTMENT_REMINDER_TZ)
    local = scheduled_start.astimezone(local_tz)
    time_str = local.strftime("%-I:%M %p") if _supports_dash_strftime() else local.strftime("%I:%M %p").lstrip("0")
    if kind == KIND_DAY_BEFORE:
        return f"Appointment tomorrow at {time_str}"
    if kind == KIND_MORNING_OF:
        return f"Appointment today at {time_str}"
    return "Appointment in 1 hour"


def _supports_dash_strftime() -> bool:
    """%-I is POSIX-only; fall back on Windows."""
    try:
        datetime.now().strftime("%-I")
        return True
    except ValueError:
        return False


async def sync_appointment_reminders(
    session: AsyncSession,
    appointment: Any,
) -> SyncResult:
    """Cancel stale reminders and (re)create reminders for an appointment.

    Idempotent: cancels all existing pending reminders for the appointment, then
    creates one row per applicable, still-future reminder kind. Safe to call on
    every appointment write. Caller owns the transaction/commit.
    """
    repo = PendingActionRepository(session)
    result = SyncResult()
    now_utc = datetime.now(UTC)

    appointment_id = _get(appointment, "id")
    if appointment_id is None:
        # #region agent log
        emit_debug_log(
            hypothesis_id="H1",
            location="appointment_reminder_service.py:200",
            message="Reminder sync skipped due to missing appointment id",
            data={},
        )
        # #endregion
        result.skipped = True
        result.reason = "no_appointment_id"
        return result

    # Always clear existing pending reminders first — handles reschedule and
    # outcome changes uniformly.
    result.cancelled = await repo.cancel_pending_appointment_reminders(appointment_id)

    eligible, reason = _is_eligible(appointment, now_utc)
    # #region agent log
    emit_debug_log(
        hypothesis_id="H1",
        location="appointment_reminder_service.py:211",
        message="Reminder eligibility evaluated",
        data={
            "appointmentId": str(appointment_id),
            "eligible": eligible,
            "reason": reason,
            "cancelledCount": result.cancelled,
            "scheduledStart": (
                _to_utc(_get(appointment, "scheduled_start")).isoformat()
                if _get(appointment, "scheduled_start")
                else None
            ),
            "outcome": _outcome_value(appointment),
        },
    )
    # #endregion
    if not eligible:
        result.skipped = True
        result.reason = reason
        return result

    due_times = compute_reminder_due_times(
        _get(appointment, "scheduled_start"), now_utc=now_utc
    )
    # #region agent log
    emit_debug_log(
        hypothesis_id="H2",
        location="appointment_reminder_service.py:225",
        message="Computed reminder due times",
        data={
            "appointmentId": str(appointment_id),
            "dueTimes": {k: (v.isoformat() if v else None) for k, v in due_times.items()},
            "timezone": settings.APPOINTMENT_REMINDER_TZ,
            "dayBeforeHour": settings.APPOINTMENT_DAY_BEFORE_REMINDER_HOUR,
            "morningHour": settings.APPOINTMENT_MORNING_REMINDER_HOUR,
        },
    )
    # #endregion
    for kind, due_at in due_times.items():
        if due_at is None:
            continue
        row = _build_reminder_row(appointment, kind, due_at)
        await repo.create(row)
        result.created.append(kind)

    logger.info(
        "Synced appointment reminders",
        appointment_id=str(appointment_id),
        created=result.created,
        cancelled=result.cancelled,
    )
    return result


async def cancel_appointment_reminders(
    session: AsyncSession,
    appointment_id: UUID,
) -> int:
    """Cancel all pending reminders for an appointment (e.g. on delete)."""
    repo = PendingActionRepository(session)
    cancelled = await repo.cancel_pending_appointment_reminders(appointment_id)
    if cancelled:
        logger.info(
            "Cancelled appointment reminders",
            appointment_id=str(appointment_id),
            cancelled=cancelled,
        )
    return cancelled
