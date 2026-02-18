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

from sqlalchemy import select, func, case, or_
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
from app.infrastructure.database.models.ask_otto_conversation import (
    AskOttoConversationORM,
    AskOttoMessageORM,
)
from app.infrastructure.database.models.lead import LeadORM

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
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Simple query: get ALL of today's appointments for this company
        today_query = (
            select(AppointmentORM)
            .where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.scheduled_start >= today_start,
                AppointmentORM.scheduled_start <= today_end,
            )
            .order_by(AppointmentORM.scheduled_start.desc())
            .limit(9)
        )
        today_result = await self.session.execute(today_query)
        appointments = today_result.scalars().all()

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
        sales_overview = await self._get_sales_overview(company_id, start_date=start_date, end_date=end_date)
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

        # Total recording duration from appointments (duration_seconds)
        total_duration_result = await self.session.execute(
            select(
                AppointmentORM.assigned_rep_id,
                func.coalesce(func.sum(AppointmentORM.duration_seconds), 0).label("total_sec"),
            )
            .where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.assigned_rep_id.in_(rep_ids),
                AppointmentORM.duration_seconds.isnot(None),
            )
            .group_by(AppointmentORM.assigned_rep_id)
        )
        duration_map = {r[0]: r[1] for r in total_duration_result.all()}

        # Win rate: won appointments / total assigned appointments per rep
        appt_stats_result = await self.session.execute(
            select(
                AppointmentORM.assigned_rep_id,
                func.count(AppointmentORM.id).label("total"),
                func.count(case(
                    (AppointmentORM.outcome == "won", AppointmentORM.id)
                )).label("won"),
            )
            .where(
                AppointmentORM.company_id == company_id,
                AppointmentORM.assigned_rep_id.in_(rep_ids),
            )
            .group_by(AppointmentORM.assigned_rep_id)
        )
        appt_stats_map = {r[0]: (r.total, r.won) for r in appt_stats_result.all()}

        # SOP compliance (process score) from call analyses
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

        # Otto usage: sum of conversation durations per rep
        conv_duration_subq = (
            select(
                AskOttoConversationORM.user_id.label("user_id"),
                (
                    func.extract('epoch', func.max(AskOttoMessageORM.created_at))
                    - func.extract('epoch', func.min(AskOttoMessageORM.created_at))
                ).label("duration_seconds"),
            )
            .select_from(AskOttoConversationORM)
            .join(AskOttoMessageORM, AskOttoConversationORM.id == AskOttoMessageORM.conversation_id)
            .where(
                AskOttoConversationORM.company_id == company_id,
                AskOttoConversationORM.user_id.in_(rep_ids),
            )
            .group_by(AskOttoConversationORM.id, AskOttoConversationORM.user_id)
        ).subquery()

        otto_usage_result = await self.session.execute(
            select(
                conv_duration_subq.c.user_id,
                func.coalesce(func.sum(conv_duration_subq.c.duration_seconds), 0).label("total_seconds"),
            )
            .group_by(conv_duration_subq.c.user_id)
        )
        otto_usage_map = {r[0]: r[1] for r in otto_usage_result.all()}

        # Count conversations per rep (for minimum duration of single-message convos)
        conv_count_result = await self.session.execute(
            select(
                AskOttoConversationORM.user_id,
                func.count(AskOttoConversationORM.id).label("conv_count"),
            )
            .where(
                AskOttoConversationORM.company_id == company_id,
                AskOttoConversationORM.user_id.in_(rep_ids),
            )
            .group_by(AskOttoConversationORM.user_id)
        )
        conv_count_map = {r[0]: r[1] for r in conv_count_result.all()}

        entries: List[SalesTeamStatsEntry] = []
        for rep in sales_reps:
            rep_id = rep.id
            total_sec = duration_map.get(rep_id, 0) or 0
            total_hours = round(total_sec / 3600.0, 2)

            # Win rate = won / total assigned appointments
            total_appts, won = appt_stats_map.get(rep_id, (0, 0))
            win_rate = round((won / total_appts * 100.0) if total_appts > 0 else 0.0, 2)

            avg_sop = process_map.get(rep_id)
            process_score = round(float(avg_sop * 10), 2) if avg_sop is not None else 0.0

            skills_score = process_score

            # Otto usage hours from conversation durations
            otto_seconds = float(otto_usage_map.get(rep_id, 0) or 0)
            total_convos = conv_count_map.get(rep_id, 0) or 0
            min_seconds = total_convos * 60  # at least 1 min per conversation
            effective_seconds = max(otto_seconds, min_seconds)
            otto_usage_hours = round(effective_seconds / 3600.0, 2)

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

    async def _get_sales_overview(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[SalesOverview]:
        """Build sales_overview directly from DB tables (appointments, leads, calls, call_analyses)."""
        try:
            from datetime import timedelta

            # Compute internal date range
            if end_date:
                _end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            else:
                _end_dt = datetime.now(timezone.utc)
            if start_date:
                _start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            else:
                _start_dt = _end_dt - timedelta(days=30)

            # Previous period for comparisons
            period_days = (_end_dt - _start_dt).days
            prev_start = _start_dt - timedelta(days=period_days)
            prev_end = _start_dt

            # --- Total conversations & avg recording duration (from appointments) ---
            # For sales inside dashboard, conversations refer to appointments.
            appt_calls_result = await self.session.execute(
                select(
                    func.count(AppointmentORM.id).label("total"),
                    func.avg(AppointmentORM.duration_seconds).label("avg_dur"),
                ).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.scheduled_start >= _start_dt,
                    AppointmentORM.scheduled_start <= _end_dt,
                )
            )
            appt_calls_row = appt_calls_result.one()
            total_appointments = int(appt_calls_row.total or 0)
            avg_sec = float(appt_calls_row.avg_dur or 0)
            avg_recording_duration = self._format_duration_as_hm(avg_sec)

            # --- Revenue & avg deal size ---
            # Compute revenue for the selected period (align with other KPIs)
            revenue_result = await self.session.execute(
                select(
                    func.coalesce(func.sum(LeadORM.deal_size), 0.0).label("total_revenue"),
                    func.count(LeadORM.id).label("deal_count"),
                    func.avg(LeadORM.deal_size).label("avg_deal"),
                ).where(
                    LeadORM.company_id == company_id,
                    LeadORM.deal_size.isnot(None),
                    LeadORM.deal_size > 0,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(func.coalesce(LeadORM.deal_status, "")) == "won",
                    ),
                    or_(
                        LeadORM.closed_at.between(_start_dt, _end_dt),
                        LeadORM.updated_at.between(_start_dt, _end_dt),
                    ),
                )
            )
            rev_row = revenue_result.one()
            revenue = float(rev_row.total_revenue or 0)
            avg_deal_size = float(rev_row.avg_deal or 0)

            # Fallback: if no won leads in period, try from appointments with outcome=won → leads
            if revenue == 0:
                apt_rev_result = await self.session.execute(
                    select(
                        func.coalesce(func.sum(LeadORM.deal_size), 0.0).label("total_revenue"),
                        func.count(LeadORM.id.distinct()).label("deal_count"),
                        func.avg(LeadORM.deal_size).label("avg_deal"),
                    )
                    .select_from(AppointmentORM)
                    .join(LeadORM, AppointmentORM.lead_id == LeadORM.id)
                    .where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.outcome == "won",
                        AppointmentORM.scheduled_start >= _start_dt,
                        AppointmentORM.scheduled_start <= _end_dt,
                        LeadORM.deal_size.isnot(None),
                        LeadORM.deal_size > 0,
                    )
                )
                apt_row = apt_rev_result.one()
                revenue = float(apt_row.total_revenue or 0)
                avg_deal_size = float(apt_row.avg_deal or 0)

            # --- Team win rate (won / total appointments) ---
            appt_result = await self.session.execute(
                select(
                    func.count(AppointmentORM.id).label("total"),
                    func.count(case(
                        (AppointmentORM.outcome == "won", AppointmentORM.id)
                    )).label("won"),
                ).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.scheduled_start >= _start_dt,
                    AppointmentORM.scheduled_start <= _end_dt,
                )
            )
            appt_row = appt_result.one()
            team_win_rate = round((appt_row.won / appt_row.total * 100), 2) if appt_row.total > 0 else 0.0

            # --- First touch win rate (fresh_sales via call analysis) ---
            first_touch_result = await self.session.execute(
                select(
                    func.count(AppointmentORM.id).label("total"),
                    func.count(case(
                        (AppointmentORM.outcome == "won", AppointmentORM.id)
                    )).label("won"),
                )
                .select_from(AppointmentORM)
                .join(CallORM, AppointmentORM.interaction_id == CallORM.id)
                .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
                .where(
                    AppointmentORM.company_id == company_id,
                    CallAnalysisORM.detected_call_type == "fresh_sales",
                    AppointmentORM.scheduled_start >= _start_dt,
                    AppointmentORM.scheduled_start <= _end_dt,
                )
            )
            ft_row = first_touch_result.one()
            first_touch_win_rate = round((ft_row.won / ft_row.total * 100), 2) if ft_row.total > 0 else 0.0

            # --- Follow-up win rate (follow_up_inquiry via call analysis) ---
            follow_up_wr_result = await self.session.execute(
                select(
                    func.count(AppointmentORM.id).label("total"),
                    func.count(case(
                        (AppointmentORM.outcome == "won", AppointmentORM.id)
                    )).label("won"),
                )
                .select_from(AppointmentORM)
                .join(CallORM, AppointmentORM.interaction_id == CallORM.id)
                .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
                .where(
                    AppointmentORM.company_id == company_id,
                    CallAnalysisORM.detected_call_type == "follow_up_inquiry",
                    AppointmentORM.scheduled_start >= _start_dt,
                    AppointmentORM.scheduled_start <= _end_dt,
                )
            )
            fu_row = follow_up_wr_result.one()
            follow_up_win_rate = round((fu_row.won / fu_row.total * 100), 2) if fu_row.total > 0 else 0.0

            # --- Follow-up rate: % of analyzed calls requiring follow-up ---
            follow_up_stats_result = await self.session.execute(
                select(
                    func.count(CallAnalysisORM.id).label("total_analyzed"),
                    func.count(case(
                        (CallAnalysisORM.follow_up_required == True, CallAnalysisORM.id)
                    )).label("follow_up_count"),
                )
                .select_from(CallORM)
                .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= _start_dt,
                    CallORM.created_at <= _end_dt,
                )
            )
            fu_stats = follow_up_stats_result.one()
            total_analyzed = fu_stats.total_analyzed or 0
            follow_up_count = fu_stats.follow_up_count or 0
            follow_up_rate = round((follow_up_count / total_analyzed * 100), 2) if total_analyzed > 0 else 0.0

            # --- Follow-up growth: compare with previous period ---
            prev_fu_stats_result = await self.session.execute(
                select(
                    func.count(CallAnalysisORM.id).label("total_analyzed"),
                    func.count(case(
                        (CallAnalysisORM.follow_up_required == True, CallAnalysisORM.id)
                    )).label("follow_up_count"),
                )
                .select_from(CallORM)
                .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= prev_start,
                    CallORM.created_at < prev_end,
                )
            )
            prev_fu_stats = prev_fu_stats_result.one()
            prev_total = prev_fu_stats.total_analyzed or 0
            prev_follow_up = prev_fu_stats.follow_up_count or 0
            prev_follow_up_rate = (prev_follow_up / prev_total * 100) if prev_total > 0 else 0.0
            follow_up_growth_percent = round(follow_up_rate - prev_follow_up_rate, 2) if prev_total > 0 else 0.0

            core_kpis = CoreKpis(
                revenue=round(revenue, 2),
                avg_deal_size=round(avg_deal_size, 2),
                total_conversations=total_appointments,
                avg_recording_duration=avg_recording_duration,
                team_win_rate=round(team_win_rate, 2),
                first_touch_win_rate=round(first_touch_win_rate, 2),
                follow_up_win_rate=round(follow_up_win_rate, 2),
                follow_up_rate=follow_up_rate,
                follow_up_growth_percent=follow_up_growth_percent,
            )

            # --- Close rate series: daily close rate chart points ---
            daily_stats_result = await self.session.execute(
                select(
                    func.date(AppointmentORM.scheduled_start).label("day"),
                    func.count(AppointmentORM.id).label("total"),
                    func.count(case(
                        (AppointmentORM.outcome == "won", AppointmentORM.id)
                    )).label("won"),
                )
                .where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.outcome.in_(["won", "lost", "no_show"]),
                    AppointmentORM.scheduled_start >= _start_dt,
                    AppointmentORM.scheduled_start <= _end_dt,
                )
                .group_by(func.date(AppointmentORM.scheduled_start))
                .order_by(func.date(AppointmentORM.scheduled_start))
            )
            daily_rows = daily_stats_result.all()

            close_rate_series = []
            for row in daily_rows:
                day_label = row.day
                if hasattr(day_label, 'strftime'):
                    try:
                        day_str = day_label.strftime("%-d %b")
                    except ValueError:
                        day_str = f"{day_label.day} {day_label.strftime('%b')}"
                else:
                    day_str = str(row.day)
                rate = round((row.won / row.total * 100), 2) if row.total > 0 else 0.0
                close_rate_series.append(CloseRatePoint(date=day_str, value=rate))

            # --- Sales increase: revenue comparison current vs previous period ---
            current_rev_result = await self.session.execute(
                select(func.coalesce(func.sum(LeadORM.deal_size), 0.0)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.deal_size.isnot(None),
                    LeadORM.deal_size > 0,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(func.coalesce(LeadORM.deal_status, "")) == "won",
                    ),
                    or_(
                        LeadORM.closed_at.between(_start_dt, _end_dt),
                        LeadORM.updated_at.between(_start_dt, _end_dt),
                    ),
                )
            )
            current_period_revenue = float(current_rev_result.scalar() or 0.0)

            prev_rev_result = await self.session.execute(
                select(func.coalesce(func.sum(LeadORM.deal_size), 0.0)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.deal_size.isnot(None),
                    LeadORM.deal_size > 0,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(func.coalesce(LeadORM.deal_status, "")) == "won",
                    ),
                    or_(
                        LeadORM.closed_at.between(prev_start, prev_end),
                        LeadORM.updated_at.between(prev_start, prev_end),
                    ),
                )
            )
            prev_period_revenue = float(prev_rev_result.scalar() or 0.0)

            sales_increase = None
            if current_period_revenue > 0 or prev_period_revenue > 0:
                value_increase = round(current_period_revenue - prev_period_revenue, 2)
                percentage_increase = round(
                    ((current_period_revenue - prev_period_revenue) / prev_period_revenue * 100)
                    if prev_period_revenue > 0 else 0.0,
                    2,
                )

                weekly_data_result = await self.session.execute(
                    select(
                        func.date_trunc('week', LeadORM.closed_at).label("week"),
                        func.coalesce(func.sum(LeadORM.deal_size), 0.0).label("revenue"),
                    )
                    .where(
                        LeadORM.company_id == company_id,
                        LeadORM.deal_size.isnot(None),
                        LeadORM.deal_size > 0,
                        or_(
                            LeadORM.status == "closed_won",
                            func.lower(func.coalesce(LeadORM.deal_status, "")) == "won",
                        ),
                        LeadORM.closed_at >= _start_dt,
                        LeadORM.closed_at <= _end_dt,
                    )
                    .group_by(func.date_trunc('week', LeadORM.closed_at))
                    .order_by(func.date_trunc('week', LeadORM.closed_at))
                )
                weekly_data = [float(r.revenue) for r in weekly_data_result.all()]

                sales_increase = SalesIncrease(
                    percentage=percentage_increase,
                    value_increase=value_increase,
                    weekly_data=weekly_data,
                )

            trends = Trends(
                close_rate_series=close_rate_series,
                sales_increase=sales_increase,
            )
            return SalesOverview(core_kpis=core_kpis, trends=trends)
        except Exception as e:
            logger.warning(f"Could not load sales_overview: {e}")
            import traceback
            traceback.print_exc()
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

            # Attendance: (total - no_show) / total * 100
            attendance_result = await self.session.execute(
                select(
                    func.count(AppointmentORM.id).label("total"),
                    func.count(case(
                        (AppointmentORM.outcome == "no_show", AppointmentORM.id)
                    )).label("no_show"),
                ).where(
                    AppointmentORM.company_id == company_id,
                )
            )
            att_row = attendance_result.one()
            attendance_rate = round(
                ((att_row.total - att_row.no_show) / att_row.total * 100), 2
            ) if att_row.total > 0 else 0.0

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

            # --- Win rate lift: Otto-using reps vs non-Otto reps ---
            otto_users_result = await self.session.execute(
                select(AskOttoConversationORM.user_id)
                .where(
                    AskOttoConversationORM.company_id == company_id,
                    AskOttoConversationORM.user_id.isnot(None),
                )
                .distinct()
            )
            otto_user_ids = set(r[0] for r in otto_users_result.all())

            win_rate_lift = 0.0
            otto_assisted_sales = OttoAssistedSales(deals_count=0, revenue_saved=0.0)

            if otto_user_ids:
                # Otto-assisted win rate
                otto_won_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.assigned_rep_id.in_(otto_user_ids),
                        AppointmentORM.outcome == "won",
                    )
                )
                otto_won = otto_won_result.scalar() or 0

                otto_resolved_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.assigned_rep_id.in_(otto_user_ids),
                        AppointmentORM.outcome.in_(["won", "lost", "no_show"]),
                    )
                )
                otto_resolved = otto_resolved_result.scalar() or 0
                otto_win_rate = (otto_won / otto_resolved * 100) if otto_resolved > 0 else 0.0

                # Non-Otto win rate
                non_otto_won_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.assigned_rep_id.notin_(otto_user_ids),
                        AppointmentORM.assigned_rep_id.isnot(None),
                        AppointmentORM.outcome == "won",
                    )
                )
                non_otto_won = non_otto_won_result.scalar() or 0

                non_otto_resolved_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.assigned_rep_id.notin_(otto_user_ids),
                        AppointmentORM.assigned_rep_id.isnot(None),
                        AppointmentORM.outcome.in_(["won", "lost", "no_show"]),
                    )
                )
                non_otto_resolved = non_otto_resolved_result.scalar() or 0
                non_otto_win_rate = (non_otto_won / non_otto_resolved * 100) if non_otto_resolved > 0 else 0.0

                win_rate_lift = round(otto_win_rate - non_otto_win_rate, 2)

                # --- Otto-assisted sales: won deals + revenue for Otto-using reps ---
                otto_deals_count = otto_won  # reuse from above

                otto_revenue_result = await self.session.execute(
                    select(func.coalesce(func.sum(LeadORM.deal_size), 0.0)).where(
                        LeadORM.company_id == company_id,
                        LeadORM.assigned_rep_id.in_(otto_user_ids),
                        LeadORM.status == "closed_won",
                        LeadORM.deal_size.isnot(None),
                    )
                )
                otto_revenue = float(otto_revenue_result.scalar() or 0.0)

                otto_assisted_sales = OttoAssistedSales(
                    deals_count=otto_deals_count,
                    revenue_saved=round(otto_revenue, 2),
                )

            return TeamCoachingMetrics(
                common_objection_peak=round(common_objection_peak, 2),
                script_adherence=round(script_adherence, 2),
                ask_otto_usage_hours=round(ask_otto_usage_hours, 2),
                win_rate_lift=win_rate_lift,
                otto_assisted_sales=otto_assisted_sales,
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
