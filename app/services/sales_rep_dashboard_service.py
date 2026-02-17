"""
Sales rep dashboard service.

Provides business logic for /sales_rep/dashboard endpoints:
- Main dashboard with ridealongs_list and sales_team_stats
- Filtered ridealongs list
- Sales team stats with pagination
"""
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.enums import AppointmentOutcome
from app.domain.schemas.sales_rep_dashboard import (
    RidealongEntry,
    SalesTeamStatsEntry,
    SalesRepDashboardResponse,
    ObjectionEntry,
    CallLogEntry,
    MostCoachingNeedEntry,
    SalesOverview,
    CoreKpis,
    Trends,
    CloseRatePoint,
    SalesIncrease,
    TeamCoachingMetrics,
    OttoAssistedSales,
    AttendanceMetrics,
)
from app.services.analytics_service import AnalyticsService
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.domain.users.repository import UserRepository
from app.services.metrics_service import MetricsService

logger = get_logger(__name__)

OUTCOME_TO_STATUS = {
    "pending": "In Progress",
    None: "In Progress",
    "won": "Won",
    "lost": "Lost",
    "no_show": "No Show",
    "rescheduled": "Rescheduled",
}


def _format_time(dt: Optional[datetime]) -> str:
    """Format datetime to time string like 9:00AM."""
    if not dt:
        return ""
    try:
        return dt.strftime("%-I:%M%p")
    except ValueError:
        h, m = dt.hour, dt.minute
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d}{ampm}"


def _format_time_with_space(dt: Optional[datetime]) -> str:
    """Format datetime to time string like 8:55 AM."""
    if not dt:
        return ""
    try:
        return dt.strftime("%-I:%M %p")
    except ValueError:
        h, m = dt.hour, dt.minute
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {ampm}"


class SalesRepDashboardService:
    """Service for sales rep dashboard operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.appointment_repo = AppointmentRepository(session)
        self.contact_repo = ContactRepository(session)
        self.user_repo = UserRepository(session)
        self.metrics_service = MetricsService(session)

    async def _enrich_ridealong(
        self,
        appointment: Any,
        contact_name: str,
        rep_name: str,
        ghost_mode: bool,
    ) -> RidealongEntry:
        """Build RidealongEntry from appointment and enriched data."""
        outcome = getattr(appointment, "outcome", None)
        if isinstance(outcome, AppointmentOutcome):
            outcome = outcome.value if outcome else None
        status = OUTCOME_TO_STATUS.get(outcome, "In Progress")

        scheduled_start = getattr(appointment, "scheduled_start", None)
        scheduled_time = _format_time(scheduled_start) if scheduled_start else ""

        extra = getattr(appointment, "extra_metadata", None) or {}
        arrival_time = extra.get("arrival_time") or extra.get("arrival")
        if not arrival_time and scheduled_start:
            arrival_time = _format_time_with_space(scheduled_start)
        if isinstance(arrival_time, datetime):
            arrival_time = _format_time_with_space(arrival_time)

        service_type = extra.get("service_type") or extra.get("service_type_description") or "Appointment"

        appointment_id = getattr(appointment, "id", None)
        return RidealongEntry(
            appointment_id=appointment_id,
            customer_name=contact_name,
            sales_rep=rep_name,
            service_type=str(service_type),
            scheduled_time=scheduled_time or "",
            arrival_time=arrival_time or "",
            status=status,
            ghost_mode="True" if ghost_mode else "False",
        )

    async def get_dashboard(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> SalesRepDashboardResponse:
        """
        Get main dashboard: ridealongs_list (up to 9 today) and sales_team_stats (up to 3).
        Also includes objections in the same format as /metrics/objections/top.
        """
        today = date.today()

        appointments = await self.appointment_repo.get_ridealongs_filtered(
            company_id=company_id,
            start_date=today,
            end_date=today,
            skip=0,
            limit=9,
            order_desc=True,
        )

        ridealongs: List[RidealongEntry] = []
        for apt in appointments:
            contact_name = ""
            if apt.contact_card_id:
                contact = await self.contact_repo.get_by_id(apt.contact_card_id)
                if contact:
                    first = contact.first_name or ""
                    last = contact.last_name or ""
                    contact_name = f"{first} {last}".strip() or "Unknown"

            rep_name = ""
            ghost_mode = False
            if apt.assigned_rep_id:
                user = await self.user_repo.get_by_id(apt.assigned_rep_id)
                if user:
                    first = user.first_name or ""
                    last = user.last_name or ""
                    rep_name = f"{first} {last}".strip() or "Unknown"
                    extra = user.extra_metadata or {}
                    ghost_mode = extra.get("ghost_mode_active", False) is True

            entry = await self._enrich_ridealong(
                appointment=apt,
                contact_name=contact_name,
                rep_name=rep_name,
                ghost_mode=ghost_mode,
            )
            ridealongs.append(entry)

        sales_team_stats = await self._get_sales_team_stats(company_id, skip=0, limit=3)

        # Get objections in the same format as /metrics/objections/top
        objections = await self._get_objections(company_id, start_date=start_date, end_date=end_date, limit=10)
        sales_overview = await self._get_sales_overview(company_id)
        team_coaching_metrics = await self._get_team_coaching_metrics(
            company_id, objections, sales_team_stats
        )

        return SalesRepDashboardResponse(
            ridealongs_list=ridealongs,
            sales_team_stats=sales_team_stats,
            objections=objections,
            sales_overview=sales_overview,
            team_coaching_metrics=team_coaching_metrics,
        )

    async def get_ridealongs_list(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        ghost_mode: Optional[bool] = None,
        sales_rep_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RidealongEntry]:
        """
        Get ridealongs with filters.
        """
        appointments = await self.appointment_repo.get_ridealongs_filtered(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            ghost_mode=ghost_mode,
            sales_rep_name=sales_rep_name,
            skip=skip,
            limit=limit,
            order_desc=True,
        )

        ridealongs: List[RidealongEntry] = []
        for apt in appointments:
            contact_name = ""
            if apt.contact_card_id:
                contact = await self.contact_repo.get_by_id(apt.contact_card_id)
                if contact:
                    first = contact.first_name or ""
                    last = contact.last_name or ""
                    contact_name = f"{first} {last}".strip() or "Unknown"

            rep_name = ""
            ghost_mode = False
            if apt.assigned_rep_id:
                user = await self.user_repo.get_by_id(apt.assigned_rep_id)
                if user:
                    first = user.first_name or ""
                    last = user.last_name or ""
                    rep_name = f"{first} {last}".strip() or "Unknown"
                    extra = user.extra_metadata or {}
                    ghost_mode = extra.get("ghost_mode_active", False) is True

            entry = await self._enrich_ridealong(
                appointment=apt,
                contact_name=contact_name,
                rep_name=rep_name,
                ghost_mode=ghost_mode,
            )
            ridealongs.append(entry)

        return ridealongs

    async def _get_sales_team_stats(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[SalesTeamStatsEntry]:
        """
        Get sales team stats: rep_name, total_recordings_hours, win_rate,
        process_score, skills_score, otto_usage_hours.
        """
        from app.domain.enums import UserRole

        sales_reps = await self.user_repo.get_by_role(
            role=UserRole.SALES_REP,
            company_id=company_id,
            skip=0,
            limit=500,
        )

        if not sales_reps:
            return []

        rep_ids = [r.id for r in sales_reps]
        rep_names = {r.id: f"{(r.first_name or '')} {(r.last_name or '')}".strip() or "Unknown" for r in sales_reps}

        total_duration_result = await self.session.execute(
            select(
                CallORM.handled_by_user_id,
                func.coalesce(func.sum(CallORM.duration_seconds), 0).label("total_sec"),
            )
            .where(
                CallORM.company_id == company_id,
                CallORM.handled_by_user_id.in_(rep_ids),
                CallORM.duration_seconds.isnot(None),
            )
            .group_by(CallORM.handled_by_user_id)
        )
        duration_map = {r[0]: r[1] for r in total_duration_result.all()}

        won_result = await self.session.execute(
            select(
                AppointmentORM.assigned_rep_id,
                func.count(AppointmentORM.id).label("cnt"),
            )
            .where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.assigned_rep_id.in_(rep_ids),
                AppointmentORM.outcome == "won",
            )
            .group_by(AppointmentORM.assigned_rep_id)
        )
        won_map = {r[0]: r[1] for r in won_result.all()}

        resolved_result = await self.session.execute(
            select(
                AppointmentORM.assigned_rep_id,
                func.count(AppointmentORM.id).label("cnt"),
            )
            .where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.assigned_rep_id.in_(rep_ids),
                AppointmentORM.outcome.in_(["won", "lost", "no_show"]),
            )
            .group_by(AppointmentORM.assigned_rep_id)
        )
        resolved_map = {r[0]: r[1] for r in resolved_result.all()}

        process_result = await self.session.execute(
            select(
                CallORM.handled_by_user_id,
                func.avg(CallAnalysisORM.sop_compliance_score).label("avg_sop"),
            )
            .select_from(CallORM)
            .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
            .where(
                CallORM.company_id == company_id,
                CallORM.handled_by_user_id.in_(rep_ids),
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
            .group_by(CallORM.handled_by_user_id)
        )
        process_map = {r[0]: r[1] for r in process_result.all()}

        entries: List[SalesTeamStatsEntry] = []
        for rep in sales_reps:
            rep_id = rep.id
            total_sec = duration_map.get(rep_id, 0) or 0
            total_hours = round(total_sec / 3600.0, 2)

            won = won_map.get(rep_id, 0) or 0
            resolved = resolved_map.get(rep_id, 0) or 0
            win_rate = round((won / resolved * 100.0) if resolved > 0 else 0.0, 2)

            avg_sop = process_map.get(rep_id)
            process_score = round(float(avg_sop * 10), 2) if avg_sop is not None else 0.0

            skills_score = process_score
            otto_usage_hours = 0.0

            entries.append(
                SalesTeamStatsEntry(
                    sales_rep_id=rep_id,
                    rep_name=rep_names.get(rep_id, "Unknown"),
                    total_recordings_hours=total_hours,
                    win_rate=win_rate,
                    process_score=process_score,
                    skills_score=skills_score,
                    otto_usage_hours=otto_usage_hours,
                )
            )

        entries.sort(key=lambda e: e.win_rate, reverse=True)
        return entries[skip : skip + limit]

    async def _get_objections(
        self, company_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None, limit: int = 10
    ) -> List[ObjectionEntry]:
        """Get top objections with call_logs matching /metrics/objections/top format."""
        try:
            analytics_service = AnalyticsService(self.session)
            result = await analytics_service.get_top_objections(
                company_id=company_id,
                user_id=None,  # Company-wide
                start_date=start_date,
                end_date=end_date,
            )
            objections_data = result.get("objections") or []
            
            # Convert to ObjectionEntry format
            objections = []
            for obj_data in objections_data[:limit]:
                call_logs = []
                for call_log_data in obj_data.get("call_logs", []):
                    call_logs.append(CallLogEntry(
                        call_id=call_log_data.get("call_id", ""),
                        lead_id=call_log_data.get("lead_id"),
                        contact_name=call_log_data.get("contact_name", "Unknown"),
                        phone_number=call_log_data.get("phone_number", ""),
                        audio_url=call_log_data.get("audio_url"),
                        call_type=call_log_data.get("call_type"),
                        duration_seconds=call_log_data.get("duration_seconds"),
                        created_at=call_log_data.get("created_at"),
                        qualification_status=call_log_data.get("qualification_status"),
                        booking_status=call_log_data.get("booking_status"),
                        transcript=call_log_data.get("transcript"),
                        summary=call_log_data.get("summary"),
                    ))
                
                # Convert most_coaching_needs to most_coaching_need format
                # get_top_objections returns "most_coaching_needs" (plural) per objection
                most_coaching_need = []
                most_coaching_needs_data = obj_data.get("most_coaching_needs", [])
                for mcn_data in most_coaching_needs_data:
                    # Handle both formats: user_id/user_name (from get_top_objections) or csr_id/csr_name (from get_calls_by_objection_self)
                    user_id = mcn_data.get("user_id") or mcn_data.get("csr_id")
                    user_name = mcn_data.get("user_name") or mcn_data.get("csr_name", "Unknown")
                    unbooked_count = mcn_data.get("unbooked_count", 0) or mcn_data.get("unbooked_calls", 0)
                    
                    if user_id:  # Only add if we have a user_id
                        most_coaching_need.append(MostCoachingNeedEntry(
                            csr_id=str(user_id),
                            csr_name=user_name,
                            unbooked_calls=unbooked_count,
                        ))
                
                objections.append(ObjectionEntry(
                    objection_type=obj_data.get("objection_type", ""),
                    count=obj_data.get("count", 0),
                    affected_leads_count=obj_data.get("affected_leads_count", 0),
                    call_logs=call_logs,
                    most_coaching_need=most_coaching_need,
                ))
            
            return objections
        except Exception as e:
            logger.warning(f"Could not load objections: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _format_duration_as_hm(self, total_seconds: float) -> str:
        """Format seconds as e.g. 1h45m."""
        if total_seconds <= 0:
            return "0m"
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        if h > 0 and m > 0:
            return f"{h}h{m}m"
        if h > 0:
            return f"{h}h"
        return f"{m}m"

    async def _get_sales_overview(self, company_id: UUID) -> Optional[SalesOverview]:
        """Build sales_overview from company overview and sales rep KPIs."""
        try:
            overview = await self.metrics_service.get_company_overview(
                company_id=company_id,
            )
            kpi = await self.metrics_service.get_sales_rep_kpi(company_id=company_id)

            revenue = float(overview.get("total_revenue", 0) or 0)
            total_calls = int(overview.get("total_calls", 0) or 0)
            avg_deal_size = float(kpi.get("average_deal_size", 0) or 0)
            team_win_rate = float(kpi.get("win_rate", 0) or 0)
            first_touch_win_rate = float(kpi.get("first_touch_win_rate", 0) or 0)
            follow_up_win_rate = float(kpi.get("follow_up_win_rate", 0) or 0)

            avg_sec = 0.0
            if total_calls > 0:
                dur = await self.session.execute(
                    select(func.avg(CallORM.duration_seconds)).where(
                        CallORM.company_id == company_id,
                        CallORM.duration_seconds.isnot(None),
                    )
                )
                avg_sec = float(dur.scalar() or 0)
            avg_recording_duration = self._format_duration_as_hm(avg_sec)

            core_kpis = CoreKpis(
                revenue=round(revenue, 2),
                avg_deal_size=round(avg_deal_size, 2),
                total_conversations=total_calls,
                avg_recording_duration=avg_recording_duration,
                team_win_rate=round(team_win_rate, 2),
                first_touch_win_rate=round(first_touch_win_rate, 2),
                follow_up_win_rate=round(follow_up_win_rate, 2),
                follow_up_rate=0.0,
                follow_up_growth_percent=0.0,
            )

            trends = Trends(
                close_rate_series=[],
                sales_increase=None,
            )
            return SalesOverview(core_kpis=core_kpis, trends=trends)
        except Exception as e:
            logger.warning(f"Could not load sales_overview: {e}")
            return None

    async def _get_team_coaching_metrics(
        self,
        company_id: UUID,
        objections: List[ObjectionEntry],
        sales_team_stats: List[SalesTeamStatsEntry],
    ) -> Optional[TeamCoachingMetrics]:
        """Build team_coaching_metrics from objections, SOP, Otto usage, attendance."""
        try:
            # Calculate common_objection_peak from objections count
            common_objection_peak = 0.0
            if objections:
                # Get the objection with the highest count
                max_count = max((o.count for o in objections), default=0)
                if max_count > 0:
                    # Calculate percentage (simplified - could be improved with total)
                    total_count = sum(o.count for o in objections)
                    if total_count > 0:
                        common_objection_peak = round((max_count / total_count) * 100, 2)

            script_adherence = 0.0
            avg_sop = await self.session.execute(
                select(func.avg(CallAnalysisORM.sop_compliance_score)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                ).join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            )
            sop_val = avg_sop.scalar()
            if sop_val is not None:
                script_adherence = round(float(sop_val) * 10, 2)
                if script_adherence > 100:
                    script_adherence = 100.0

            ask_otto_usage_hours = sum(s.otto_usage_hours for s in sales_team_stats)

            kpi = await self.metrics_service.get_sales_rep_kpi(company_id=company_id)
            attendance_rate = float(kpi.get("attendance", 0) or 0)

            avg_tardiness_min = 0
            from app.domain.enums import UserRole
            sales_reps = await self.user_repo.get_by_role(
                role=UserRole.SALES_REP,
                company_id=company_id,
                skip=0,
                limit=500,
            )
            if sales_reps:
                tardinesses = []
                for u in sales_reps:
                    extra = getattr(u, "extra_metadata", None) or {}
                    t = extra.get("avg_tardiness_min")
                    if t is not None:
                        try:
                            tardinesses.append(int(t))
                        except (TypeError, ValueError):
                            pass
                avg_tardiness_min = int(sum(tardinesses) / len(tardinesses)) if tardinesses else 0

            return TeamCoachingMetrics(
                common_objection_peak=round(common_objection_peak, 2),
                script_adherence=round(script_adherence, 2),
                ask_otto_usage_hours=round(ask_otto_usage_hours, 2),
                win_rate_lift=0.0,
                otto_assisted_sales=OttoAssistedSales(deals_count=0, revenue_saved=0.0),
                attendance=AttendanceMetrics(rate=round(attendance_rate, 2), avg_tardiness_min=avg_tardiness_min),
            )
        except Exception as e:
            logger.warning(f"Could not load team_coaching_metrics: {e}")
            return None

    async def get_sales_team_stats(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[SalesTeamStatsEntry]:
        """
        Get sales team stats with pagination.
        If limit is None, returns all.
        """
        effective_limit = limit if limit is not None else 500
        return await self._get_sales_team_stats(
            company_id=company_id,
            skip=skip,
            limit=effective_limit,
        )
