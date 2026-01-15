"""
Metrics service.

Provides metrics and analytics calculations with date range filtering.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, date

from sqlalchemy import select, func, and_, or_, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.user import UserORM
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
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get company overview metrics within date range."""
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
            total_leads_count = total_leads.scalar() or 0
            
            # Active leads (not closed) in date range
            active_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status.notin_(["closed_won", "closed_lost", "abandoned", "dormant"])
                )
            )
            active_leads_count = active_leads.scalar() or 0
            
            # Qualified leads in date range
            # Count leads with deal_status = "qualified" OR status in qualified statuses
            # This handles both the deal_status field and the status field for qualification
            qualified_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    or_(
                        LeadORM.deal_status == "qualified",
                        LeadORM.status.in_(["qualified_booked", "qualified_unbooked", "qualified_service_not_offered"])
                    )
                )
            )
            qualified_leads_count = qualified_leads.scalar() or 0
            
            # Total calls in date range
            total_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_calls_count = total_calls.scalar() or 0
            
            # Missed calls in date range
            missed_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                )
            )
            missed_calls_count = missed_calls.scalar() or 0
            
            # Total appointments in date range
            total_appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            total_appointments_count = total_appointments.scalar() or 0
            
            # Conversion rate (closed_won / total leads) in date range
            won_leads = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
            )
            won_count = won_leads.scalar() or 0
            conversion_rate = (won_count / total_leads_count * 100) if total_leads_count > 0 else 0.0
            
            # Total revenue in date range
            total_revenue = await self.session.execute(
                select(func.sum(LeadORM.deal_size)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "closed_won"
                )
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
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get CSR dashboard metrics within date range."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            # Total calls in date range
            total_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                )
            )
            total_calls_count = total_calls.scalar() or 0
            
            # Missed calls in date range
            missed_calls = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.missed_call == True
                )
            )
            missed_calls_count = missed_calls.scalar() or 0
            
            # Calls today
            calls_today = await self.session.execute(
                select(func.count(CallORM.id)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= today_start
                )
            )
            calls_today_count = calls_today.scalar() or 0
            
            # Average call duration in date range
            avg_duration = await self.session.execute(
                select(func.avg(CallORM.duration_seconds)).where(
                    CallORM.company_id == company_id,
                    CallORM.created_at >= start_dt,
                    CallORM.created_at <= end_dt,
                    CallORM.duration_seconds.isnot(None)
                )
            )
            avg_duration_val = avg_duration.scalar() or 0.0
            
            # Leads count in date range
            leads_count = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            leads_assigned = leads_count.scalar() or 0
            
            # Appointments scheduled in date range
            appointments = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
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
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get booking rate improvement metrics comparing current period to previous period."""
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Calculate period length
            period_length = (end_dt - start_dt).days
            previous_start = start_dt - timedelta(days=period_length)
            previous_end = start_dt
            
            # Current period bookings
            current_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= start_dt,
                    AppointmentORM.created_at <= end_dt,
                )
            )
            current_count = current_bookings.scalar() or 0
            
            # Current period qualified leads
            current_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status.in_(["qualified_booked", "qualified_unbooked"]),
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                )
            )
            current_qualified_count = current_qualified.scalar() or 0
            
            # Previous period bookings
            previous_bookings = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.created_at >= previous_start,
                    AppointmentORM.created_at < previous_end,
                )
            )
            previous_count = previous_bookings.scalar() or 0
            
            # Previous period qualified
            previous_qualified = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
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
            
            # Get leads in date range
            leads = await self.session.execute(
                select(LeadORM).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status == "qualified_unbooked"
                ).order_by(LeadORM.created_at.desc()).limit(limit)
            )
            leads_list = leads.scalars().all()
            
            # Calculate average days unbooked
            now = datetime.utcnow()
            total_days = sum(
                (now - lead.created_at).days if lead.created_at else 0
                for lead in leads_list
            )
            avg_days = (total_days / len(leads_list)) if leads_list else 0.0
            
            return {
                "total_unbooked": unbooked_count,
                "qualified_unbooked": unbooked_count,
                "avg_days_unbooked": round(avg_days, 2),
                "leads": [
                    {
                        "id": str(lead.id),
                        "contact_card_id": str(lead.contact_card_id),
                        "status": lead.status,
                        "deal_size": lead.deal_size,
                        "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    }
                    for lead in leads_list
                ],
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
        try:
            start_dt, end_dt = self._get_date_range(start_date, end_date)
            
            # Get hot, warm, new leads prioritized in date range
            leads = await self.session.execute(
                select(LeadORM).where(
                    LeadORM.company_id == company_id,
                    LeadORM.created_at >= start_dt,
                    LeadORM.created_at <= end_dt,
                    LeadORM.status.in_(["hot", "warm", "new"])
                ).order_by(
                    func.case(
                        (LeadORM.status == "hot", 1),
                        (LeadORM.status == "warm", 2),
                        (LeadORM.status == "new", 3),
                    ),
                    LeadORM.created_at.desc()
                ).limit(limit)
            )
            leads_list = leads.scalars().all()
            
            # Count by status
            hot_count = sum(1 for l in leads_list if l.status == "hot")
            warm_count = sum(1 for l in leads_list if l.status == "warm")
            new_count = sum(1 for l in leads_list if l.status == "new")
            
            return {
                "total": len(leads_list),
                "hot_leads": hot_count,
                "warm_leads": warm_count,
                "new_leads": new_count,
                "leads": [
                    {
                        "id": str(lead.id),
                        "contact_card_id": str(lead.contact_card_id),
                        "status": lead.status,
                        "deal_size": lead.deal_size,
                        "assigned_rep_id": str(lead.assigned_rep_id) if lead.assigned_rep_id else None,
                        "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    }
                    for lead in leads_list
                ],
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting auto-queued leads: {e}")
            raise e
