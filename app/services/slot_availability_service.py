"""Compute bookable appointment slots from tenant business hours."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.schemas.tenant_config import BusinessHours, DaySchedule
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.tenant_config import TenantConfigORM
from app.services.tenant_config_service import TenantConfigService

logger = get_logger(__name__)

_DEFAULT_HOURS = BusinessHours()
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=hour, minute=minute)


class SlotAvailabilityService:
    """Generate candidate inspection slots minus existing appointments."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._tenant_svc = TenantConfigService(session)

    async def _load_business_hours(self, company_id: UUID) -> BusinessHours:
        cfg = await self._tenant_svc.get_config_by_company(company_id)
        if cfg and cfg.business_hours:
            try:
                return BusinessHours.model_validate(cfg.business_hours)
            except Exception:
                logger.warning("Invalid business_hours JSON for company", company_id=str(company_id))
        return _DEFAULT_HOURS

    async def get_slots(
        self,
        company_id: UUID,
        target_date: date,
        *,
        assigned_rep_id: Optional[UUID] = None,
        slot_minutes: int = 60,
    ) -> list[str]:
        bh = await self._load_business_hours(company_id)
        tz = ZoneInfo(bh.timezone or "America/Phoenix")
        weekday = _WEEKDAYS[target_date.weekday()]
        day: Optional[DaySchedule] = getattr(bh, weekday, None)
        if not day or day.is_closed:
            return []

        open_t = _parse_hhmm(day.open)
        close_t = _parse_hhmm(day.close)
        start_local = datetime.combine(target_date, open_t, tzinfo=tz)
        end_local = datetime.combine(target_date, close_t, tzinfo=tz)
        if end_local <= start_local:
            return []

        candidates: list[datetime] = []
        cursor = start_local
        delta = timedelta(minutes=slot_minutes)
        while cursor + delta <= end_local:
            candidates.append(cursor.astimezone(timezone.utc))
            cursor += delta

        if not candidates:
            return []

        day_start_utc = start_local.astimezone(timezone.utc)
        day_end_utc = end_local.astimezone(timezone.utc)
        q = select(AppointmentORM).where(
            AppointmentORM.company_id == company_id,
            AppointmentORM.scheduled_start >= day_start_utc,
            AppointmentORM.scheduled_start < day_end_utc,
        )
        if assigned_rep_id:
            q = q.where(AppointmentORM.assigned_rep_id == assigned_rep_id)
        result = await self.session.execute(q)
        booked = result.scalars().all()

        def _overlaps(slot_start: datetime) -> bool:
            slot_end = slot_start + delta
            for appt in booked:
                appt_start = appt.scheduled_start
                if appt_start.tzinfo is None:
                    appt_start = appt_start.replace(tzinfo=timezone.utc)
                appt_end = appt.scheduled_end or (appt_start + delta)
                if appt_end.tzinfo is None:
                    appt_end = appt_end.replace(tzinfo=timezone.utc)
                if slot_start < appt_end and slot_end > appt_start:
                    return True
            return False

        free = [s.isoformat() for s in candidates if not _overlaps(s)]
        return free

    async def company_timezone(self, company_id: UUID) -> str:
        bh = await self._load_business_hours(company_id)
        return bh.timezone or "America/Phoenix"
