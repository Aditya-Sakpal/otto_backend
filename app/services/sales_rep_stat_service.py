"""
Sales rep stat service.

Provides GET /sales_rep/stat/{sales_rep_id} response with
personal stats and pending leads.
"""
from datetime import date
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.enums import UserRole
from app.domain.schemas.sales_rep import PendingLeadResultItem
from app.domain.schemas.sales_rep_stat import (
    PersonalStat,
    PendingLeadItem,
    SalesRepStatResponse,
)
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.user import UserORM
from app.services.lead_service import LeadService
from app.services.metrics_service import MetricsService

logger = get_logger(__name__)


class SalesRepStatService:
    """Service for sales rep stat endpoint."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.metrics_service = MetricsService(session)
        self.lead_service = LeadService(session)

    async def get_sales_rep_stat(
        self,
        sales_rep_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> SalesRepStatResponse:
        """
        Get sales rep stat: personal stats and pending leads.

        ``start_date`` / ``end_date`` align KPI metrics and the recordings count
        (calls with ``handled_by_user_id`` == rep in that UTC window).
        """
        from datetime import datetime, timezone, timedelta
        from app.infrastructure.database.models.appointment import AppointmentORM

        user_result = await self.session.execute(
            select(UserORM).where(UserORM.id == sales_rep_id)
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.company_id:
            raise ValueError("Sales rep not found or has no company")
        if user.role != UserRole.SALES_REP.value:
            raise ValueError("User is not a sales rep")

        company_id = user.company_id
        rep_name = f"{(user.first_name or '')} {(user.last_name or '')}".strip() or "Unknown"

        start_dt, end_dt = self.metrics_service._get_date_range(start_date, end_date)

        total_recordings_result = await self.session.execute(
            select(func.count(AppointmentORM.id)).where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.assigned_rep_id == sales_rep_id,
                AppointmentORM.scheduled_start >= _start_dt,
                AppointmentORM.scheduled_start <= _end_dt,
                AppointmentORM.audio_url.isnot(None),
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
            )
        )
        total_recordings = total_recordings_result.scalar() or 0

        kpi = await self.metrics_service.get_sales_rep_kpi(
            user_id=sales_rep_id,
            start_date=start_date,
            end_date=end_date,
        )

        tardiness = 0
        if user.extra_metadata and isinstance(user.extra_metadata, dict):
            tardiness = int(user.extra_metadata.get("avg_tardiness_min", 0) or 0)

        personal_stat = PersonalStat(
            total_recordings=total_recordings,
            win_rate=round(kpi.get("win_rate", 0) or 0, 2),
            win_rate_first_touch=round(kpi.get("first_touch_win_rate", 0) or 0, 2),
            win_rate_follow_ups=round(kpi.get("follow_up_win_rate", 0) or 0, 2),
            average_follow_up_per_lead=round(
                kpi.get("average_follow_up_per_deal", 0) or 0, 2
            ),
            average_follow_up_to_win=round(
                kpi.get("average_follow_up_per_deal", 0) or 0, 2
            ),
            attendance_rate=round(kpi.get("attendance", 0) or 0, 2),
            tardiness=tardiness,
            average_deal_size=round(kpi.get("average_deal_size", 0) or 0, 2),
        )

        pending_response = await self.lead_service.get_pending_leads(
            company_id=company_id,
            rep_id=sales_rep_id,
            status_filter="pending",
            limit=50,
            offset=0,
        )

        pending_lead = [
            self._to_pending_lead_item(item) for item in pending_response.results
        ]

        return SalesRepStatResponse(
            id=sales_rep_id,
            rep_name=rep_name,
            personal_stat=personal_stat,
            pending_lead=pending_lead,
        )

    def _to_pending_lead_item(self, item: PendingLeadResultItem) -> PendingLeadItem:
        """Transform PendingLeadResultItem to PendingLeadItem."""
        last_touched = None
        if item.sales_context.last_touched:
            lt = item.sales_context.last_touched
            last_touched = lt.strftime("%Y-%m-%d") if hasattr(lt, "strftime") else str(lt)

        date_of_appointment = None
        if item.appointment.scheduled_for:
            sf = item.appointment.scheduled_for
            date_of_appointment = (
                sf.strftime("%Y-%m-%d") if hasattr(sf, "strftime") else str(sf)
            )

        tasks = "; ".join(item.workflow.tasks) if item.workflow.tasks else ""
        recording = item.appointment.recording_url or ""

        return PendingLeadItem(
            lead_id=item.id,
            name=item.customer.full_name or "",
            looking_for=item.sales_context.intent or "",
            objection=item.sales_context.primary_objection or "",
            last_touched=last_touched,
            sales_rep=item.appointment.assigned_rep or "",
            address=item.customer.address or "",
            date_of_appointment=date_of_appointment,
            follow_up=item.sales_context.follow_up_count,
            tasks=tasks,
            appointment_recording=recording,
            summary=item.workflow.summary_notes or "",
        )
