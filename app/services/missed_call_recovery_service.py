"""
Rep missed-call recovery dashboard service.

Composes a rep-scoped view over `call_back` PendingActions (the tasks auto-created
when a VoIP missed call is detected). Reuses the Action Center countdown
(`compute_urgency_tier`) and `_build_source_call` (caller name/phone). No new
tables, schedulers, AI, metrics systems, or migrations — completion time is the
existing `pending_actions.updated_at`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import PendingActionStatus
from app.domain.schemas.sales_rep import MissedCallItem, MissedCallRecoveryResponse
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.call import CallORM
from app.services.pending_action_service import compute_urgency_tier, _build_source_call

logger = get_logger(__name__)

UTC = ZoneInfo("UTC")
CALL_BACK_TYPE = "call_back"
_PENDING_STATUSES = (PendingActionStatus.PENDING.value, PendingActionStatus.IN_PROGRESS.value)


def _build_item(row: PendingActionORM, now_utc: datetime, tz: ZoneInfo, completed: bool) -> MissedCallItem:
    """Map a call_back ORM row to a MissedCallItem (reuses countdown + source call)."""
    tier, minutes_until_due = compute_urgency_tier(row.due_at, now_utc, tz)
    return MissedCallItem(
        pending_action_id=row.id,
        call_id=row.call_id,
        lead_id=row.lead_id,
        raw_text=row.raw_text,
        status=row.status,
        due_at=row.due_at,
        created_at=row.created_at,
        completed_at=row.updated_at if completed else None,
        minutes_until_due=None if completed else minutes_until_due,
        urgency_tier=None if completed else tier,
        overdue=(not completed) and minutes_until_due is not None and minutes_until_due < 0,
        source_call=_build_source_call(getattr(row, "call", None)),
    )


def build_missed_call_dashboard(
    *,
    company_id: UUID,
    owner_id: UUID,
    pending_rows: list[PendingActionORM],
    completed_rows: list[PendingActionORM],
    now_utc: datetime,
    tz: ZoneInfo,
    unassigned_rows: list[PendingActionORM] | None = None,
) -> MissedCallRecoveryResponse:
    """Assemble the dashboard from pre-fetched rows (pure; unit-testable).

    `pending_rows`/`completed_rows` are the owner's own callbacks. `unassigned_rows`
    are company-wide callbacks with no owner (true missed calls) — surfaced as a
    separate, claimable triage section. Assigned counts stay owner-only.
    """
    unassigned_rows = unassigned_rows or []
    pending = [_build_item(r, now_utc, tz, completed=False) for r in pending_rows]
    completed = [_build_item(r, now_utc, tz, completed=True) for r in completed_rows]
    unassigned = [_build_item(r, now_utc, tz, completed=False) for r in unassigned_rows]

    overdue_count = sum(1 for it in pending if it.overdue)
    unassigned_overdue_count = sum(1 for it in unassigned if it.overdue)
    today_local = now_utc.astimezone(tz).date()
    completed_today_count = sum(
        1 for r in completed_rows
        if r.updated_at and r.updated_at.astimezone(tz).date() == today_local
    )

    # pending_count and overdue_count cover ALL pending callbacks surfaced in
    # the response (owner-assigned + unassigned) so that summary counts always
    # reconcile with the returned callback records.
    total_pending_count = len(pending) + len(unassigned)
    total_overdue_count = overdue_count + unassigned_overdue_count

    return MissedCallRecoveryResponse(
        generated_at=now_utc,
        company_id=company_id,
        owner_id=owner_id,
        pending_callbacks=pending,
        completed_callbacks=completed,
        unassigned_callbacks=unassigned,
        pending_count=total_pending_count,
        overdue_count=total_overdue_count,
        completed_today_count=completed_today_count,
        unassigned_count=len(unassigned),
        unassigned_overdue_count=unassigned_overdue_count,
    )


class MissedCallRecoveryService:
    """Builds the rep missed-call recovery dashboard from existing call_back tasks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _fetch(self, company_id: UUID, owner_id: UUID, statuses, limit: int,
                     since: Optional[datetime] = None) -> list[PendingActionORM]:
        filters = [
            PendingActionORM.company_id == company_id,
            PendingActionORM.owner_id == owner_id,
            PendingActionORM.action_type == CALL_BACK_TYPE,
            PendingActionORM.status.in_(statuses),
        ]
        if since is not None:
            filters.append(PendingActionORM.updated_at >= since)
        query = (
            select(PendingActionORM)
            .options(selectinload(PendingActionORM.call).selectinload(CallORM.contact_card))
            .where(and_(*filters))
            .order_by(PendingActionORM.due_at.asc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _fetch_unassigned(self, company_id: UUID, statuses, limit: int) -> list[PendingActionORM]:
        """Company-wide call_back tasks with NO owner (true missed calls).

        Tenant-scoped by company_id only; never returns another rep's owned tasks
        (owner_id IS NULL). Mirrors the existing notification broadcast for
        null-owner callbacks, surfaced for query/triage.
        """
        query = (
            select(PendingActionORM)
            .options(selectinload(PendingActionORM.call).selectinload(CallORM.contact_card))
            .where(
                and_(
                    PendingActionORM.company_id == company_id,
                    PendingActionORM.owner_id.is_(None),
                    PendingActionORM.action_type == CALL_BACK_TYPE,
                    PendingActionORM.status.in_(statuses),
                )
            )
            .order_by(PendingActionORM.due_at.asc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_missed_call_dashboard(
        self,
        *,
        company_id: UUID,
        owner_id: UUID,
        limit: int = 100,
        completed_window_hours: int = 24,
    ) -> MissedCallRecoveryResponse:
        now_utc = datetime.now(UTC)
        try:
            tz = ZoneInfo(settings.APPOINTMENT_REMINDER_TZ)
        except Exception:
            tz = ZoneInfo("America/New_York")

        pending_rows = await self._fetch(company_id, owner_id, _PENDING_STATUSES, limit)
        completed_rows = await self._fetch(
            company_id, owner_id, (PendingActionStatus.COMPLETED.value,), limit,
            since=now_utc - timedelta(hours=completed_window_hours),
        )
        unassigned_rows = await self._fetch_unassigned(company_id, _PENDING_STATUSES, limit)

        return build_missed_call_dashboard(
            company_id=company_id,
            owner_id=owner_id,
            pending_rows=pending_rows,
            completed_rows=completed_rows,
            unassigned_rows=unassigned_rows,
            now_utc=now_utc,
            tz=tz,
        )
