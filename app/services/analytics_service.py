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
