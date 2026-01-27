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
            end_dt = datetime.combine(end_date, datetime.max.time())
        else:
            end_dt = datetime.utcnow()
        
        if start_date:
            start_dt = datetime.combine(start_date, datetime.min.time())
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
            if user_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("Either provide company_id, or provide user_id that belongs to a user with a company_id")
                company_id = user.company_id
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
            # Count leads with deal_status = "qualified" OR status in qualified statuses
            # This handles both the deal_status field and the status field for qualification
            qualified_leads_filters = lead_filters + [
                or_(
                    LeadORM.deal_status == "qualified",
                    LeadORM.status.in_(["qualified_booked", "qualified_unbooked", "qualified_service_not_offered"])
                )
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
            
            # Conversion rate (closed_won / total leads) in date range
            won_leads_filters = lead_filters + [LeadORM.status == "closed_won"]
            won_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(*won_leads_filters)
            )
            won_count = won_leads.scalar() or 0
            conversion_rate = (won_count / total_leads_count * 100) if total_leads_count > 0 else 0.0
            
            # Total revenue in date range
            revenue_filters = lead_filters + [LeadORM.status == "closed_won"]
            total_revenue = await self.session.execute(
                select(func.sum(LeadORM.deal_size)).where(*revenue_filters)
            )
            revenue = total_revenue.scalar() or 0.0
            
            return {
                "total_leads": total_leads_count,
                "active_leads": active_leads_count,
                "qualified_leads": qualified_leads_count,
                "total_calls": total_calls_count,
                "missed_calls": missed_calls_count,
                "total_appointments": total_appointments_count,
                "conversion_rate": round(conversion_rate, 2),
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
            
            return {
                "missed_calls": missed_count,
                "total_calls": total_count,
                "miss_rate": round(miss_rate, 2),
                "recent_missed": [
                    {
                        "id": str(call.id),
                        "phone_number": call.phone_number,
                        "created_at": call.created_at.isoformat() if call.created_at else None,
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
    ) -> Dict[str, Any]:
        """Get booking rate improvement metrics comparing current period to previous period."""
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
            
            # Calculate period length
            period_length = (end_dt - start_dt).days
            previous_start = start_dt - timedelta(days=period_length)
            previous_end = start_dt
            
            # Optional user scoping:
            # - Appointments: by assigned_rep_id
            # - Leads: by assigned_rep_id
            appointment_scope = [AppointmentORM.company_id == company_id]
            lead_scope = [LeadORM.company_id == company_id]
            if user_id:
                appointment_scope.append(AppointmentORM.assigned_rep_id == user_id)
                lead_scope.append(LeadORM.assigned_rep_id == user_id)

            # Current period bookings
            current_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            current_count = current_bookings.scalar() or 0
            
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
            
            # Previous period bookings
            previous_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    *appointment_scope,
                    AppointmentORM.created_at >= previous_start,
                    AppointmentORM.created_at < previous_end,
                )
            )
            previous_count = previous_bookings.scalar() or 0
            
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
            
            current_rate = (current_count / current_qualified_count * 100) if current_qualified_count > 0 else 0.0
            previous_rate = (previous_count / previous_qualified_count * 100) if previous_qualified_count > 0 else 0.0
            improvement = current_rate - previous_rate
            
            return {
                "current_rate": round(current_rate, 2),
                "previous_rate": round(previous_rate, 2),
                "improvement_percentage": round(improvement, 2),
                "total_bookings": current_count,
                "total_qualified": current_qualified_count,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "previous_period_start": previous_start.isoformat(),
                "previous_period_end": previous_end.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting booking rate improvement: {e}")
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
            
            # Get all analyses with objections in date range
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections != None,
                    func.array_length(CallAnalysisORM.objections, 1) > 0
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
            
            # Get analyses with low SOP compliance in date range
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
                    CallAnalysisORM.sop_compliance_score < 0.7
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
                    CallAnalysisORM.sop_compliance_score < 0.7
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
            
            # Emergency calls (negative sentiment) in date range
            emergency = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sentiment_score.isnot(None),
                    CallAnalysisORM.sentiment_score < -0.5
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
            
            # Count completed actions in date range
            completed_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        PendingActionORM.company_id == company_id,
                        PendingActionORM.created_at >= start_dt,
                        PendingActionORM.created_at <= end_dt,
                        PendingActionORM.status == PendingActionStatus.COMPLETED.value
                    )
                )
            )
            completed_count = completed_query.scalar() or 0
            
            # Count converted actions in date range
            converted_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        PendingActionORM.company_id == company_id,
                        PendingActionORM.created_at >= start_dt,
                        PendingActionORM.created_at <= end_dt,
                        PendingActionORM.status == PendingActionStatus.CONVERTED.value
                    )
                )
            )
            converted_count = converted_query.scalar() or 0
            
            # Count actions with due_at in the future (urgent)
            from zoneinfo import ZoneInfo
            now_utc = datetime.now(ZoneInfo("UTC"))
            urgent_query = await self.session.execute(
                select(func.count(PendingActionORM.id)).where(
                    and_(
                        PendingActionORM.company_id == company_id,
                        PendingActionORM.status == PendingActionStatus.PENDING.value,
                        PendingActionORM.due_at.isnot(None),
                        PendingActionORM.due_at <= now_utc + timedelta(days=1)  # Due within 24 hours
                    )
                )
            )
            urgent_count = urgent_query.scalar() or 0
            
            total_actions = pending_count + completed_count + converted_count
            
            return {
                "total_pending": pending_count,
                "total_actions": total_actions,
                "pending_actions": pending_count,
                "completed_actions": completed_count,
                "converted_actions": converted_count,
                "urgent_actions": urgent_count,
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
            booked = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            booked_count = booked.scalar() or 0
            
            # Total leads in date range
            leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            leads_count = leads.scalar() or 0
            
            conversion_rate = (booked_count / leads_count * 100) if leads_count > 0 else 0.0
            
            return {
                "converted_count": booked_count,
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
            
            # Get all analyses with objections in date range
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections != None,
                    func.array_length(CallAnalysisORM.objections, 1) > 0
                )
            )
            analyses_list = analyses.scalars().all()
            
            # Count objections by type
            objections_by_type: Dict[str, int] = {}
            total_objections = 0
            
            for analysis in analyses_list:
                if analysis.objections:
                    for obj in analysis.objections:
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
            
            # Get analyses with this objection in date range
            analyses = await self.session.execute(
                select(CallAnalysisORM).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    text(f":objection = ANY({CallAnalysisORM.__table__.name}.objections)").bindparams(bindparam('objection', objection_type))
                ).order_by(CallAnalysisORM.created_at.desc()).limit(limit)
            )
            analyses_list = analyses.scalars().all()
            
            # Count total
            total = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    text(f":objection = ANY({CallAnalysisORM.__table__.name}.objections)").bindparams(bindparam('objection', objection_type))
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
            
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get hot, warm, new leads prioritized in date range with contact_card loaded
            leads = await self.session.execute(
                select(LeadORM)
                .options(selectinload(LeadORM.contact_card))
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status.in_(["hot", "warm", "new"])
                ).order_by(
                    case(
                        (LeadORM.status == "hot", 1),
                        (LeadORM.status == "warm", 2),
                        (LeadORM.status == "new", 3),
                        else_=4,
                    ),
                    LeadORM.created_at.desc()
                ).limit(limit)
            )
            leads_list = leads.scalars().all()
            
            # Count by status
            hot_count = sum(1 for l in leads_list if l.status == "hot")
            warm_count = sum(1 for l in leads_list if l.status == "warm")
            new_count = sum(1 for l in leads_list if l.status == "new")
            
            # Convert to dict with contact_card info
            leads_data = []
            for lead in leads_list:
                lead_dict = {
                    "id": str(lead.id),
                    "contact_card_id": str(lead.contact_card_id),
                    "status": lead.status,
                    "deal_size": lead.deal_size,
                    "assigned_rep_id": str(lead.assigned_rep_id) if lead.assigned_rep_id else None,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                }
                # Add contact_card info if available
                if lead.contact_card:
                    lead_dict["contact_card"] = {
                        "id": str(lead.contact_card.id),
                        "first_name": lead.contact_card.first_name,
                        "last_name": lead.contact_card.last_name,
                        "primary_phone": lead.contact_card.primary_phone,
                        "email": lead.contact_card.email,
                    }
                leads_data.append(lead_dict)
            
            return {
                "total": len(leads_list),
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
            
            if user.role != UserRole.CSR.value:
                raise ValueError(f"User {user_id} is not a CSR")
            
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
            
            # Qualified leads
            qualified_leads_result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.assigned_rep_id == user_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(
                        LeadORM.status.like('qualified_%'),
                        LeadORM.deal_status == 'qualified'
                    )
                )
            )
            qualified_leads = qualified_leads_result.scalar() or 0
            
            # ===== APPOINTMENT METRICS =====
            # Booked appointments
            booked_appointments_result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.assigned_rep_id == user_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            booked_appointments = booked_appointments_result.scalar() or 0
            
            # Booking rate
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
            # Get objection handling improvement
            current_month_objections = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                ).join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            )
            current_objections = current_month_objections.scalar() or 0
            
            # Compare with previous period
            prev_start_dt = start_dt - (end_dt - start_dt)
            prev_objections_result = await self.session.execute(
                select(func.count(CallAnalysisORM.id)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= prev_start_dt,
                    CallAnalysisORM.created_at < start_dt,
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                ).join(CallORM, CallAnalysisORM.call_id == CallORM.id)
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
            # Check SOP compliance
            avg_sop_score_result = await self.session.execute(
                select(func.avg(CallAnalysisORM.sop_compliance_score)).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.sop_compliance_score.isnot(None),
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
            # Compare qualification_status from analysis with actual lead status
            qualification_accuracy_result = await self.session.execute(
                select(
                    func.count(CallAnalysisORM.id),
                    func.sum(case((CallAnalysisORM.qualification_status == 'qualified', 1), else_=0))
                ).where(
                    CallAnalysisORM.company_id == company_id,
                    CallORM.handled_by_user_id == user_id,
                    CallORM.lead_id.isnot(None),
                    CallAnalysisORM.created_at >= start_dt,
                    CallAnalysisORM.created_at <= end_dt,
                    CallAnalysisORM.qualification_status.isnot(None),
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