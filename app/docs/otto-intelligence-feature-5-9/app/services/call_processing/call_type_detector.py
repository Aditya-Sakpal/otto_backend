"""
LLM-Based Call Type Detector

Detects whether a call is:
- fresh_sales: New sales inquiry (even from existing customer)
- follow_up: Follow-up on existing interaction that wasn't completed
- existing_service: About an already booked/completed job

Uses semantic understanding instead of keyword matching for accurate detection.
"""

from typing import Dict, Any, Optional
import json
import logging
from datetime import datetime

from ...config import get_settings
from ...core.llm import get_llm_client, get_active_model

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMCallTypeDetector:
    """
    LLM-based detection of call type for existing customers.
    
    Uses semantic understanding instead of keyword matching to accurately
    distinguish between:
    - Fresh sales inquiries (new lead or different property)
    - Follow-up calls on pending matters
    - Existing service inquiries on already booked jobs
    """
    
    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.1  # Low for consistency
    
    async def detect_call_type(
        self, 
        transcript: str, 
        customer_history: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detect call type using LLM semantic understanding.
        
        Args:
            transcript: Full call transcript
            customer_history: Previous customer interaction history (if exists)
            
        Returns:
            {
                "call_type": "new_inquiry" | "confirmation" | "follow_up" | "service_call" | "quote_only",
                "confidence": 0.0-1.0,
                "reasoning": str,
                "property_same": bool or None,
                "key_indicator": str,
                "time_since_last_days": int or None
            }
        """
        # If no customer history, it's definitely a new inquiry call
        if not customer_history:
            return {
                "call_type": "new_inquiry",
                "confidence": 1.0,
                "reasoning": "No customer history found - treating as new lead",
                "property_same": None,
                "key_indicator": "new_customer",
                "time_since_last_days": None
            }
        
        # Build context from customer history
        history_context = self._build_history_context(customer_history)
        time_since_last = self._calculate_days_since_last(customer_history)
        
        prompt = f"""Analyze this call to determine its type.

**CUSTOMER HISTORY:**
{history_context}

**CURRENT CALL TRANSCRIPT:**
{transcript}

**CLASSIFICATION TASK:**
Determine if this call is:

1. **new_inquiry** - First-time customer or new opportunity
   - Customer asking about a DIFFERENT property ("my neighbor's house", "my other property")
   - Customer referring someone else (neighbor, relative, friend)
   - Significantly different service from previous interaction
   - First contact in 90+ days about a NEW issue (not follow-up on old one)
   - Phrases: "I'm interested in...", "I need a quote for...", "first time calling about..."
   
2. **confirmation** - Confirming an existing appointment
   - Short call to verify appointment details
   - Rep or customer confirming scheduled visit
   - No new sales discussion, just logistics
   - Phrases: "confirming your appointment", "reminder about", "still on for", "see you tomorrow"
   
3. **follow_up** - Post-sale follow-up or installation scheduling
   - Project already sold, planning next steps
   - Installation scheduling after contract signed
   - Rep calling about job in production queue
   - Phrases: "installation of your roof", "next steps", "your project", "moving forward"
   
4. **service_call** - Existing customer with service issue
   - Problem with completed work
   - Warranty claim or defect
   - Maintenance request on existing system
   - Phrases: "problem with my roof", "warranty", "leak", "issue with the work"
   
5. **quote_only** - Customer wants phone quote without inspection
   - Asking "how much" without wanting in-person visit
   - Price-focused inquiry without willingness to schedule
   - Rep should educate on need for in-person assessment
   - Phrases: "just need a quick quote", "how much do you charge", "ballpark price"

**IMPORTANT CONTEXT CLUES:**
- "My neighbor" / "my relative" / "different property" / "my other house" = new_inquiry
- "Confirming the visit" / "see you tomorrow" / "reminder call" = confirmation
- "Installation date" / "your project" / "moving forward" / "next steps" = follow_up
- "Problem with" / "warranty" / "leak" / "issue" = service_call
- "How much" / "quick quote" / "ballpark" = quote_only
- Customer mentions address DIFFERENT from history = new_inquiry
- REP calling customer about scheduled job = confirmation or follow_up
- Customer calling about job that's "in the queue" = follow_up

**OUTPUT FORMAT (JSON only):**
{{
    "call_type": "new_inquiry" | "confirmation" | "follow_up" | "service_call" | "quote_only",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of why this classification",
    "property_same": true/false/null,
    "key_indicator": "The phrase or context that determined this"
}}

Analyze and output JSON only:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You analyze call transcripts to classify call types with semantic understanding. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            result["time_since_last_days"] = time_since_last
            
            logger.info(f"Call type detected: {result.get('call_type')} (confidence: {result.get('confidence')})")
            return result
            
        except Exception as e:
            logger.error(f"Call type detection failed: {e}")
            # Default to new_inquiry on error
            return {
                "call_type": "new_inquiry",
                "confidence": 0.5,
                "reasoning": f"Detection failed, defaulting to new_inquiry: {str(e)}",
                "property_same": None,
                "key_indicator": "error_fallback",
                "time_since_last_days": time_since_last
            }
    
    def _build_history_context(self, history: Dict[str, Any]) -> str:
        """Build readable context from customer history."""
        last = history.get("last_interaction", {})
        
        # Format previous interactions
        interactions_summary = ""
        previous_calls = history.get("previous_calls", [])
        if previous_calls:
            recent = previous_calls[:3]  # Last 3 calls
            for i, call in enumerate(recent):
                interactions_summary += f"\n  {i+1}. {call.get('date', 'Unknown')}: {call.get('service_type', 'Unknown')} - {call.get('outcome', 'Unknown')}"
        
        return f"""
- Customer Name: {history.get("name", "Unknown")}
- Last Contact Date: {last.get("date", "Unknown")}
- Last Booking Status: {last.get("booking_status", "Unknown")}
- Last Service Type: {last.get("service_type", "Unknown")}
- Property Address on File: {last.get("address", "Unknown")}
- Previous Call Outcome: {last.get("call_outcome", "Unknown")}
- Total Previous Interactions: {len(previous_calls)}
- Recent Interaction History:{interactions_summary if interactions_summary else " None"}
"""
    
    def _calculate_days_since_last(self, history: Dict[str, Any]) -> Optional[int]:
        """Calculate days since last interaction."""
        try:
            last = history.get("last_interaction", {})
            last_date_str = last.get("date")
            
            if not last_date_str:
                return None
            
            # Handle different date formats
            if isinstance(last_date_str, datetime):
                last_date = last_date_str
            else:
                # Try ISO format first
                try:
                    last_date = datetime.fromisoformat(last_date_str.replace('Z', '+00:00'))
                except:
                    # Try other common formats
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
            
            days = (datetime.now() - last_date.replace(tzinfo=None)).days
            return days
            
        except Exception as e:
            logger.warning(f"Could not calculate days since last interaction: {e}")
            return None


# Singleton instance
_call_type_detector: Optional[LLMCallTypeDetector] = None


def get_call_type_detector() -> LLMCallTypeDetector:
    """Get singleton call type detector instance."""
    global _call_type_detector
    if _call_type_detector is None:
        _call_type_detector = LLMCallTypeDetector()
    return _call_type_detector

