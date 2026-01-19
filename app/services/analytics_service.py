"""
Analytics service.

Provides analytics calculations for objections and calls.
"""
import traceback
from typing import Optional, List, Dict, Any
from uuid import UUID

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
        
        Returns list of objections with:
        - objection_type: Type of objection
        - count: Number of times this objection appeared
        - affected_leads_count: Number of unique leads affected by this objection
        """
        try:
            # Get all analyses with objections for this company, joined with calls to get lead_id
            query = select(
                CallAnalysisORM,
                CallORM.lead_id
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0
            )
            
            results = await self.session.execute(query)
            rows = results.all()
            
            # Count objections and track affected leads
            objection_counts: Dict[str, int] = {}
            objection_leads: Dict[str, set] = {}  # Track unique lead IDs per objection
            
            for analysis, lead_id in rows:
                if not analysis.objections:
                    continue
                
                # Count each objection and track affected leads
                for obj_type in analysis.objections:
                    if obj_type not in objection_counts:
                        objection_counts[obj_type] = 0
                        objection_leads[obj_type] = set()
                    
                    objection_counts[obj_type] += 1
                    
                    # Track unique lead if available
                    if lead_id:
                        objection_leads[obj_type].add(lead_id)
            
            # Build response list
            result = [
                {
                    "objection_type": obj_type,
                    "count": count,
                    "affected_leads_count": len(objection_leads.get(obj_type, set())),
                }
                for obj_type, count in sorted(
                    objection_counts.items(),
                    key=lambda x: x[1],
                    reverse=True
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
            
            unbooked_leads_query = select(
                LeadORM,
                ContactCardORM
            ).join(
                ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id
            ).join(
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
            ).distinct()
            
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
