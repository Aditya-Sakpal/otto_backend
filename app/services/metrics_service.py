"""
Metrics service.

Provides metrics and analytics calculations with date range filtering.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, date, timezone

from sqlalchemy import select, func, and_, or_, text, bindparam, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger


def _metrics_exclude_existing_and_service_not_offered():
    """Exclude call analyses that are existing-customer or service-not-offered from metrics."""
    return and_(
        or_(
            CallAnalysisORM.is_existing_customer == False,
            CallAnalysisORM.is_existing_customer.is_(None),
        ),
        or_(
            CallAnalysisORM.booking_status.is_(None),
            func.lower(CallAnalysisORM.booking_status) != "service_not_offered",
        ),
        or_(
            CallAnalysisORM.service_not_offered_reason.is_(None),
            CallAnalysisORM.service_not_offered_reason == "",
        ),
    )
def _compute_percentage_ticks(values: List[float], max_ticks: int = 6) -> List[float]:
    """Compute y-axis ticks for percentage data (0-100 range)."""
    if not values or max(values) <= 0:
        return [0.0]
    max_v = max(values)
    nice_steps = [1, 2, 5, 10, 20, 25, 50]
    best_step = 20  # default
    for step in nice_steps:
        n_ticks = int(max_v // step) + 2
        if 3 <= n_ticks <= max_ticks + 1:
            best_step = step
            break
    high = min(((int(max_v) // best_step) + 1) * best_step, 100)
    ticks: List[float] = []
    v = 0.0
    while v <= high:
        ticks.append(v)
        v += best_step
    return ticks


from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.user import UserORM
from app.domain.enums import UserRole
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository

logger = get_logger(__name__)


class MetricsService:
    """Service for metrics and analytics."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
        self.lead_repo = LeadRepository(session)
        self.appointment_repo = AppointmentRepository(session)
        self.analysis_repo = CallAnalysisRepository(session)

    def _classify_objections_in_analysis(self, analysis: CallAnalysisORM) -> List[str]:
        """
        Classify raw objections from analysis into standardized categories.

        Args:
            analysis: CallAnalysisORM instance with raw objections

        Returns:
            List of classified objection categories (deduplicated)
        """
        from app.domain.objection_classifier import ObjectionClassifier

        if not analysis or not analysis.objections:
            return []

        return ObjectionClassifier.classify_and_deduplicate(analysis.objections)

    def _get_date_range(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> tuple[datetime, datetime]:
        """
        Get datetime range from date parameters.
        
        If not provided, defaults to last 30 days.
        """
        if end_date:
            end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)

        if start_date:
            start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        else:
            start_dt = end_dt - timedelta(days=30)

        return start_dt, end_dt
    
    async def get_company_overview(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get company overview metrics within date range."""
        try:
            # Resolution rules:
            # - If user_id is provided: prefer user_id and derive company_id from user
            # - Else: company_id must be provided
            user_role = None
            if user_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("Either provide company_id, or provide user_id that belongs to a user with a company_id")
                company_id = user.company_id
                user_role = user.role
            elif not company_id:
                raise ValueError("Either company_id or user_id is required")

            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Build base filters
            lead_filters = [
                LeadORM.company_id == company_id,
                LeadORM.created_at >= start_dt,
                LeadORM.created_at <= end_dt,
            ]
            call_filters = [
                CallORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
            ]
            appointment_filters = [
                AppointmentORM.company_id == company_id,
                AppointmentORM.created_at >= start_dt,
                AppointmentORM.created_at <= end_dt,
            ]
            
            # Add user_id filtering if provided
            if user_id:
                lead_filters.append(LeadORM.assigned_rep_id == user_id)
                call_filters.append(CallORM.handled_by_user_id == user_id)
                appointment_filters.append(AppointmentORM.assigned_rep_id == user_id)
            
            # Total leads in date range
            total_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(*lead_filters)
            )
            total_leads_count = total_leads.scalar() or 0
            
            # Active leads (not closed) in date range
            active_leads_filters = lead_filters + [LeadORM.status.notin_(["closed_won", "closed_lost", "abandoned", "dormant"])]
            active_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(*active_leads_filters)
            )
            active_leads_count = active_leads.scalar() or 0
            
            # Qualified leads in date range
            # Count leads whose status is one of the qualified statuses
            qualified_leads_filters = lead_filters + [
                LeadORM.status.in_(["qualified_booked", "qualified_unbooked"])
            ]
            qualified_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(*qualified_leads_filters)
            )
            qualified_leads_count = qualified_leads.scalar() or 0
            
            # Total calls in date range
            total_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(*call_filters)
            )
            total_calls_count = total_calls.scalar() or 0
            
            # Missed calls in date range
            missed_calls_filters = call_filters + [CallORM.missed_call == True]
            missed_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(*missed_calls_filters)
            )
            missed_calls_count = missed_calls.scalar() or 0
            
            # Total appointments in date range
            total_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*appointment_filters)
            )
            total_appointments_count = total_appointments.scalar() or 0

            # Booked appointments (lead-count): number of leads with status == 'qualified_booked'
            booked_leads_filters = lead_filters + [
                LeadORM.status == "qualified_booked"
            ]
            if user_id:
                booked_leads_filters.append(LeadORM.assigned_rep_id == user_id)
            booked_leads_result = await self.session.execute(
                select(func.count(LeadORM.id)).where(*booked_leads_filters)
            )
            booked_leads_value = booked_leads_result.scalar() or 0

            # For sales reps: show close rate (won appointments / total appointments)
            # For CSRs/company-wide: show booking rate (booked_leads / qualified_leads)
            is_sales_rep = user_role == "sales_rep"

            if is_sales_rep:
                # Close rate: won appointments / total appointments
                won_appts_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        *appointment_filters,
                        AppointmentORM.outcome == "won",
                    )
                )
                won_appts_count = won_appts_result.scalar() or 0
                conversion_rate = (won_appts_count / total_appointments_count * 100) if total_appointments_count > 0 else 0.0
            else:
                # Booking rate: (booked_leads / qualified_leads) * 100
                if qualified_leads_count > 0:
                    booking_rate = (booked_leads_value / qualified_leads_count) * 100
                else:
                    booking_rate = 0.0
                conversion_rate = booking_rate

            # Total revenue: for sales reps use won deals, for others use booked deals.
            if is_sales_rep:
                won_revenue_filters = [
                    LeadORM.company_id == company_id,
                    LeadORM.assigned_rep_id == user_id,
                    LeadORM.deal_size.isnot(None),
                    LeadORM.deal_size > 0,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(func.coalesce(LeadORM.deal_status, "")) == "won",
                    ),
                    or_(
                        and_(
                            LeadORM.closed_at.isnot(None),
                            LeadORM.closed_at >= start_dt,
                            LeadORM.closed_at <= end_dt,
                        ),
                        and_(
                            LeadORM.updated_at.isnot(None),
                            LeadORM.updated_at >= start_dt,
                            LeadORM.updated_at <= end_dt,
                        ),
                    ),
                ]
                total_revenue = await self.session.execute(
                    select(func.coalesce(func.sum(LeadORM.deal_size), 0.0)).where(*won_revenue_filters)
                )
                revenue = float(total_revenue.scalar() or 0.0)
            else:
                is_booked = or_(
                    func.lower(LeadORM.status) == "qualified_booked",
                    and_(
                        LeadORM.deal_status.isnot(None),
                        func.lower(func.trim(LeadORM.deal_status)) == "booked",
                    ),
                )
                lead_booked_in_period_filters = [
                    LeadORM.company_id == company_id,
                    is_booked,
                    or_(
                        and_(
                            LeadORM.created_at >= start_dt,
                            LeadORM.created_at <= end_dt,
                        ),
                        and_(
                            LeadORM.updated_at.isnot(None),
                            LeadORM.updated_at >= start_dt,
                            LeadORM.updated_at <= end_dt,
                        ),
                    ),
                ]
                if user_id:
                    lead_booked_in_period_filters.append(LeadORM.assigned_rep_id == user_id)
                total_revenue = await self.session.execute(
                    select(func.sum(LeadORM.deal_size)).where(*lead_booked_in_period_filters)
                )
                revenue = total_revenue.scalar() or 0.0

            return {
                "total_leads": total_leads_count,
                "active_leads": active_leads_count,
                "qualified_leads": qualified_leads_count,
                "total_calls": total_calls_count,
                "missed_calls": missed_calls_count,
                "total_appointments": total_appointments_count if is_sales_rep else booked_leads_value,
                "conversion_rate": round(conversion_rate, 2),
                "booked_leads": booked_leads_value,
                "total_revenue": round(revenue, 2),
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting company overview: {e}")
            raise e
    
    async def get_csr_dashboard(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get CSR dashboard metrics within date range."""
        try:
            # Resolution rules:
            # - If user_id is provided: prefer user_id and derive company_id from user
            # - Else: company_id must be provided
            if user_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("Either provide company_id, or provide user_id that belongs to a user with a company_id")
                company_id = user.company_id
            elif not company_id:
                raise ValueError("Either company_id or user_id is required")

            start_dt, end_dt = self._get_date_range(start_date, end_date)
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            # Build base filters
            call_filters = [
                CallORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
            ]
            lead_filters = [
                LeadORM.company_id == company_id,
                LeadORM.created_at >= start_dt,
                LeadORM.created_at <= end_dt,
            ]
            appointment_filters = [
                AppointmentORM.company_id == company_id,
                AppointmentORM.created_at >= start_dt,
                AppointmentORM.created_at <= end_dt,
            ]
            
            # Add user_id filtering if provided
            if user_id:
                call_filters.append(CallORM.handled_by_user_id == user_id)
                lead_filters.append(LeadORM.assigned_rep_id == user_id)
                appointment_filters.append(AppointmentORM.assigned_rep_id == user_id)
            
            # Total calls in date range
            total_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(*call_filters)
            )
            total_calls_count = total_calls.scalar() or 0
            
            # Missed calls in date range
            missed_calls_filters = call_filters + [CallORM.missed_call == True]
            missed_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(*missed_calls_filters)
            )
            missed_calls_count = missed_calls.scalar() or 0
            
            # Calls today
            calls_today_filters = [
                CallORM.company_id == company_id,
                CallORM.created_at >= today_start,
            ]
            if user_id:
                calls_today_filters.append(CallORM.handled_by_user_id == user_id)
            calls_today = await self.session.execute(
                select(func.count(CallORM.id)).where(*calls_today_filters)
            )
            calls_today_count = calls_today.scalar() or 0
            
            # Average call duration in date range
            avg_duration_filters = call_filters + [CallORM.duration_seconds.isnot(None)]
            avg_duration = await self.session.execute(
                select(func.avg(CallORM.duration_seconds)).where(*avg_duration_filters)
            )
            avg_duration_val = avg_duration.scalar() or 0.0
            
            # Leads count in date range
            leads_count = await self.session.execute(
                select(func.count(LeadORM.id)).where(*lead_filters)
            )
            leads_assigned = leads_count.scalar() or 0
            
            # Appointments scheduled in date range
            appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*appointment_filters)
            )
            appointments_count = appointments.scalar() or 0
            
            return {
                "total_calls": total_calls_count,
                "missed_calls": missed_calls_count,
                "calls_today": calls_today_count,
                "avg_call_duration": round(avg_duration_val, 2),
                "leads_assigned": leads_assigned,
                "appointments_scheduled": appointments_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting CSR dashboard: {e}")
            raise e
    
    async def get_missed_calls(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get missed calls metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Missed calls in date range
            missed_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                )
            )
            missed_count = missed_calls.scalar() or 0
            
            # Total calls in date range
            total_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_count = total_calls.scalar() or 0
            
            # Picked up: missed calls that were followed up (have a lead)
            picked_up_result = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True,
                    CallORM.lead_id.isnot(None),
                )
            )
            picked_up_count = picked_up_result.scalar() or 0

            # Booked: missed calls linked to a qualified_booked lead
            from sqlalchemy import join as sa_join
            booked_result = await self.session.execute(
                select(func.count(CallORM.id))
                .select_from(
                    sa_join(CallORM, LeadORM, CallORM.lead_id == LeadORM.id)
                )
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True,
                    LeadORM.status == "qualified_booked",
                )
            )
            booked_count = booked_result.scalar() or 0

            # Recent missed calls in date range
            recent_missed = await self.session.execute(
                select(CallORM).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                ).order_by(CallORM.created_at.desc()).limit(10)
            )
            recent_missed_list = recent_missed.scalars().all()

            miss_rate = (missed_count / total_count * 100) if total_count > 0 else 0.0
            booking_percentage = round((booked_count / missed_count * 100), 2) if missed_count > 0 else 0.0

            return {
                "missed_calls": missed_count,
                "total_calls": total_count,
                "miss_rate": round(miss_rate, 2),
                "picked_up": picked_up_count,
                "booked": booked_count,
                "booking_percentage": booking_percentage,
                "recent_missed": [
                    {
                        "id": str(call.id),
                        "phone_number": call.phone_number,
                        "created_at": call.created_at.isoformat() if call.created_at else None,
                        "lead_id": str(call.lead_id) if call.lead_id else None,
                    }
                    for call in recent_missed_list
                ],
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting missed calls: {e}")
            raise e
    
    async def get_booking_rate_improvement(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        start_a: Optional[date] = None,
        end_a: Optional[date] = None,
        start_b: Optional[date] = None,
        end_b: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get booking rate improvement metrics.
        - Legacy single-period mode: provide start_date & end_date (keeps backward compatibility).
        - New dual-period mode: provide start_a,end_a and start_b,end_b to return per-day booked counts for both periods,
          plus a unified x_axis for plotting.
        """
        try:
            # Resolve company_id from user if provided
            if user_id and not company_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("Either provide company_id, or provide user_id that belongs to a user with a company_id")
                company_id = user.company_id
            elif not company_id:
                # company_id will be required in later logic (either directly or via user_id)
                pass

            # If dual-period params provided, run per-day counts for both periods and return series
            if start_a and end_a and start_b and end_b:
                if not company_id:
                    raise ValueError("company_id or user_id (with company) is required for dual-period mode")

                # Define booked condition for leads
                is_booked = or_(
                    func.lower(LeadORM.status) == "qualified_booked",
                    and_(
                        LeadORM.deal_status.isnot(None),
                        func.lower(func.trim(LeadORM.deal_status)) == "booked",
                    ),
                )

                from datetime import timedelta as _td, time as _time

                async def rates_by_day(s: date, e: date) -> Dict[str, float]:
                    """Compute booking rate percentage per day: (booked / qualified) * 100."""
                    rates: Dict[str, float] = {}
                    current = s
                    while current <= e:
                        day_start = datetime.combine(current, _time.min).replace(tzinfo=timezone.utc)
                        day_end = datetime.combine(current, _time.max).replace(tzinfo=timezone.utc)

                        # Single query: count all qualified leads and conditionally count booked ones
                        q = select(
                            func.count(LeadORM.id).label("total_qualified"),
                            func.count(case((is_booked, LeadORM.id))).label("total_booked"),
                        ).where(
                            LeadORM.company_id == company_id,
                            LeadORM.status.in_(["qualified_booked", "qualified_unbooked"]),
                            or_(
                                and_(LeadORM.created_at >= day_start, LeadORM.created_at <= day_end),
                                and_(LeadORM.updated_at >= day_start, LeadORM.updated_at <= day_end),
                            )
                        )
                        if user_id:
                            q = q.where(LeadORM.assigned_rep_id == user_id)

                        row = (await self.session.execute(q)).one()
                        qualified = row.total_qualified or 0
                        booked = row.total_booked or 0
                        rate = round((booked / qualified) * 100, 2) if qualified > 0 else 0.0
                        rates[current.isoformat()] = rate
                        current = current + _td(days=1)
                    return rates

                a_rates = await rates_by_day(start_a, end_a)
                b_rates = await rates_by_day(start_b, end_b)

                # Prepare date lists for each day in the periods
                def dates_list(start: date, end: date) -> List[str]:
                    lst: List[str] = []
                    cur = start
                    from datetime import timedelta as __td
                    while cur <= end:
                        lst.append(cur.isoformat())
                        cur = cur + __td(days=1)
                    return lst

                a_dates = dates_list(start_a, end_a)
                b_dates = dates_list(start_b, end_b)

                # Build per-day ordered lists of rate percentages
                a_vals = [a_rates.get(d, 0.0) for d in a_dates]
                b_vals = [b_rates.get(d, 0.0) for d in b_dates]

                len_a = len(a_vals)
                len_b = len(b_vals)
                K = max(len_a, len_b, 1)

                # series: x = actual ISO date (or empty), y = booking rate percentage
                series_a = [{"x": a_dates[i] if i < len_a else "", "y": a_vals[i] if i < len_a else 0.0} for i in range(K)]
                series_b = [{"x": b_dates[i] if i < len_b else "", "y": b_vals[i] if i < len_b else 0.0} for i in range(K)]

                # x_axis: "periodA_date/periodB_date"
                x_axis = [f"{(a_dates[i] if i < len_a else '')}/{(b_dates[i] if i < len_b else '')}" for i in range(K)]

                # Compute percentage y-axis ticks
                combined_vals = a_vals + b_vals
                ticks = _compute_percentage_ticks(combined_vals)

                return {
                    "period_a": {
                        "start": start_a.isoformat(),
                        "end": end_a.isoformat(),
                        "average_booking_rate": round(sum(a_vals) / len(a_vals), 2) if a_vals else 0.0,
                        "series": series_a,
                    },
                    "period_b": {
                        "start": start_b.isoformat(),
                        "end": end_b.isoformat(),
                        "average_booking_rate": round(sum(b_vals) / len(b_vals), 2) if b_vals else 0.0,
                        "series": series_b,
                    },
                    "x_axis": x_axis,
                    "y_axis": ticks,
                }

            # Legacy behavior (single period): keep existing calculation (current vs previous period)
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            # Calculate period length
            period_length = (end_dt - start_dt).days
            previous_start = start_dt - timedelta(days=period_length)
            previous_end = start_dt

            appointment_scope = [AppointmentORM.company_id == company_id]
            lead_scope = [LeadORM.company_id == company_id]
            if user_id:
                appointment_scope.append(AppointmentORM.assigned_rep_id == user_id)
                lead_scope.append(LeadORM.assigned_rep_id == user_id)

            # Current period: appointments (booked appointments)
            current_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            current_appointments = current_bookings.scalar() or 0

            # Current period: booked calls (from call_analyses, case-insensitive booking_status)
            current_booked_calls_q = (
                select(func.count(CallAnalysisORM.id))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallAnalysisORM.booking_status.isnot(None),
                    func.lower(CallAnalysisORM.booking_status) == "booked",
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            if user_id:
                current_booked_calls_q = current_booked_calls_q.where(CallORM.handled_by_user_id == user_id)
            current_booked_calls = await self.session.execute(current_booked_calls_q)
            current_booked_calls_count = current_booked_calls.scalar() or 0

            # Current period: booked leads (status=qualified_booked or deal_status=booked)
            current_booked_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(
                        LeadORM.status == "qualified_booked",
                        func.lower(LeadORM.deal_status) == "booked",
                    ),
                )
            )
            current_booked_leads_count = current_booked_leads.scalar() or 0

            # Current period qualified leads
            current_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.status.in_(["qualified_booked", "qualified_unbooked"]),
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            current_qualified_count = current_qualified.scalar() or 0

            # Previous period: appointments + booked calls
            previous_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    AppointmentORM.created_at >= previous_start,
                    AppointmentORM.created_at < previous_end,
                )
            )
            previous_appointments = previous_bookings.scalar() or 0
            previous_booked_calls_q = (
                select(func.count(CallAnalysisORM.id))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= previous_start,
                    CallORM.created_at < previous_end,
                    CallAnalysisORM.booking_status.isnot(None),
                    func.lower(CallAnalysisORM.booking_status) == "booked",
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            if user_id:
                previous_booked_calls_q = previous_booked_calls_q.where(CallORM.handled_by_user_id == user_id)
            previous_booked_calls = await self.session.execute(previous_booked_calls_q)
            previous_booked_calls_count = previous_booked_calls.scalar() or 0

            # Previous period qualified
            previous_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.status.in_(["qualified_booked", "qualified_unbooked"]),
                    LeadORM.created_at >= previous_start,
                    LeadORM.created_at < previous_end,
                )
            )
            previous_qualified_count = previous_qualified.scalar() or 0

            # Combined booked: appointments + booked calls (so APIs return non-zero when DB has booked calls)
            current_count = current_appointments + current_booked_calls_count
            previous_count = previous_appointments + previous_booked_calls_count

            current_rate = (current_count / current_qualified_count * 100) if current_qualified_count > 0 else 0.0
            previous_rate = (previous_count / previous_qualified_count * 100) if previous_qualified_count > 0 else 0.0
            improvement = current_rate - previous_rate

            return {
                "current_rate": round(current_rate, 2),
                "previous_rate": round(previous_rate, 2),
                "improvement_percentage": round(improvement, 2),
                "total_bookings": current_count,
                "booked_appointments": current_appointments,
                "booked_calls": current_booked_calls_count,
                "booked_leads": current_booked_leads_count,
                "total_qualified": current_qualified_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "previous_period_start": previous_start.isoformat(),
                "previous_period_end": previous_end.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting booking rate improvement: {e}")
            raise e

    async def get_close_rate_trends(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        start_a: Optional[date] = None,
        end_a: Optional[date] = None,
        start_b: Optional[date] = None,
        end_b: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get close rate trends metrics (similar to booking rate improvement but for closed deals).

        - Legacy single-period mode: provide start_date & end_date (keeps backward compatibility).
        - New dual-period mode: provide start_a,end_a and start_b,end_b to return per-day closed counts for both periods,
          plus a unified x_axis for plotting.

        Tracks appointments with outcome='won' and leads with status='closed_won'.
        """
        try:
            # Resolve company_id from user if provided
            if user_id and not company_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("Either provide company_id, or provide user_id that belongs to a user with a company_id")
                company_id = user.company_id
            elif not company_id:
                pass

            # If dual-period params provided, run per-day counts for both periods and return series
            if start_a and end_a and start_b and end_b:
                if not company_id:
                    raise ValueError("company_id or user_id (with company) is required for dual-period mode")

                from datetime import timedelta as _td, time as _time

                async def rates_by_day(s: date, e: date) -> Dict[str, float]:
                    """Compute close rate percentage per day: (won appointments / total appointments) * 100."""
                    rates: Dict[str, float] = {}
                    current = s
                    while current <= e:
                        day_start = datetime.combine(current, _time.min).replace(tzinfo=timezone.utc)
                        day_end = datetime.combine(current, _time.max).replace(tzinfo=timezone.utc)

                        # Single query: count all appointments and conditionally count won ones
                        q = select(
                            func.count(AppointmentORM.id).label("total_appointments"),
                            func.count(case(
                                (func.lower(AppointmentORM.outcome) == "won", AppointmentORM.id)
                            )).label("won_appointments"),
                        ).where(
                            AppointmentORM.company_id == company_id,
                            or_(
                                and_(AppointmentORM.created_at >= day_start, AppointmentORM.created_at <= day_end),
                                and_(AppointmentORM.updated_at >= day_start, AppointmentORM.updated_at <= day_end),
                            )
                        )
                        if user_id:
                            q = q.where(AppointmentORM.assigned_rep_id == user_id)

                        row = (await self.session.execute(q)).one()
                        total = row.total_appointments or 0
                        won = row.won_appointments or 0
                        rate = round((won / total) * 100, 2) if total > 0 else 0.0
                        rates[current.isoformat()] = rate
                        current = current + _td(days=1)
                    return rates

                a_rates = await rates_by_day(start_a, end_a)
                b_rates = await rates_by_day(start_b, end_b)

                # Prepare date lists for each day in the periods
                def dates_list(start: date, end: date) -> List[str]:
                    lst: List[str] = []
                    cur = start
                    from datetime import timedelta as __td
                    while cur <= end:
                        lst.append(cur.isoformat())
                        cur = cur + __td(days=1)
                    return lst

                a_dates = dates_list(start_a, end_a)
                b_dates = dates_list(start_b, end_b)

                # Build per-day ordered lists of rate percentages
                a_vals = [a_rates.get(d, 0.0) for d in a_dates]
                b_vals = [b_rates.get(d, 0.0) for d in b_dates]

                len_a = len(a_vals)
                len_b = len(b_vals)
                K = max(len_a, len_b, 1)

                # series: x = actual ISO date (or empty), y = close rate percentage
                series_a = [{"x": a_dates[i] if i < len_a else "", "y": a_vals[i] if i < len_a else 0.0} for i in range(K)]
                series_b = [{"x": b_dates[i] if i < len_b else "", "y": b_vals[i] if i < len_b else 0.0} for i in range(K)]

                # x_axis: "periodA_date/periodB_date"
                x_axis = [f"{(a_dates[i] if i < len_a else '')}/{(b_dates[i] if i < len_b else '')}" for i in range(K)]

                # Compute percentage y-axis ticks
                combined_vals = a_vals + b_vals
                ticks = _compute_percentage_ticks(combined_vals)

                return {
                    "period_a": {
                        "start": start_a.isoformat(),
                        "end": end_a.isoformat(),
                        "average_close_rate": round(sum(a_vals) / len(a_vals), 2) if a_vals else 0.0,
                        "series": series_a,
                    },
                    "period_b": {
                        "start": start_b.isoformat(),
                        "end": end_b.isoformat(),
                        "average_close_rate": round(sum(b_vals) / len(b_vals), 2) if b_vals else 0.0,
                        "series": series_b,
                    },
                    "x_axis": x_axis,
                    "y_axis": ticks,
                }

            # Legacy behavior (single period): keep existing calculation (current vs previous period)
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            period_length = (end_dt - start_dt).days
            previous_start = start_dt - timedelta(days=period_length)
            previous_end = start_dt

            appointment_scope = [AppointmentORM.company_id == company_id]
            lead_scope = [LeadORM.company_id == company_id]
            if user_id:
                appointment_scope.append(AppointmentORM.assigned_rep_id == user_id)
                lead_scope.append(LeadORM.assigned_rep_id == user_id)

            # Current period: won appointments
            current_won_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    func.lower(AppointmentORM.outcome) == "won",
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            current_won_appts_count = current_won_appointments.scalar() or 0

            # Current period: closed won leads
            current_closed_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(LeadORM.deal_status) == "won",
                    ),
                )
            )
            current_closed_leads_count = current_closed_leads.scalar() or 0

            # Previous period: won appointments
            previous_won_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    func.lower(AppointmentORM.outcome) == "won",
                    AppointmentORM.created_at >= previous_start,
                    AppointmentORM.created_at < previous_end,
                )
            )
            previous_won_appts_count = previous_won_appointments.scalar() or 0

            # Previous period: closed won leads
            previous_closed_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.created_at >= previous_start,
                    LeadORM.created_at < previous_end,
                    or_(
                        LeadORM.status == "closed_won",
                        func.lower(LeadORM.deal_status) == "won",
                    ),
                )
            )
            previous_closed_leads_count = previous_closed_leads.scalar() or 0

            # Total qualified leads for rate calculation
            current_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            current_qualified_count = current_qualified.scalar() or 0

            previous_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    *lead_scope,
                    LeadORM.created_at >= previous_start,
                    LeadORM.created_at < previous_end,
                )
            )
            previous_qualified_count = previous_qualified.scalar() or 0

            # Combined closed: won appointments + closed won leads
            current_count = current_won_appts_count + current_closed_leads_count
            previous_count = previous_won_appts_count + previous_closed_leads_count

            current_rate = (current_count / current_qualified_count * 100) if current_qualified_count > 0 else 0.0
            previous_rate = (previous_count / previous_qualified_count * 100) if previous_qualified_count > 0 else 0.0
            improvement = current_rate - previous_rate

            return {
                "current_rate": round(current_rate, 2),
                "previous_rate": round(previous_rate, 2),
                "improvement_percentage": round(improvement, 2),
                "total_closed": current_count,
                "closed_appointments": current_won_appts_count,
                "closed_leads": current_closed_leads_count,
                "total_qualified": current_qualified_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "previous_period_start": previous_start.isoformat(),
                "previous_period_end": previous_end.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting close rate trends: {e}")
            raise e

    async def get_top_objections(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get top objections from call analyses within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get all analyses with objections in date range (exclude existing customer & service not offered)
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections != None,
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            analyses_list = analyses.scalars().all()
            
            # Count objections
            objection_counts: Dict[str, int] = {}
            total_with_objections = 0
            
            for analysis in analyses_list:
                if analysis.objections:
                    total_with_objections += 1
                    for obj in analysis.objections:
                        objection_counts[obj] = objection_counts.get(obj, 0) + 1
            
            # Sort by count and get top
            sorted_objections = sorted(objection_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            total_objections = sum(objection_counts.values())
            
            objections = [
                {
                    "objection_type": obj_type,
                    "count": count,
                    "percentage": round((count / total_objections * 100) if total_objections > 0 else 0, 2),
                }
                for obj_type, count in sorted_objections
            ]
            
            return {
                "objections": objections,
                "total_calls_with_objections": total_with_objections,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting top objections: {e}")
            raise e
    
    async def get_coaching_opportunities(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Get coaching opportunities based on low SOP compliance within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get analyses with low SOP compliance in date range (exclude existing customer & service not offered)
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                    CallAnalysisORM.sop_compliance_score < 0.7,
                    _metrics_exclude_existing_and_service_not_offered(),
                ).order_by(CallAnalysisORM.sop_compliance_score.asc()).limit(limit)
            )
            analyses_list = analyses.scalars().all()
            
            # Count total
            total = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                    CallAnalysisORM.sop_compliance_score < 0.7,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            total_count = total.scalar() or 0
            
            opportunities = []
            for analysis in analyses_list:
                # Get call to find owner
                call = await self.session.execute(
                    select(CallORM).where(CallORM.id == analysis.call_id)
                )
                call_obj = call.scalar_one_or_none()
                
                opportunities.append({
                    "call_id": str(analysis.call_id),
                    "rep_id": str(call_obj.handled_by_user_id) if call_obj and call_obj.handled_by_user_id else None,
                    "sop_compliance_score": analysis.sop_compliance_score,
                    "sop_stages_missed": analysis.sop_stages_missed or [],
                    "sentiment_score": analysis.sentiment_score,
                })
            
            return {
                "opportunities": opportunities,
                "total_count": total_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting coaching opportunities: {e}")
            raise e
    
    async def get_most_coaching_opportunities(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get most coaching opportunities - top 5 employees with least success rate.
        
        Success rate = qualified_leads / booked_leads
        - Qualified leads: qualification_status in ['hot', 'cold', 'warm', 'qualified']
        - Booked leads: booking_status == 'booked'
        
        For each employee, also returns top 3 objections (most coaching need).
        """
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Join call_analyses with calls to get handled_by_user_id
            # Filter by company_id and date range
            # Count qualified and booked leads per employee
            from sqlalchemy import join
            
            # Build the join; filter by call date (when call happened) so booked calls are included
            call_analysis_call_join = join(
                CallAnalysisORM,
                CallORM,
                CallAnalysisORM.call_id == CallORM.id
            ).join(UserORM, CallORM.handled_by_user_id == UserORM.id)

            # Get all analyses with calls for this company (use CallORM.created_at for date range)
            # Only include sales_rep users, not CSRs
            analyses_query = select(
                CallORM.handled_by_user_id,
                CallAnalysisORM.qualification_status,
                CallAnalysisORM.booking_status,
                CallAnalysisORM,  # Need full analysis object for classification
                CallORM.id.label('call_id')
            ).select_from(call_analysis_call_join).where(
                CallAnalysisORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
                CallORM.handled_by_user_id.isnot(None),
                UserORM.role == 'sales_rep',
                _metrics_exclude_existing_and_service_not_offered(),
            )
            
            analyses_result = await self.session.execute(analyses_query)
            analyses_list = analyses_result.all()
            
            # Group by employee and calculate metrics
            employee_stats: Dict[UUID, Dict[str, Any]] = {}
            
            for row in analyses_list:
                user_id = row.handled_by_user_id
                analysis = row[3]  # CallAnalysisORM is the 4th field (index 3)
                if not user_id:
                    continue

                if user_id not in employee_stats:
                    employee_stats[user_id] = {
                        'qualified_leads': 0,
                        'booked_leads': 0,
                        'total_calls': 0,
                        # Per objection: count, qualified count, booked count (for % Unbooked and # Unbooked/Qualified)
                        'objections': {}  # objection -> {'count': n, 'qualified': q, 'booked': b}
                    }

                stats = employee_stats[user_id]
                stats['total_calls'] += 1

                # Check if qualified
                qual_status = row.qualification_status
                is_qualified = qual_status and qual_status.lower() in ['hot', 'cold', 'warm', 'qualified']
                if is_qualified:
                    stats['qualified_leads'] += 1

                # Check if booked
                booking_status = row.booking_status
                is_booked = booking_status and booking_status.lower() == 'booked'
                if is_booked:
                    stats['booked_leads'] += 1

                # Count objections and per-objection qualified/booked (after classification)
                if analysis and analysis.objections:
                    # Classify objections before counting
                    classified_objections = self._classify_objections_in_analysis(analysis)
                    for obj in classified_objections:
                        if obj:  # Skip empty strings
                            obj_stripped = str(obj).strip()
                            if obj_stripped not in stats['objections']:
                                stats['objections'][obj_stripped] = {'count': 0, 'qualified': 0, 'booked': 0}
                            stats['objections'][obj_stripped]['count'] += 1
                            if is_qualified:
                                stats['objections'][obj_stripped]['qualified'] += 1
                            if is_booked:
                                stats['objections'][obj_stripped]['booked'] += 1
            
            # Calculate success rate and prepare results
            employee_results = []
            for user_id, stats in employee_stats.items():
                qualified = stats['qualified_leads']
                booked = stats['booked_leads']
                
                # Calculate success rate: booked_leads / qualified_leads (as percentage)
                # This matches the image format where 7/11 = 64%
                # If qualified is 0, success_rate is 0
                if qualified > 0:
                    success_rate = (booked / qualified) * 100
                else:
                    # If no qualified leads, set success_rate to 0
                    # This ensures employees with no qualified leads are prioritized for coaching
                    success_rate = 0.0
                
                # Get top 3 objections with % Unbooked and # Unbooked/Qualified per objection
                objections_sorted = sorted(
                    stats['objections'].items(),
                    key=lambda x: x[1]['count'],
                    reverse=True
                )[:3]
                top_objections_with_metrics = []
                for obj_name, obj_data in objections_sorted:
                    q = obj_data['qualified']
                    b = obj_data['booked']
                    unbooked = max(0, q - b)
                    pct_unbooked = (unbooked / q * 100) if q > 0 else 0.0
                    unbooked_qualified_ratio = f"{unbooked}/{q}"
                    top_objections_with_metrics.append({
                        'objection': obj_name,
                        'pct_unbooked': round(pct_unbooked, 2),
                        'unbooked_qualified_ratio': unbooked_qualified_ratio,
                        'unbooked_count': unbooked,
                        'qualified_count': q,
                    })
                
                employee_results.append({
                    'user_id': str(user_id),
                    'qualified_leads': qualified,
                    'booked_leads': booked,
                    'total_calls': stats['total_calls'],
                    'success_rate': round(success_rate, 2),
                    'top_objections': top_objections_with_metrics
                })
            
            # Sort by success_rate ascending (least success rate first) and get top 5
            employee_results.sort(key=lambda x: x['success_rate'])
            top_5_employees = employee_results[:5]
            
            # Get user details for the top 5 employees — only sales_rep role
            user_ids = [UUID(emp['user_id']) for emp in top_5_employees]
            users_query = select(UserORM).where(
                UserORM.id.in_(user_ids),
                UserORM.company_id == company_id,
                UserORM.role == 'sales_rep',
            )
            users_result = await self.session.execute(users_query)
            users_list = users_result.scalars().all()
            
            # Create a mapping of user_id to user details
            users_map = {user.id: user for user in users_list}
            
            # Build final response with user names
            opportunities = []
            for emp in top_5_employees:
                user_id = UUID(emp['user_id'])
                user = users_map.get(user_id)
                
                # Format booked/qualified ratio
                booked_qualified_ratio = f"{emp['booked_leads']}/{emp['qualified_leads']}"
                
                opportunities.append({
                    'user_id': emp['user_id'],
                    'csr_name': f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                    'success_rate': emp['success_rate'],
                    'booked_qualified_ratio': booked_qualified_ratio,
                    'booked_leads': emp['booked_leads'],
                    'qualified_leads': emp['qualified_leads'],
                    'total_calls': emp['total_calls'],
                    # Top 3 objections with % Unbooked and # Unbooked/Qualified per objection
                    'most_coaching_need': emp['top_objections'],
                })
            
            return {
                'opportunities': opportunities,
                'total_count': len(opportunities),
                'start_date': start_dt.isoformat(),
                'end_date': end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting most coaching opportunities: {e}")
            raise e
    
    async def get_lead_to_sale_conversion(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get lead to sale conversion metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Total leads in date range
            total_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            total_count = total_leads.scalar() or 0
            
            # Converted leads in date range
            converted = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
            )
            converted_count = converted.scalar() or 0
            
            # Total revenue in date range
            revenue = await self.session.execute(
                select(func.sum(LeadORM.deal_size)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
            )
            total_revenue = revenue.scalar() or 0.0
            
            # Average days to conversion
            avg_days = await self.session.execute(
                select(func.avg(
                    func.extract('epoch', LeadORM.closed_at - LeadORM.created_at) / 86400
                )).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won",
                    LeadORM.closed_at.isnot(None)
                )
            )
            avg_days_val = avg_days.scalar() or 0.0
            
            conversion_rate = (converted_count / total_count * 100) if total_count > 0 else 0.0
            
            return {
                "total_leads": total_count,
                "converted_leads": converted_count,
                "conversion_rate": round(conversion_rate, 2),
                "avg_days_to_conversion": round(avg_days_val, 2),
                "total_revenue": round(total_revenue, 2),
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting lead to sale conversion: {e}")
            raise e
    
    async def get_emergencies_dropped(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get emergency/dropped calls metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Dropped/missed calls in date range
            dropped = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                )
            )
            dropped_count = dropped.scalar() or 0
            
            # Emergency calls (negative sentiment) in date range (exclude existing customer & service not offered)
            emergency = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sentiment_score.isnot(None),
                    CallAnalysisORM.sentiment_score < -0.5,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            emergency_count = emergency.scalar() or 0
            
            # Total calls in date range
            total = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_count = total.scalar() or 0
            
            drop_rate = (dropped_count / total_count * 100) if total_count > 0 else 0.0
            
            return {
                "dropped_calls": dropped_count,
                "emergency_calls": emergency_count,
                "drop_rate": round(drop_rate, 2),
                "avg_response_time": 0.0,  # Would need timing data
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting emergencies dropped: {e}")
            raise e
    
    async def get_company_performance(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get company performance metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Total revenue in date range
            revenue = await self.session.execute(
                select(func.sum(LeadORM.deal_size)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
            )
            total_revenue = revenue.scalar() or 0.0
            
            # Total leads in date range
            leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            total_leads = leads.scalar() or 0
            
            # Won leads in date range
            won = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
            )
            won_count = won.scalar() or 0
            
            conversion_rate = (won_count / total_leads * 100) if total_leads > 0 else 0.0
            avg_deal = (total_revenue / won_count) if won_count > 0 else 0.0
            
            # Active reps in date range
            reps = await self.session.execute(
                select(func.count(func.distinct(LeadORM.assigned_rep_id))).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.assigned_rep_id.isnot(None)
                )
            )
            active_reps = reps.scalar() or 0
            
            # Total calls in date range
            calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_calls = calls.scalar() or 0
            
            calls_per_rep = (total_calls / active_reps) if active_reps > 0 else 0.0
            
            return {
                "total_revenue": round(total_revenue, 2),
                "total_leads": total_leads,
                "conversion_rate": round(conversion_rate, 2),
                "avg_deal_size": round(avg_deal, 2),
                "active_reps": active_reps,
                "calls_per_rep": round(calls_per_rep, 2),
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting company performance: {e}")
            raise e
    
    async def get_calls_summary(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get calls summary metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            # Total calls in date range
            total = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_count = total.scalar() or 0
            
            # Answered calls in date range
            answered = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == False
                )
            )
            answered_count = answered.scalar() or 0
            
            # Missed calls in date range
            missed = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                )
            )
            missed_count = missed.scalar() or 0
            
            # Average duration in date range
            avg_duration = await self.session.execute(
                select(func.avg(CallORM.duration_seconds)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.duration_seconds.isnot(None)
                )
            )
            avg_duration_val = avg_duration.scalar() or 0.0
            
            # Total duration in date range
            total_duration = await self.session.execute(
                select(func.sum(CallORM.duration_seconds)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.duration_seconds.isnot(None)
                )
            )
            total_duration_val = total_duration.scalar() or 0
            
            # Calls today
            calls_today = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= today_start
                )
            )
            calls_today_count = calls_today.scalar() or 0
            
            return {
                "total_calls": total_count,
                "answered_calls": answered_count,
                "missed_calls": missed_count,
                "avg_duration": round(avg_duration_val, 2),
                "total_duration": total_duration_val,
                "calls_today": calls_today_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting calls summary: {e}")
            raise e
    
    async def get_bookings_summary(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get bookings summary metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            # Total bookings in date range
            total = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            total_count = total.scalar() or 0
            
            # Confirmed (won outcome) in date range
            confirmed = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                    AppointmentORM.outcome == "won"
                )
            )
            confirmed_count = confirmed.scalar() or 0
            
            # Pending in date range
            pending = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                    or_(AppointmentORM.outcome == "pending", AppointmentORM.outcome.is_(None))
                )
            )
            pending_count = pending.scalar() or 0
            
            # Cancelled in date range
            cancelled = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                    AppointmentORM.outcome.in_(["lost", "no_show"])
                )
            )
            cancelled_count = cancelled.scalar() or 0
            
            # Bookings today
            bookings_today = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= today_start
                )
            )
            bookings_today_count = bookings_today.scalar() or 0
            
            return {
                "total_bookings": total_count,
                "confirmed_bookings": confirmed_count,
                "pending_bookings": pending_count,
                "cancelled_bookings": cancelled_count,
                "bookings_today": bookings_today_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting bookings summary: {e}")
            raise e
    
    async def get_unbooked_leads(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get unbooked leads metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Count unbooked in date range
            unbooked = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "qualified_unbooked"
                )
            )
            unbooked_count = unbooked.scalar() or 0
            
            # Get leads in date range with contact card
            from sqlalchemy.orm import selectinload
            from app.infrastructure.database.models.contact import ContactCardORM
            
            leads = await self.session.execute(
                select(LeadORM)
                .options(selectinload(LeadORM.contact_card))
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "qualified_unbooked"
                ).order_by(LeadORM.created_at.desc()).limit(limit)
            )
            leads_list = leads.scalars().all()
            
            # Calculate average days unbooked
            now = datetime.now(timezone.utc)
            total_days = sum(
                (now - lead.created_at).days if lead.created_at else 0
                for lead in leads_list
            )
            avg_days = (total_days / len(leads_list)) if leads_list else 0.0
            
            # Build leads response with name and phone
            leads_response = []
            for lead in leads_list:
                lead_data = {
                    "id": str(lead.id),
                    "contact_card_id": str(lead.contact_card_id),
                    "status": lead.status,
                    "deal_size": lead.deal_size,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                }
                
                # Add name and phone from contact card
                if lead.contact_card:
                    first_name = lead.contact_card.first_name or ""
                    last_name = lead.contact_card.last_name or ""
                    lead_data["name"] = f"{first_name} {last_name}".strip() or None
                    lead_data["phone_number"] = lead.contact_card.primary_phone
                else:
                    lead_data["name"] = None
                    lead_data["phone_number"] = None
                
                leads_response.append(lead_data)
            
            return {
                "total_unbooked": unbooked_count,
                "qualified_unbooked": unbooked_count,
                "avg_days_unbooked": round(avg_days, 2),
                "leads": leads_response,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting unbooked leads: {e}")
            raise e
    
    async def get_pending_actions(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get pending actions metrics within date range."""
        try:
            from app.infrastructure.database.models.pending_action import PendingActionORM
            from app.domain.enums import PendingActionStatus
            
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Count pending actions by status in date range
            pending_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        PendingActionORM.company_id == company_id,
                        PendingActionORM.created_at >= start_dt,
                        PendingActionORM.created_at <= end_dt,
                        PendingActionORM.status == PendingActionStatus.PENDING.value
                    )
                )
            )
            pending_count = pending_query.scalar() or 0

            pending_base = and_(
                PendingActionORM.company_id == company_id,
                PendingActionORM.created_at >= start_dt,
                PendingActionORM.created_at <= end_dt,
                PendingActionORM.status == PendingActionStatus.PENDING.value,
            )
            action_type_lower = func.lower(PendingActionORM.action_type)

            from app.domain.pending_action_metrics import (
                CALLS_TO_MAKE_TYPES,
                APPOINTMENTS_TO_SCHEDULE_TYPES,
                FOLLOW_UPS_NEEDED_TYPES,
            )

            calls_condition = or_(
                action_type_lower.in_(list(CALLS_TO_MAKE_TYPES)),
                action_type_lower.like("%call_back%"),
            )
            appointments_type_condition = or_(
                action_type_lower.in_(list(APPOINTMENTS_TO_SCHEDULE_TYPES)),
                action_type_lower.like("%schedule%"),
            )
            follow_ups_type_condition = or_(
                action_type_lower.in_(list(FOLLOW_UPS_NEEDED_TYPES)),
                action_type_lower.like("follow_up%"),
                action_type_lower == "follow_up",
                action_type_lower.like("%follow_up%"),
            )

            calls_to_make_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(pending_base, calls_condition)
                )
            )
            calls_to_make = calls_to_make_query.scalar() or 0

            appointments_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        pending_base,
                        ~calls_condition,
                        appointments_type_condition,
                    )
                )
            )
            appointments_to_schedule = appointments_query.scalar() or 0

            follow_ups_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        pending_base,
                        ~calls_condition,
                        ~appointments_type_condition,
                        follow_ups_type_condition,
                    )
                )
            )
            follow_ups_needed = follow_ups_query.scalar() or 0

            return {
                "total_pending": pending_count,
                "follow_ups_needed": follow_ups_needed,
                "calls_to_make": calls_to_make,
                "appointments_to_schedule": appointments_to_schedule,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting pending actions: {e}")
            raise e
    
    async def get_conversions_pending_to_booked(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get conversions from pending to booked within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Booked appointments in date range
            booked_appts = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            booked_appointments_count = booked_appts.scalar() or 0
            
            # Booked leads in date range (status=qualified_booked or deal_status=booked, case-insensitive)
            booked_leads_result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(
                        LeadORM.status == "qualified_booked",
                        func.lower(LeadORM.deal_status) == "booked",
                    ),
                )
            )
            booked_leads_count = booked_leads_result.scalar() or 0
            
            # Combined converted = appointments + booked leads
            converted_count = booked_appointments_count + booked_leads_count
            
            # Total leads in date range
            leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            leads_count = leads.scalar() or 0
            
            conversion_rate = (converted_count / leads_count * 100) if leads_count > 0 else 0.0
            
            return {
                "converted_count": converted_count,
                "booked_appointments": booked_appointments_count,
                "booked_leads": booked_leads_count,
                "conversion_rate": round(conversion_rate, 2),
                "avg_days_to_book": 0.0,  # Would need additional tracking
                "period_start": start_dt.isoformat(),
                "period_end": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting conversions pending to booked: {e}")
            raise e
    
    async def get_objections_summary(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get objections summary within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get all analyses with objections in date range (exclude existing customer & service not offered)
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections != None,
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            analyses_list = analyses.scalars().all()
            
            # Count objections by type (after classification)
            objections_by_type: Dict[str, int] = {}
            total_objections = 0

            for analysis in analyses_list:
                if analysis.objections:
                    # Classify objections before counting
                    classified = self._classify_objections_in_analysis(analysis)
                    for obj in classified:
                        objections_by_type[obj] = objections_by_type.get(obj, 0) + 1
                        total_objections += 1
            
            top_objection = max(objections_by_type, key=objections_by_type.get) if objections_by_type else ""
            
            return {
                "total_objections": total_objections,
                "unique_objection_types": len(objections_by_type),
                "top_objection": top_objection,
                "objections_by_type": objections_by_type,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting objections summary: {e}")
            raise e
    
    async def get_objection_calls(
        self,
        company_id: UUID,
        objection_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get calls with specific objection type within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get analyses with this objection in date range (exclude existing customer & service not offered)
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    text(f":objection = ANY({CallAnalysisORM.__table__.name}.objections)").bindparams(bindparam('objection', objection_type)),
                    _metrics_exclude_existing_and_service_not_offered(),
                ).order_by(CallAnalysisORM.created_at.desc()).limit(limit)
            )
            analyses_list = analyses.scalars().all()
            
            # Count total
            total = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    text(f":objection = ANY({CallAnalysisORM.__table__.name}.objections)").bindparams(bindparam('objection', objection_type)),
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            total_count = total.scalar() or 0
            
            calls = []
            for analysis in analyses_list:
                call = await self.session.execute(
                    select(CallORM).where(CallORM.id == analysis.call_id)
                )
                call_obj = call.scalar_one_or_none()
                
                if call_obj:
                    calls.append({
                        "call_id": str(call_obj.id),
                        "phone_number": call_obj.phone_number,
                        "created_at": call_obj.created_at.isoformat() if call_obj.created_at else None,
                        "duration_seconds": call_obj.duration_seconds,
                        "objection_texts": analysis.objection_texts or [],
                        "summary": analysis.summary,
                    })
            
            return {
                "objection_type": objection_type,
                "total_calls": total_count,
                "calls": calls,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting objection calls: {e}")
            raise e
    
    async def get_auto_queued_leads(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get auto-queued leads for CSR within date range."""
        import traceback
        try:
            from sqlalchemy.orm import selectinload
            from app.infrastructure.database.models.contact import ContactCardORM
            from app.infrastructure.database.models.call import CallORM
            from app.infrastructure.database.models.analysis import CallAnalysisORM

            start_dt, end_dt = self._get_date_range(start_date, end_date)

            # Get missed calls in date range with contact_card loaded
            missed_calls_query = await self.session.execute(
                select(CallORM)
                .options(selectinload(CallORM.contact_card))
                .where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True,
                )
                .order_by(CallORM.created_at.desc())
                .limit(limit)
            )
            missed_calls = missed_calls_query.scalars().all()

            # Fetch lead info for calls that have lead_id
            lead_ids = [c.lead_id for c in missed_calls if c.lead_id]
            leads_map: Dict[str, Any] = {}
            if lead_ids:
                leads_result = await self.session.execute(
                    select(LeadORM).where(LeadORM.id.in_(lead_ids))
                )
                for lead in leads_result.scalars().all():
                    leads_map[str(lead.id)] = lead

            # Fetch service_requested from call_analyses
            call_ids = [c.id for c in missed_calls]
            service_map: Dict[str, str] = {}
            if call_ids:
                ca_rows = await self.session.execute(
                    select(CallAnalysisORM.call_id, CallAnalysisORM.service_requested)
                    .where(
                        CallAnalysisORM.call_id.in_(call_ids),
                        CallAnalysisORM.service_requested.isnot(None),
                        CallAnalysisORM.service_requested != "",
                    )
                )
                for row in ca_rows.all():
                    service_map[str(row.call_id)] = row.service_requested

            # Count leads by status from missed calls
            hot_count = 0
            warm_count = 0
            new_count = 0
            for c in missed_calls:
                if c.lead_id and str(c.lead_id) in leads_map:
                    status = leads_map[str(c.lead_id)].status
                    if status == "hot":
                        hot_count += 1
                    elif status == "warm":
                        warm_count += 1
                    elif status == "new":
                        new_count += 1

            # Build response
            leads_data = []
            for call in missed_calls:
                lead = leads_map.get(str(call.lead_id)) if call.lead_id else None
                call_dict = {
                    "id": str(call.id),
                    "contact_card_id": str(call.contact_card_id) if call.contact_card_id else None,
                    "lead_id": str(call.lead_id) if call.lead_id else None,
                    "phone_number": call.phone_number,
                    "call_type": call.call_type,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "service_requested": service_map.get(str(call.id)),
                    "status": lead.status if lead else None,
                    "deal_size": lead.deal_size if lead else None,
                    "assigned_rep_id": str(lead.assigned_rep_id) if lead and lead.assigned_rep_id else None,
                }
                # Add contact_card info if available
                if call.contact_card:
                    call_dict["contact_card"] = {
                        "id": str(call.contact_card.id),
                        "first_name": call.contact_card.first_name,
                        "last_name": call.contact_card.last_name,
                        "primary_phone": call.contact_card.primary_phone,
                        "email": call.contact_card.email,
                        "address": call.contact_card.address,
                        "city": call.contact_card.city,
                        "state": call.contact_card.state,
                    }
                leads_data.append(call_dict)

            return {
                "total": len(missed_calls),
                "hot_leads": hot_count,
                "warm_leads": warm_count,
                "new_leads": new_count,
                "leads": leads_data,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting auto-queued leads: {e}")
            traceback.print_exc()
            raise e
    
    async def get_csr_profile(
        self,
        user_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive CSR profile with all metrics, rank, and coaching insights.
        
        Args:
            user_id: CSR user ID
            start_date: Start date for metrics (defaults to 30 days ago)
            end_date: End date for metrics (defaults to today)
            
        Returns:
            Dictionary with all CSR profile data
        """
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get user info
            user_result = await self.session.execute(
                select(UserORM).where(UserORM.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Allow non-CSR callers for /metrics/csr/{user_id}/profile (e.g. exec viewing any user).
            # if user.role != UserRole.CSR.value:
            #     raise ValueError(f"User {user_id} is not a CSR")
            
            if not user.company_id:
                raise ValueError(f"User {user_id} has no company_id")
            
            company_id = user.company_id
            user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "CSR Agent"
            
            # Get all CSRs in the company for ranking
            all_csrs_result = await self.session.execute(
                select(UserORM.id).where(
                    UserORM.company_id == company_id,
                    UserORM.role == UserRole.CSR.value,
                    UserORM.is_active == True
                )
            )
            all_csr_ids = [row[0] for row in all_csrs_result.all()]
            total_csrs = len(all_csr_ids)
            
            # ===== CALL METRICS =====
            # Total calls
            total_calls_result = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_calls = total_calls_result.scalar() or 0
            
            # Calls answered
            calls_answered_result = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == False,
                )
            )
            calls_answered = calls_answered_result.scalar() or 0
            
            # Missed calls
            missed_calls = total_calls - calls_answered
            calls_answered_percentage = (calls_answered / total_calls * 100) if total_calls > 0 else 0.0
            
            # Determine missed calls status
            missed_calls_percentage = (missed_calls / total_calls * 100) if total_calls > 0 else 0.0
            if missed_calls_percentage > 10:
                missed_calls_status = "high"
            elif missed_calls_percentage > 5:
                missed_calls_status = "medium"
            else:
                missed_calls_status = "low"
            
            # Average response time (in seconds)
            avg_response_time_result = await self.session.execute(
                select(
                    func.avg(
                        func.extract('epoch', CallORM.answered_at - CallORM.created_at)
                    )
                ).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == False,
                    CallORM.answered_at.isnot(None),
                )
            )
            avg_response_time = avg_response_time_result.scalar() or 0.0
            
            # Response time status
            response_time_target = 15.0
            if avg_response_time <= response_time_target:
                response_time_status = "on_target"
            elif avg_response_time <= response_time_target * 1.5:
                response_time_status = "above_target"
            else:
                response_time_status = "below_target"
            
            # ===== LEAD METRICS =====
            # Total leads (leads assigned to this CSR)
            total_leads_result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.assigned_rep_id == user_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            total_leads = total_leads_result.scalar() or 0
            
            # Qualified leads (from call_analyses: qualification_status in hot/warm/cold)
            qualified_leads_result = await self.session.execute(
                select(func.count(func.distinct(CallAnalysisORM.id)))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    func.lower(CallAnalysisORM.qualification_status).in_(["hot", "warm", "cold"]),
                )
            )
            qualified_leads = qualified_leads_result.scalar() or 0
            
            # ===== APPOINTMENT METRICS =====
            # Booked appointments (from call_analyses where booking_status = 'booked')
            booked_appointments_result = await self.session.execute(
                select(func.count(CallAnalysisORM.id))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    func.lower(CallAnalysisORM.booking_status) == "booked",
                )
            )
            booked_appointments = booked_appointments_result.scalar() or 0

            # Booking rate: booked appointments / qualified leads
            booking_rate = (booked_appointments / qualified_leads * 100) if qualified_leads > 0 else 0.0
            
            # ===== CONVERSION RATE =====
            # Conversion rate: appointments with outcome='won' / qualified_leads
            won_appointments_result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.assigned_rep_id == user_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                    AppointmentORM.outcome == 'won',
                )
            )
            won_appointments = won_appointments_result.scalar() or 0
            conversion_rate = (won_appointments / qualified_leads * 100) if qualified_leads > 0 else 0.0
            
            # ===== RANK CALCULATION =====
            # Calculate booking rates for all CSRs to determine rank
            csr_booking_rates = {}
            for csr_id in all_csr_ids:
                csr_qualified_result = await self.session.execute(
                    select(func.count(LeadORM.id)).where(
                        LeadORM.assigned_rep_id == csr_id,
                        LeadORM.created_at >= start_dt,
                        LeadORM.created_at <= end_dt,
                        or_(
                            LeadORM.status.like('qualified_%'),
                            LeadORM.deal_status == 'qualified'
                        )
                    )
                )
                csr_qualified = csr_qualified_result.scalar() or 0
                
                csr_appointments_result = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.assigned_rep_id == csr_id,
                        AppointmentORM.created_at >= start_dt,
                        AppointmentORM.created_at <= end_dt,
                    )
                )
                csr_appointments = csr_appointments_result.scalar() or 0
                
                csr_booking_rate = (csr_appointments / csr_qualified * 100) if csr_qualified > 0 else 0.0
                csr_booking_rates[csr_id] = csr_booking_rate
            
            # Sort CSRs by booking rate (descending) and find rank
            sorted_csrs = sorted(csr_booking_rates.items(), key=lambda x: x[1], reverse=True)
            rank = None
            for idx, (csr_id, rate) in enumerate(sorted_csrs, 1):
                if csr_id == user_id:
                    rank = idx
                    break
            
            # ===== COACHING INSIGHTS =====
            coaching_insights = []
            
            # 1. Objection Handling
            # Get objection handling improvement (exclude existing customer & service not offered)
            current_month_objections = await self.session.execute(
                select(func.count(CallAnalysisORM.id))
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            current_objections = current_month_objections.scalar() or 0
            
            # Compare with previous period
            prev_start_dt = start_dt - (end_dt - start_dt)
            prev_objections_result = await self.session.execute(
                select(func.count(CallAnalysisORM.id))
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= prev_start_dt,
                    CallAnalysisORM.created_at < start_dt,
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            prev_objections = prev_objections_result.scalar() or 0
            
            if prev_objections > 0:
                improvement = ((prev_objections - current_objections) / prev_objections) * 100
                if improvement > 0:
                    coaching_insights.append({
                        "type": "objection_handling",
                        "title": "Objection Handling",
                        "message": f"You've improved your handling of pricing objections by {improvement:.0f}% this month. Keep up the great work!",
                        "status": "positive",
                        "improvement_percentage": improvement
                    })
            
            # 2. Script Adherence
            # Check SOP compliance (exclude existing customer & service not offered)
            avg_sop_score_result = await self.session.execute(
                select(func.avg(CallAnalysisORM.sop_compliance_score)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                    _metrics_exclude_existing_and_service_not_offered(),
                ).join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            )
            avg_sop_score = avg_sop_score_result.scalar() or 0.0
            
            if avg_sop_score < 80:
                coaching_insights.append({
                    "type": "script_adherence",
                    "title": "Script Adherence",
                    "message": "Focus on following the booking script more closely, especially during peak hours.",
                    "status": "recommendation",
                    "improvement_percentage": None
                })
            
            # 3. Response Time
            if avg_response_time > response_time_target:
                coaching_insights.append({
                    "type": "response_time",
                    "title": "Response Time",
                    "message": f"Your average response time is above target. Try to answer calls within the first 3 rings.",
                    "status": "warning",
                    "improvement_percentage": None
                })
            
            # 4. Lead Qualification Accuracy
            # Compare qualification_status from analysis with actual lead status (exclude existing customer & service not offered)
            # Qualified statuses: hot, cold, warm, qualified
            qualified_statuses = ['hot', 'cold', 'warm', 'qualified']
            qualification_accuracy_result = await self.session.execute(
                select(
                    func.count(CallAnalysisORM.id),
                    func.sum(case((
                        func.lower(CallAnalysisORM.qualification_status).in_(
                            [s.lower() for s in qualified_statuses]
                        ), 1), else_=0))
                ).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.lead_id.isnot(None),
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.qualification_status.isnot(None),
                    _metrics_exclude_existing_and_service_not_offered(),
                ).join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            )
            qual_result = qualification_accuracy_result.first()
            total_qualifications = qual_result[0] or 0
            qualified_count = qual_result[1] or 0
            
            if total_qualifications > 0:
                qualification_accuracy = (qualified_count / total_qualifications) * 100
                if qualification_accuracy >= 90:
                    coaching_insights.append({
                        "type": "lead_qualification",
                        "title": "Lead Qualification",
                        "message": f"Your lead qualification accuracy is {qualification_accuracy:.0f}%, one of the highest on the team!",
                        "status": "positive",
                        "improvement_percentage": None
                    })
            
            # Build response
            return {
                "user_id": str(user_id),
                "name": user_name,
                "email": user.email,
                "role": user.role,
                "rank": rank,
                "total_csrs": total_csrs,
                "total_calls": total_calls,
                "calls_answered": calls_answered,
                "calls_answered_percentage": round(calls_answered_percentage, 1),
                "missed_calls": missed_calls,
                "missed_calls_status": missed_calls_status,
                "booked_appointments": booked_appointments,
                "total_leads": total_leads,
                "qualified_leads": qualified_leads,
                "booking_rate": round(booking_rate, 1),
                "avg_response_time": round(avg_response_time, 1),
                "response_time_status": response_time_status,
                "executive_view": {
                    "booking_rate": round(booking_rate, 1),
                    "conversion_rate": round(conversion_rate, 1),
                    "calls_answered": calls_answered,
                    "total_calls": total_calls,
                    "avg_response_time": round(avg_response_time, 1),
                    "response_time_target": response_time_target,
                },
                "coaching_insights": coaching_insights,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error getting CSR profile: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def get_sales_rep_kpi(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get sales rep KPIs: win_rate, first_touch_win_rate, follow_up_win_rate,
        attendance, average_deal_size, average_follow_up_per_deal.
        """
        try:
            if user_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("user_id must belong to a user with company_id")
                company_id = user.company_id
            elif not company_id:
                raise ValueError("Either company_id or user_id is required")

            start_dt, end_dt = self._get_date_range(start_date, end_date)

            appointment_filters = [
                AppointmentORM.company_id == company_id,
                AppointmentORM.scheduled_start >= start_dt,
                AppointmentORM.scheduled_start <= end_dt,
            ]
            lead_closed_dt = func.coalesce(LeadORM.closed_at, LeadORM.updated_at)
            lead_filters = [
                LeadORM.company_id == company_id,
                lead_closed_dt.isnot(None),
                lead_closed_dt.between(start_dt, end_dt),
            ]
            if user_id:
                appointment_filters.append(AppointmentORM.assigned_rep_id == user_id)
                lead_filters.append(LeadORM.assigned_rep_id == user_id)

            # Win rate: appointments with outcome=won / total appointments with resolved outcome
            total_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*appointment_filters)
            )
            total_appts = total_appointments.scalar() or 0
            won_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_filters, AppointmentORM.outcome == "won"
                )
            )
            won_appts = won_appointments.scalar() or 0
            resolved = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_filters,
                    AppointmentORM.outcome.isnot(None),
                    AppointmentORM.outcome.in_(["won", "lost", "no_show"]),
                )
            )
            resolved_count = resolved.scalar() or 0
            win_rate = (won_appts / resolved_count) if resolved_count > 0 else 0.0

            # First-touch vs follow-up win rates: join appointments -> calls -> call_analyses
            from sqlalchemy import join

            appt_call_join = join(
                AppointmentORM,
                CallORM,
                AppointmentORM.interaction_id == CallORM.id,
            )
            appt_call_analysis_join = join(
                appt_call_join,
                CallAnalysisORM,
                CallORM.id == CallAnalysisORM.call_id,
            )
            first_touch_base = (
                select(func.count(AppointmentORM.id))
                .select_from(appt_call_analysis_join)
                .where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.scheduled_start >= start_dt,
                    AppointmentORM.scheduled_start <= end_dt,
                    CallAnalysisORM.detected_call_type == "fresh_sales",
                )
            )
            if user_id:
                first_touch_base = first_touch_base.where(
                    AppointmentORM.assigned_rep_id == user_id
                )
            first_touch_won = await self.session.execute(
                first_touch_base.where(AppointmentORM.outcome == "won")
            )
            first_touch_won_count = first_touch_won.scalar() or 0
            first_touch_total = await self.session.execute(first_touch_base)
            first_touch_total_count = first_touch_total.scalar() or 0
            first_touch_win_rate = (
                (first_touch_won_count / first_touch_total_count)
                if first_touch_total_count > 0
                else 0.0
            )

            follow_up_base = (
                select(func.count(AppointmentORM.id))
                .select_from(appt_call_analysis_join)
                .where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.scheduled_start >= start_dt,
                    AppointmentORM.scheduled_start <= end_dt,
                    CallAnalysisORM.detected_call_type == "follow_up_inquiry",
                )
            )
            if user_id:
                follow_up_base = follow_up_base.where(
                    AppointmentORM.assigned_rep_id == user_id
                )
            follow_up_won = await self.session.execute(
                follow_up_base.where(AppointmentORM.outcome == "won")
            )
            follow_up_won_count = follow_up_won.scalar() or 0
            follow_up_total = await self.session.execute(follow_up_base)
            follow_up_total_count = follow_up_total.scalar() or 0
            follow_up_win_rate = (
                (follow_up_won_count / follow_up_total_count)
                if follow_up_total_count > 0
                else 0.0
            )

            # Attendance: 1 - no_show rate (appointments that were not no_show)
            no_show_count_result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_filters, AppointmentORM.outcome == "no_show"
                )
            )
            no_show_count = no_show_count_result.scalar() or 0
            attendance = (
                ((total_appts - no_show_count) / total_appts) if total_appts > 0 else 0.0
            )

            # Average deal size: closed_won leads with actual deal values
            avg_deal_result = await self.session.execute(
                select(func.avg(LeadORM.deal_size)).where(
                    *lead_filters,
                    LeadORM.status == "closed_won",
                    LeadORM.deal_size.isnot(None),
                    LeadORM.deal_size > 0,
                )
            )
            average_deal_size = float(avg_deal_result.scalar() or 0.0)

            # Average follow-up per deal: avg number of follow-up touches per closed_won lead
            # (e.g. count calls with follow_up_required or follow_up_inquiry per lead, then avg)
            won_lead_ids_result = await self.session.execute(
                select(LeadORM.id).where(
                    *lead_filters, LeadORM.status == "closed_won"
                )
            )
            won_lead_ids = [r[0] for r in won_lead_ids_result.all()]
            average_follow_up_per_deal = 0.0
            if won_lead_ids:
                follow_up_calls = await self.session.execute(
                    select(func.count(CallAnalysisORM.id))
                    .select_from(CallORM)
                    .join(CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id)
                    .where(
                        CallORM.company_id == company_id,
                        CallORM.lead_id.in_(won_lead_ids),
                        CallORM.created_at >= start_dt,
                        CallORM.created_at <= end_dt,
                        CallAnalysisORM.follow_up_required == True,
                    )
                )
                follow_up_total_touches = follow_up_calls.scalar() or 0
                average_follow_up_per_deal = (
                    follow_up_total_touches / len(won_lead_ids)
                    if won_lead_ids
                    else 0.0
                )

            return {
                "win_rate": round(win_rate, 4),
                "first_touch_win_rate": round(first_touch_win_rate, 4),
                "follow_up_win_rate": round(follow_up_win_rate, 4),
                "attendance": round(attendance, 4),
                "average_deal_size": round(average_deal_size, 2),
                "average_follow_up_per_deal": round(average_follow_up_per_deal, 2),
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting sales rep KPI: {e}")
            raise e

    async def get_strengths_and_issues(
        self,
        user_id: UUID,
        company_id: UUID,
        shunya_profile: Dict[str, Any],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Build unified strengths & issues response by combining Shunya coaching
        profile with our DB performance metrics.
        """
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)

            # --- DB metrics: calls ---
            total_calls_q = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_calls = total_calls_q.scalar() or 0

            answered_q = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == False,
                )
            )
            calls_answered = answered_q.scalar() or 0
            missed_calls = total_calls - calls_answered
            calls_answered_pct = (calls_answered / total_calls * 100) if total_calls > 0 else 0.0
            missed_pct = (missed_calls / total_calls * 100) if total_calls > 0 else 0.0
            missed_status = "high" if missed_pct > 10 else ("medium" if missed_pct > 5 else "low")

            # Avg response time
            resp_time_q = await self.session.execute(
                select(
                    func.avg(func.extract('epoch', CallORM.answered_at - CallORM.created_at))
                ).where(
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == False,
                    CallORM.answered_at.isnot(None),
                )
            )
            avg_response_time = resp_time_q.scalar() or 0.0
            rt_target = 15.0
            rt_status = "on_target" if avg_response_time <= rt_target else (
                "above_target" if avg_response_time <= rt_target * 1.5 else "below_target"
            )

            # --- Leads & appointments ---
            qualified_q = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.assigned_rep_id == user_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(LeadORM.status.like('qualified_%'), LeadORM.deal_status == 'qualified'),
                )
            )
            qualified_leads = qualified_q.scalar() or 0

            booked_appt_q = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.assigned_rep_id == user_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            booked_appointments = booked_appt_q.scalar() or 0

            booked_calls_q = await self.session.execute(
                select(func.count(CallAnalysisORM.id))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallAnalysisORM.booking_status.isnot(None),
                    func.lower(CallAnalysisORM.booking_status) == "booked",
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            booked_calls = booked_calls_q.scalar() or 0
            total_booked = booked_appointments + booked_calls
            booking_rate = (total_booked / qualified_leads * 100) if qualified_leads > 0 else 0.0

            # Conversion rate
            won_q = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.assigned_rep_id == user_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                    AppointmentORM.outcome == 'won',
                )
            )
            won = won_q.scalar() or 0
            conversion_rate = (won / qualified_leads * 100) if qualified_leads > 0 else 0.0

            # SOP compliance average
            sop_q = await self.session.execute(
                select(func.avg(CallAnalysisORM.sop_compliance_score))
                .select_from(CallAnalysisORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            avg_sop = sop_q.scalar() or 0.0

            # Rank among CSRs — single batched query instead of N+1
            all_csrs_q = await self.session.execute(
                select(UserORM.id).where(
                    UserORM.company_id == company_id,
                    UserORM.is_active == True,
                    UserORM.role.in_([UserRole.CSR.value, UserRole.SALES_REP.value]),
                )
            )
            all_csr_ids = [r[0] for r in all_csrs_q.all()]
            total_csrs = len(all_csr_ids)

            # Batch: qualified leads per CSR
            qual_q = await self.session.execute(
                select(
                    LeadORM.assigned_rep_id,
                    func.count(LeadORM.id).label("cnt"),
                ).where(
                    LeadORM.assigned_rep_id.in_(all_csr_ids),
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(LeadORM.status.like('qualified_%'), LeadORM.deal_status == 'qualified'),
                ).group_by(LeadORM.assigned_rep_id)
            )
            csr_qual_map = {row.assigned_rep_id: row.cnt for row in qual_q}

            # Batch: appointments per CSR
            appt_q = await self.session.execute(
                select(
                    AppointmentORM.assigned_rep_id,
                    func.count(AppointmentORM.id).label("cnt"),
                ).where(
                    AppointmentORM.assigned_rep_id.in_(all_csr_ids),
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                ).group_by(AppointmentORM.assigned_rep_id)
            )
            csr_appt_map = {row.assigned_rep_id: row.cnt for row in appt_q}

            csr_booking_rates = {}
            for csr_id in all_csr_ids:
                csr_qual = csr_qual_map.get(csr_id, 0)
                csr_appt = csr_appt_map.get(csr_id, 0)
                csr_booking_rates[csr_id] = (csr_appt / csr_qual * 100) if csr_qual > 0 else 0.0

            sorted_csrs = sorted(csr_booking_rates.items(), key=lambda x: x[1], reverse=True)
            rank = None
            for idx, (csr_id, _) in enumerate(sorted_csrs, 1):
                if csr_id == user_id:
                    rank = idx
                    break

            # Top 3 objection-based coaching needs
            from sqlalchemy import join as sa_join
            call_analysis_join = sa_join(CallAnalysisORM, CallORM, CallAnalysisORM.call_id == CallORM.id)
            analyses_q = await self.session.execute(
                select(
                    CallAnalysisORM.qualification_status,
                    CallAnalysisORM.booking_status,
                    CallAnalysisORM,
                ).select_from(call_analysis_join).where(
                    CallORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            obj_stats: Dict[str, Dict[str, int]] = {}
            for row in analyses_q.all():
                analysis = row[2]
                is_qualified = row.qualification_status and row.qualification_status.lower() in ['hot', 'cold', 'warm', 'qualified']
                is_booked = row.booking_status and row.booking_status.lower() == 'booked'
                if analysis and analysis.objections:
                    for obj in self._classify_objections_in_analysis(analysis):
                        obj = str(obj).strip()
                        if not obj:
                            continue
                        if obj not in obj_stats:
                            obj_stats[obj] = {'count': 0, 'qualified': 0, 'booked': 0}
                        obj_stats[obj]['count'] += 1
                        if is_qualified:
                            obj_stats[obj]['qualified'] += 1
                        if is_booked:
                            obj_stats[obj]['booked'] += 1

            top_objections = []
            for obj, s in sorted(obj_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:3]:
                unbooked = s['qualified'] - s['booked']
                top_objections.append({
                    "objection": obj,
                    "pct_unbooked": round((unbooked / s['qualified'] * 100) if s['qualified'] > 0 else 0.0, 1),
                    "unbooked_qualified_ratio": f"{unbooked}/{s['qualified']}",
                    "unbooked_count": unbooked,
                    "qualified_count": s['qualified'],
                })

            # Booking rate trend (last 4 weeks)
            booking_rate_trend = []
            for i in range(4):
                w_end = end_dt - timedelta(weeks=i)
                w_start = w_end - timedelta(weeks=1)
                wq = await self.session.execute(
                    select(func.count(LeadORM.id)).where(
                        LeadORM.assigned_rep_id == user_id,
                        LeadORM.created_at >= w_start,
                        LeadORM.created_at <= w_end,
                        or_(LeadORM.status.like('qualified_%'), LeadORM.deal_status == 'qualified'),
                    )
                )
                w_qual = wq.scalar() or 0
                wa = await self.session.execute(
                    select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.assigned_rep_id == user_id,
                        AppointmentORM.created_at >= w_start,
                        AppointmentORM.created_at <= w_end,
                    )
                )
                w_booked = wa.scalar() or 0
                booking_rate_trend.append({
                    "period_start": w_start.isoformat(),
                    "period_end": w_end.isoformat(),
                    "booking_rate": round((w_booked / w_qual * 100) if w_qual > 0 else 0.0, 1),
                    "booked": w_booked,
                    "qualified": w_qual,
                })
            booking_rate_trend.reverse()

            # --- Build unified response ---
            def _parse_severity(sv: Any) -> Any:
                if isinstance(sv, dict) and sv:
                    return {"high": sv.get("high", 0), "medium": sv.get("medium", 0), "low": sv.get("low", 0)}
                return None

            def _parse_bucket(b: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "category": b.get("category", ""),
                    "count": b.get("count", 0),
                    "severity_distribution": _parse_severity(b.get("severity_distribution")),
                    "representative_examples": b.get("representative_examples", []),
                    "related_sop_metrics": b.get("related_sop_metrics", []),
                    "latest_occurrence": b.get("latest_occurrence"),
                }

            return {
                "rep_id": shunya_profile.get("rep_id", str(user_id)),
                "rep_name": shunya_profile.get("rep_name", ""),
                "company_id": shunya_profile.get("company_id", str(company_id)),
                "window_start": shunya_profile.get("window_start", start_dt.isoformat()),
                "window_end": shunya_profile.get("window_end", end_dt.isoformat()),
                "calls_analyzed": shunya_profile.get("calls_analyzed", 0),
                "top_weaknesses": [_parse_bucket(b) for b in shunya_profile.get("top_weaknesses", [])],
                "top_strengths": [_parse_bucket(b) for b in shunya_profile.get("top_strengths", [])],
                "all_weakness_buckets": [_parse_bucket(b) for b in shunya_profile.get("all_weakness_buckets", [])],
                "all_strength_buckets": [_parse_bucket(b) for b in shunya_profile.get("all_strength_buckets", [])],
                "db_performance_metrics": {
                    "total_calls": total_calls,
                    "calls_answered": calls_answered,
                    "calls_answered_percentage": round(calls_answered_pct, 1),
                    "missed_calls": missed_calls,
                    "missed_calls_status": missed_status,
                    "booking_rate": round(booking_rate, 1),
                    "conversion_rate": round(conversion_rate, 1),
                    "avg_response_time": round(avg_response_time, 1),
                    "response_time_status": rt_status,
                    "avg_sop_compliance_score": round(float(avg_sop), 1),
                    "qualified_leads": qualified_leads,
                    "booked_appointments": booked_appointments,
                    "rank": rank,
                    "total_csrs": total_csrs,
                    "top_objections": top_objections,
                    "booking_rate_trend": booking_rate_trend,
                },
                "calculated_at": shunya_profile.get("calculated_at", datetime.utcnow().isoformat()),
                "data_sources": ["shunya_coaching_profile", "otto_db_metrics"],
            }
        except Exception as e:
            logger.error(f"Error getting strengths and issues: {e}")
            raise