"""
Customer History Service - Retrieves customer context from RAG before processing.

Enhanced with call type detection and existing customer handling.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from ...core.database import get_database
from .rag_service import get_rag_service
from .call_type_detector import get_call_type_detector

logger = logging.getLogger(__name__)


class CustomerHistoryService:
    """Service for retrieving customer history and context."""
    
    def __init__(self):
        pass
    
    async def get_customer_context(
        self,
        phone_number: Optional[str] = None,
        company_id: Optional[str] = None,
        limit: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve customer history from previous calls.
        
        Args:
            phone_number: Customer phone number
            company_id: Company identifier
            limit: Number of previous calls to retrieve
        
        Returns:
            Dictionary with customer history or None if not found
        """
        if not phone_number or not company_id:
            return None
        
        try:
            # Get previous calls from MongoDB
            db = await get_database()
            
            previous_calls = await db.call_summaries.find(
                {
                    "company_id": company_id,
                    "qualification.customer_phone": phone_number
                },
                {
                    "call_id": 1,
                    "summary.summary": 1,
                    "summary.key_points": 1,
                    "objections.objections": 1,
                    "qualification.qualification_status": 1,
                    "qualification.booking_status": 1,
                    "qualification.service_requested": 1,
                    "qualification.follow_up_reason": 1,
                    "created_at": 1
                }
            ).sort("created_at", -1).limit(limit).to_list(length=limit)
            
            if not previous_calls:
                return None
            
            # Format customer history
            history = {
                "has_history": True,
                "previous_call_count": len(previous_calls),
                "recent_calls": []
            }
            
            for call in previous_calls:
                call_summary = {
                    "call_id": call.get("call_id"),
                    "date": call.get("created_at").isoformat() if call.get("created_at") else None,
                    "summary": call.get("summary", {}).get("summary", ""),
                    "key_points": call.get("summary", {}).get("key_points", [])[:3],  # Top 3
                    "qualification_status": call.get("qualification", {}).get("qualification_status"),
                    "booking_status": call.get("qualification", {}).get("booking_status"),
                    "service_requested": call.get("qualification", {}).get("service_requested"),
                    "follow_up_reason": call.get("qualification", {}).get("follow_up_reason"),
                    "objections": [
                        f"{obj.get('category_text')}: {obj.get('sub_objection')}"
                        if obj.get("sub_objection")
                        else obj.get("category_text")
                        for obj in call.get("objections", {}).get("objections", [])
                    ][:3]  # Top 3 objections
                }
                history["recent_calls"].append(call_summary)
            
            # Extract patterns
            if history["recent_calls"]:
                latest = history["recent_calls"][0]
                history["last_interaction"] = {
                    "date": latest["date"],
                    "status": latest["qualification_status"],
                    "booking_status": latest["booking_status"],
                    "service": latest["service_requested"],
                    "follow_up_context": latest["follow_up_reason"]
                }
                
                # Collect all previous objections
                all_objections = []
                for call in history["recent_calls"]:
                    all_objections.extend(call["objections"])
                history["recurring_objections"] = list(set(all_objections))
            
            logger.info(f"Retrieved customer history: {len(previous_calls)} previous calls for {phone_number}")
            return history
            
        except Exception as e:
            logger.error(f"Failed to retrieve customer history: {e}")
            return None
    
    async def get_customer_sentiment_trend(
        self,
        phone_number: str,
        company_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get customer sentiment trend across calls.
        
        Returns:
            Sentiment trend data or None
        """
        try:
            db = await get_database()
            
            calls = await db.call_summaries.find(
                {
                    "company_id": company_id,
                    "qualification.customer_phone": phone_number
                },
                {
                    "summary.sentiment_score": 1,
                    "created_at": 1
                }
            ).sort("created_at", 1).to_list(length=10)
            
            if not calls:
                return None
            
            scores = [
                call.get("summary", {}).get("sentiment_score", 0.5)
                for call in calls
            ]
            
            return {
                "call_count": len(scores),
                "scores": scores,
                "average": sum(scores) / len(scores),
                "trend": "improving" if len(scores) > 1 and scores[-1] > scores[0] else
                         "declining" if len(scores) > 1 and scores[-1] < scores[0] else
                         "stable"
            }
            
        except Exception as e:
            logger.error(f"Failed to get sentiment trend: {e}")
            return None
    
    async def detect_call_type(
        self,
        transcript: str,
        customer_history: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detect the type of call using LLM-based analysis.
        
        Args:
            transcript: Full call transcript
            customer_history: Customer history from get_customer_context
            
        Returns:
            Call type detection result with:
            - call_type: "fresh_sales" | "follow_up" | "existing_service"
            - confidence: 0.0-1.0
            - reasoning: explanation
            - property_same: whether same property as history
        """
        detector = get_call_type_detector()
        return await detector.detect_call_type(transcript, customer_history)
    
    def build_history_for_detector(
        self,
        customer_context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Build a history object formatted for the call type detector.
        
        Args:
            customer_context: Result from get_customer_context
            
        Returns:
            Formatted history or None
        """
        if not customer_context or not customer_context.get("has_history"):
            return None
        
        recent_calls = customer_context.get("recent_calls", [])
        last_interaction = customer_context.get("last_interaction", {})
        
        return {
            "name": None,  # Will be populated from qualification if available
            "last_interaction": {
                "date": last_interaction.get("date"),
                "booking_status": last_interaction.get("booking_status"),
                "service_type": last_interaction.get("service"),
                "address": None,  # Would need to add to context retrieval
                "call_outcome": last_interaction.get("status")
            },
            "previous_calls": [
                {
                    "date": call.get("date"),
                    "service_type": call.get("service_requested"),
                    "outcome": call.get("qualification_status")
                }
                for call in recent_calls
            ]
        }
    
    def merge_with_known_customer(
        self,
        extracted: Dict[str, Any],
        customer_history: Optional[Dict[str, Any]],
        call_type_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge extracted data with known customer data based on call type.
        
        This handles:
        - Preserving booking status for follow-up/existing service calls
        - Setting appropriate call outcome category
        - Using known info when extraction missed it
        
        Args:
            extracted: Extracted call data
            customer_history: Customer history context
            call_type_result: Result from detect_call_type
            
        Returns:
            Merged extraction result
        """
        if not customer_history or not customer_history.get("has_history"):
            return extracted
        
        call_type = call_type_result.get("call_type", "fresh_sales")
        property_same = call_type_result.get("property_same")
        last_interaction = customer_history.get("last_interaction", {})
        
        # Add call type detection info to result
        extracted["detected_call_type"] = call_type
        extracted["call_type_confidence"] = call_type_result.get("confidence", 0.0)
        extracted["call_type_reasoning"] = call_type_result.get("reasoning")
        
        # Handle existing service calls (already booked/completed jobs)
        if call_type == "existing_service" and property_same is not False:
            prev_booking = last_interaction.get("booking_status")
            
            if prev_booking == "booked":
                # Preserve booked status for existing service inquiries
                extracted["call_outcome_category"] = "existing_customer_service"
                extracted["booking_status"] = "booked"  # Don't override with "not_booked"
                extracted["is_existing_customer_service"] = True
                extracted["existing_service_note"] = "Follow-up on existing booked job"
                logger.info(f"Preserved booked status for existing customer service call")
        
        # Handle follow-up calls (pending decisions)
        elif call_type == "follow_up":
            extracted["call_outcome_category"] = "follow_up_inquiry"
            extracted["is_follow_up"] = True
            
            # If they were previously booked, maintain that context
            if last_interaction.get("booking_status") == "booked":
                extracted["previous_booking_status"] = "booked"
                extracted["booking_status"] = "booked"
            
            logger.info(f"Classified as follow-up inquiry")
        
        # Fresh sales - process normally but note the existing customer context
        elif call_type == "fresh_sales":
            extracted["has_previous_history"] = True
            extracted["customer_history_context"] = (
                f"Existing customer - new inquiry. "
                f"Previous: {last_interaction.get('service')}"
            )
        
        # Use known customer info if extraction missed it
        # Note: Only fill in if not already extracted
        recent_calls = customer_history.get("recent_calls", [])
        if recent_calls:
            latest = recent_calls[0]
            
            # Don't overwrite extracted data, just supplement
            if not extracted.get("customer_name"):
                # Would need to get name from qualification
                pass
            
            # Note recurring objections for context
            recurring = customer_history.get("recurring_objections", [])
            if recurring:
                extracted["customer_recurring_objections"] = recurring
        
        return extracted
    
    async def get_full_customer_context(
        self,
        phone_number: Optional[str],
        company_id: Optional[str],
        transcript: str
    ) -> Dict[str, Any]:
        """
        Get complete customer context including call type detection.
        
        This is a convenience method that combines:
        1. Customer history retrieval
        2. Call type detection
        3. Sentiment trend (optional)
        
        Args:
            phone_number: Customer phone number
            company_id: Company identifier
            transcript: Call transcript for call type detection
            
        Returns:
            Complete customer context including call type
        """
        result = {
            "is_existing_customer": False,
            "customer_history": None,
            "call_type_detection": None,
            "sentiment_trend": None
        }
        
        # Get customer history
        history = await self.get_customer_context(phone_number, company_id)
        
        if history and history.get("has_history"):
            result["is_existing_customer"] = True
            result["customer_history"] = history
            
            # Detect call type using LLM
            detector_history = self.build_history_for_detector(history)
            call_type = await self.detect_call_type(transcript, detector_history)
            result["call_type_detection"] = call_type
            
            # Get sentiment trend
            if phone_number and company_id:
                sentiment = await self.get_customer_sentiment_trend(phone_number, company_id)
                result["sentiment_trend"] = sentiment
        
        return result


# Singleton instance
_customer_history_service: Optional[CustomerHistoryService] = None


def get_customer_history_service() -> CustomerHistoryService:
    """Get singleton customer history service instance."""
    global _customer_history_service
    if _customer_history_service is None:
        _customer_history_service = CustomerHistoryService()
    return _customer_history_service

