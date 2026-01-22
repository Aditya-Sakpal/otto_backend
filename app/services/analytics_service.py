"""
Analytics service.

Provides analytics calculations for objections and calls.
"""
import traceback
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.analysis import CallAnalysisORM

logger = get_logger(__name__)


class AnalyticsService:
    """Service for analytics calculations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_top_objections(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Get top objections aggregated by company.
        
        Returns ALL objections sorted from most occurred to least occurred, with:
        - objection_type: Type of objection
        - count: Number of times this objection appeared
        - affected_leads_count: Number of unique leads affected by this objection
        """
        try:
            # Get all analyses with objections for this company, joined with calls to get lead_id
            # Filter for non-null objections arrays
            query = select(
                CallAnalysisORM,
                CallORM.lead_id
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None)
            )
            
            results = await self.session.execute(query)
            rows = results.all()
            
            # Count objections and track affected leads
            objection_counts: Dict[str, int] = {}
            objection_leads: Dict[str, set] = {}  # Track unique lead IDs per objection
            
            for analysis, lead_id in rows:
                # Skip if objections is None or empty
                if not analysis.objections or len(analysis.objections) == 0:
                    continue
                
                # Count each objection and track affected leads
                # Filter out empty strings and None values
                for obj_type in analysis.objections:
                    # Skip empty or None objection types
                    if not obj_type or not str(obj_type).strip():
                        continue
                    
                    # Normalize objection type (strip whitespace for consistency)
                    obj_type_normalized = str(obj_type).strip()
                    
                    if obj_type_normalized not in objection_counts:
                        objection_counts[obj_type_normalized] = 0
                        objection_leads[obj_type_normalized] = set()
                    
                    objection_counts[obj_type_normalized] += 1
                    
                    # Track unique lead if available
                    if lead_id:
                        objection_leads[obj_type_normalized].add(lead_id)
            
            # Build response list - sorted by count descending (most occurred to least occurred)
            # Return ALL objections, not just top N
            result = [
                {
                    "objection_type": obj_type,
                    "count": count,
                    "affected_leads_count": len(objection_leads.get(obj_type, set())),
                }
                for obj_type, count in sorted(
                    objection_counts.items(),
                    key=lambda x: x[1],  # Sort by count
                    reverse=True  # Descending order (most to least)
                )
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting top objections: {e}")
            traceback.print_exc()
            raise
    
    async def get_objection_calls(
        self,
        company_id: UUID,
        objection: str,
        owner_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get calls filtered by objection type and optionally by CSR owner.
        
        Returns list of calls with:
        - call_id: UUID of the call
        - contact_card: Full contact card object
        - audio_url: URL to call audio recording
        - qualification_status: Qualification status from analysis
        - booking_status: Booking status from analysis
        """
        try:
            # Build query with join for better performance
            # Normalize objection to lowercase for case-insensitive matching
            objection_normalized = objection.lower().strip()
            
            # Map common variations to standard values
            # This handles data inconsistencies like 'price' vs 'pricing'
            objection_mappings = {
                'price': ['price', 'pricing', 'cost', 'costs'],
                'timing': ['timing', 'time', 'schedule', 'scheduling'],
                'authority': ['authority', 'decision', 'decision-maker'],
                'need': ['need', 'needs', 'requirement', 'requirements'],
                'competitor': ['competitor', 'competitors', 'competition'],
                'other': ['other', 'others', 'misc', 'miscellaneous'],
            }
            
            # Get all possible variations for this objection
            objection_variations = objection_mappings.get(objection_normalized, [objection_normalized])
            # Also include the original value in case it's not in the mapping
            if objection_normalized not in objection_variations:
                objection_variations.insert(0, objection_normalized)
            
            # Use PostgreSQL array overlap operator (&&) to check if any variation matches
            # Convert variations to lowercase array for case-insensitive comparison
            variations_array = [v.lower() for v in objection_variations]
            
            query = select(
                CallAnalysisORM,
                CallORM,
                ContactCardORM
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                # Check if any variation matches any element in the array (case-insensitive)
                # Using array overlap with LOWER() for case-insensitive matching
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                )
            )
            
            # Add owner_id filter if provided
            if owner_id:
                query = query.where(CallORM.handled_by_user_id == owner_id)
            
            # Execute query
            results = await self.session.execute(query)
            rows = results.all()
            
            # Build response
            result = []
            for analysis, call, contact_card in rows:
                # Get contact card data
                contact_card_data = None
                if contact_card:
                    contact_card_data = {
                        "id": str(contact_card.id),
                        "company_id": str(contact_card.company_id),
                        "primary_phone": contact_card.primary_phone,
                        "secondary_phone": contact_card.secondary_phone,
                        "email": contact_card.email,
                        "first_name": contact_card.first_name,
                        "last_name": contact_card.last_name,
                        "address": contact_card.address,
                        "city": contact_card.city,
                        "state": contact_card.state,
                        "postal_code": contact_card.postal_code,
                        "property_snapshot": contact_card.property_snapshot,
                        "extra_metadata": contact_card.extra_metadata,
                    }
                
                result.append({
                    "call_id": str(call.id),
                    "contact_card": contact_card_data,
                    "audio_url": call.audio_url,
                    "qualification_status": analysis.qualification_status,
                    "booking_status": analysis.booking_status,
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting objection calls: {e}")
            traceback.print_exc()
            raise
    
    async def get_calls_by_objection_self(
        self,
        company_id: UUID,
        objection: str,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive objection details data for the objection details page.
        
        Returns data for three tabs:
        1. Calls: List of calls with that objection (with contact name and recording URL)
        2. Unbooked leads: Leads that are unbooked and have that objection
        3. Most coaching need: CSRs with unbooked calls for that objection
        
        Args:
            company_id: Company UUID
            objection: Objection type (e.g., 'authority', 'price', 'timing')
            user_id: Optional user ID to filter by (for /self endpoint)
        
        Returns:
            Dictionary with:
            - calls: List of calls with objection details
            - unbooked_leads: List of unbooked leads with that objection
            - most_coaching_need: List of CSRs with unbooked calls count
        """
        try:
            from app.infrastructure.database.models.lead import LeadORM
            from app.infrastructure.database.models.user import UserORM
            
            # Normalize objection
            objection_normalized = objection.lower().strip()
            objection_mappings = {
                'price': ['price', 'pricing', 'cost', 'costs'],
                'timing': ['timing', 'time', 'schedule', 'scheduling'],
                'authority': ['authority', 'decision', 'decision-maker'],
                'need': ['need', 'needs', 'requirement', 'requirements'],
                'competitor': ['competitor', 'competitors', 'competition'],
                'other': ['other', 'others', 'misc', 'miscellaneous'],
            }
            objection_variations = objection_mappings.get(objection_normalized, [objection_normalized])
            if objection_normalized not in objection_variations:
                objection_variations.insert(0, objection_normalized)
            variations_array = [v.lower() for v in objection_variations]
            
            # 1. Get calls with that objection
            calls_query = select(
                CallORM,
                CallAnalysisORM,
                ContactCardORM
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                )
            )
            
            if user_id:
                calls_query = calls_query.where(CallORM.handled_by_user_id == user_id)
            
            calls_query = calls_query.order_by(CallORM.created_at.desc())
            
            calls_results = await self.session.execute(calls_query)
            calls_rows = calls_results.all()
            
            calls_data = []
            for call, analysis, contact_card in calls_rows:
                # Get contact name
                contact_name = None
                if contact_card:
                    if contact_card.first_name and contact_card.last_name:
                        contact_name = f"{contact_card.first_name} {contact_card.last_name}"
                    elif contact_card.first_name:
                        contact_name = contact_card.first_name
                    elif contact_card.last_name:
                        contact_name = contact_card.last_name
                    else:
                        contact_name = contact_card.primary_phone
                
                calls_data.append({
                    "id": str(call.id),
                    "contact_name": contact_name or "Unknown",
                    "call_recording_url": call.audio_url,
                    "phone_number": call.phone_number,
                    "call_type": call.call_type,
                    "duration_seconds": call.duration_seconds,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "transcript": call.transcript,
                    "summary": analysis.summary if analysis else None,
                })
            
            # 2. Get unbooked leads with that objection
            # Unbooked = leads with status not 'qualified_booked' and not 'closed_won'
            unbooked_statuses = ['new', 'warm', 'hot', 'qualified_unbooked', 'qualified_service_not_offered', 'nurturing']
            
            # Use DISTINCT ON to avoid JSON comparison issues
            # Use subquery to get distinct lead IDs first, then join to avoid JSON comparison issues
            distinct_lead_ids = select(LeadORM.id).join(
                CallORM, CallORM.lead_id == LeadORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).where(
                LeadORM.company_id == company_id,
                LeadORM.status.in_(unbooked_statuses),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                )
            ).distinct().subquery()
            
            unbooked_leads_query = select(
                LeadORM,
                ContactCardORM
            ).join(
                ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id
            ).where(
                LeadORM.id.in_(select(distinct_lead_ids.c.id))
            )
            
            unbooked_results = await self.session.execute(unbooked_leads_query)
            unbooked_rows = unbooked_results.all()
            
            unbooked_leads_data = []
            for lead, contact_card in unbooked_rows:
                contact_name = None
                if contact_card:
                    if contact_card.first_name and contact_card.last_name:
                        contact_name = f"{contact_card.first_name} {contact_card.last_name}"
                    elif contact_card.first_name:
                        contact_name = contact_card.first_name
                    elif contact_card.last_name:
                        contact_name = contact_card.last_name
                    else:
                        contact_name = contact_card.primary_phone
                
                unbooked_leads_data.append({
                    "id": str(lead.id),
                    "contact_name": contact_name or "Unknown",
                    "status": lead.status,
                    "deal_status": lead.deal_status,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                })
            
            # 3. Get CSRs with unbooked calls for that objection (most coaching need)
            # Count unbooked calls per CSR
            csr_unbooked_query = select(
                UserORM.id,
                UserORM.first_name,
                UserORM.last_name,
                func.count(CallORM.id).label('unbooked_calls_count')
            ).join(
                CallORM, CallORM.handled_by_user_id == UserORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).join(
                LeadORM, CallORM.lead_id == LeadORM.id
            ).where(
                UserORM.company_id == company_id,
                UserORM.role == 'csr',
                UserORM.is_active == True,
                LeadORM.status.in_(unbooked_statuses),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                )
            ).group_by(
                UserORM.id,
                UserORM.first_name,
                UserORM.last_name
            ).order_by(
                func.count(CallORM.id).desc()
            )
            
            csr_results = await self.session.execute(csr_unbooked_query)
            csr_rows = csr_results.all()
            
            most_coaching_need_data = []
            for user_id_val, first_name, last_name, unbooked_count in csr_rows:
                name = None
                if first_name and last_name:
                    name = f"{first_name} {last_name}"
                elif first_name:
                    name = first_name
                elif last_name:
                    name = last_name
                else:
                    name = "Unknown"
                
                most_coaching_need_data.append({
                    "csr_id": str(user_id_val),
                    "csr_name": name,
                    "unbooked_calls": unbooked_count,
                })
            
            return {
                "objection": objection,
                "calls": calls_data,
                "unbooked_leads": unbooked_leads_data,
                "most_coaching_need": most_coaching_need_data,
            }
            
        except Exception as e:
            logger.error(f"Error getting calls by objection self: {e}")
            traceback.print_exc()
            raise
    
    async def get_objection_details(
        self,
        company_id: UUID,
        objection: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive objection details for a single objection.
        
        Returns data for all three tabs:
        1. Unbooked leads: Leads with booking rate improvement and graph data
        2. Most coaching need: CSRs with unbooked calls for that objection
        3. Calls: Call recordings with contact names
        
        Args:
            company_id: Company UUID
            objection: Objection type (e.g., 'authority', 'price', 'timing')
            start_date: Start date for filtering (YYYY-MM-DD, optional)
            end_date: End date for filtering (YYYY-MM-DD, optional)
            user_id: Optional user ID to filter by (for CSR role)
        
        Returns:
            Dictionary with comprehensive objection details including:
            - objection: Objection type
            - unbooked_leads: Tab data with booking rate improvement and graph
            - most_coaching_need: Tab data with CSRs and unbooked calls
            - calls: Tab data with call recordings and contact names
        """
        try:
            from app.infrastructure.database.models.lead import LeadORM
            from app.infrastructure.database.models.user import UserORM
            
            # Parse dates
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=None)
            else:
                start_dt = datetime.now().replace(tzinfo=None) - timedelta(days=30)
            
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=None)
            else:
                end_dt = datetime.now().replace(tzinfo=None)
            
            # Normalize objection
            objection_normalized = objection.lower().strip()
            objection_mappings = {
                'price': ['price', 'pricing', 'cost', 'costs'],
                'timing': ['timing', 'time', 'schedule', 'scheduling'],
                'authority': ['authority', 'decision', 'decision-maker'],
                'need': ['need', 'needs', 'requirement', 'requirements'],
                'competitor': ['competitor', 'competitors', 'competition'],
                'other': ['other', 'others', 'misc', 'miscellaneous'],
            }
            objection_variations = objection_mappings.get(objection_normalized, [objection_normalized])
            if objection_normalized not in objection_variations:
                objection_variations.insert(0, objection_normalized)
            variations_array = [v.lower() for v in objection_variations]
            
            unbooked_statuses = ['new', 'warm', 'hot', 'qualified_unbooked', 'qualified_service_not_offered', 'nurturing']
            
            # 1. UNBOOKED LEADS TAB - Get booking rate improvement and graph data
            # Get qualified leads with this objection in date range
            # Use subquery to get distinct lead IDs first, then join to avoid JSON comparison issues
            qualified_lead_ids_query = select(LeadORM.id).join(
                CallORM, CallORM.lead_id == LeadORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).where(
                LeadORM.company_id == company_id,
                LeadORM.created_at >= start_dt,
                LeadORM.created_at <= end_dt,
                LeadORM.status.in_(['qualified_booked', 'qualified_unbooked']),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                )
            )
            
            if user_id:
                qualified_lead_ids_query = qualified_lead_ids_query.where(CallORM.handled_by_user_id == user_id)
            
            distinct_lead_ids = qualified_lead_ids_query.distinct().subquery()
            
            qualified_leads_query = select(
                LeadORM,
                ContactCardORM
            ).join(
                ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id
            ).where(
                LeadORM.id.in_(select(distinct_lead_ids.c.id))
            )
            
            qualified_results = await self.session.execute(qualified_leads_query)
            qualified_rows = qualified_results.all()
            
            # Calculate booking rate improvement
            total_qualified = len(qualified_rows)
            booked_count = sum(1 for lead, contact in qualified_rows if lead.status == 'qualified_booked')
            unbooked_count = sum(1 for lead, contact in qualified_rows if lead.status == 'qualified_unbooked')
            
            # Split into two periods for comparison (using lead created_at for period split)
            mid_date = start_dt + (end_dt - start_dt) / 2
            first_period_booked = sum(1 for lead, contact in qualified_rows 
                                     if lead.status == 'qualified_booked' and lead.created_at and lead.created_at < mid_date)
            first_period_total = sum(1 for lead, contact in qualified_rows 
                                    if lead.created_at and lead.created_at < mid_date)
            second_period_booked = sum(1 for lead, contact in qualified_rows 
                                      if lead.status == 'qualified_booked' and lead.created_at and lead.created_at >= mid_date)
            second_period_total = sum(1 for lead, contact in qualified_rows 
                                     if lead.created_at and lead.created_at >= mid_date)
            
            first_period_rate = (first_period_booked / first_period_total * 100) if first_period_total > 0 else 0
            second_period_rate = (second_period_booked / second_period_total * 100) if second_period_total > 0 else 0
            improvement_percentage = second_period_rate - first_period_rate
            
            # Generate graph data (daily booking rate over time)
            graph_data = []
            current_date = start_dt
            while current_date <= end_dt:
                day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                day_qualified = sum(1 for lead, contact in qualified_rows 
                                  if lead.created_at and day_start <= lead.created_at < day_end)
                day_booked = sum(1 for lead, contact in qualified_rows 
                               if lead.status == 'qualified_booked' and lead.created_at and day_start <= lead.created_at < day_end)
                
                booking_rate = (day_booked / day_qualified * 100) if day_qualified > 0 else 0
                
                graph_data.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "booking_rate": round(booking_rate, 2),
                    "qualified_count": day_qualified,
                    "booked_count": day_booked
                })
                
                current_date += timedelta(days=1)
            
            # Get unbooked leads list with name and phone
            unbooked_leads_list = []
            for lead, contact_card in qualified_rows:
                if lead.status == 'qualified_unbooked':
                    contact_name = None
                    if contact_card:
                        first_name = contact_card.first_name or ""
                        last_name = contact_card.last_name or ""
                        contact_name = f"{first_name} {last_name}".strip() or None
                    
                    unbooked_leads_list.append({
                        "id": str(lead.id),
                        "contact_name": contact_name,
                        "phone_number": contact_card.primary_phone if contact_card else None,
                        "status": lead.status,
                        "deal_status": lead.deal_status,
                        "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    })
            
            # 2. MOST COACHING NEED TAB - CSRs with unbooked calls
            csr_unbooked_query = select(
                UserORM.id,
                UserORM.first_name,
                UserORM.last_name,
                func.count(CallORM.id).label('unbooked_calls_count')
            ).join(
                CallORM, CallORM.handled_by_user_id == UserORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).join(
                LeadORM, CallORM.lead_id == LeadORM.id
            ).where(
                UserORM.company_id == company_id,
                UserORM.role == 'csr',
                UserORM.is_active == True,
                LeadORM.status.in_(unbooked_statuses),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                ),
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt
            ).group_by(
                UserORM.id,
                UserORM.first_name,
                UserORM.last_name
            ).order_by(
                func.count(CallORM.id).desc()
            )
            
            csr_results = await self.session.execute(csr_unbooked_query)
            csr_rows = csr_results.all()
            
            most_coaching_need_data = []
            for user_id_val, first_name, last_name, unbooked_count in csr_rows:
                name = None
                if first_name and last_name:
                    name = f"{first_name} {last_name}"
                elif first_name:
                    name = first_name
                elif last_name:
                    name = last_name
                else:
                    name = "Unknown"
                
                most_coaching_need_data.append({
                    "csr_id": str(user_id_val),
                    "csr_name": name,
                    "unbooked_calls": unbooked_count,
                })
            
            # 3. CALLS TAB - Call recordings with contact names
            calls_query = select(
                CallORM,
                CallAnalysisORM,
                ContactCardORM
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                text("ARRAY(SELECT LOWER(unnest(call_analyses.objections))) && :variations").bindparams(
                    bindparam('variations', variations_array)
                ),
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt
            )
            
            if user_id:
                calls_query = calls_query.where(CallORM.handled_by_user_id == user_id)
            
            calls_query = calls_query.order_by(CallORM.created_at.desc())
            
            calls_results = await self.session.execute(calls_query)
            calls_rows = calls_results.all()
            
            calls_data = []
            for call, analysis, contact_card in calls_rows:
                # Get contact name
                contact_name = None
                if contact_card:
                    first_name = contact_card.first_name or ""
                    last_name = contact_card.last_name or ""
                    contact_name = f"{first_name} {last_name}".strip() or None
                    if not contact_name:
                        contact_name = contact_card.primary_phone
                
                calls_data.append({
                    "id": str(call.id),
                    "contact_name": contact_name or "Unknown",
                    "call_recording_url": call.audio_url,
                    "phone_number": call.phone_number,
                    "call_type": call.call_type,
                    "duration_seconds": call.duration_seconds,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "transcript": call.transcript,
                    "summary": analysis.summary if analysis else None,
                })
            
            return {
                "objection": objection,
                "unbooked_leads": {
                    "booking_rate_improvement": {
                        "title": "Booking Rate Improvement",
                        "percentage": round(improvement_percentage, 1),
                        "description": f"{round(improvement_percentage, 1)}% Increase in Booking Appointments",
                        "context": "Growth in qualified leads booked from start to end of the selected timeframe.",
                        "current_rate": round(second_period_rate, 1),
                        "previous_rate": round(first_period_rate, 1),
                        "total_qualified": total_qualified,
                        "booked_count": booked_count,
                        "unbooked_count": unbooked_count
                    },
                    "graph_data": graph_data,
                    "leads": unbooked_leads_list
                },
                "most_coaching_need": {
                    "total_csr": len(most_coaching_need_data),
                    "csrs": most_coaching_need_data
                },
                "calls": {
                    "total_calls": len(calls_data),
                    "call_recordings": calls_data
                },
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error(f"Error getting objection details: {e}")
            traceback.print_exc()
            raise
