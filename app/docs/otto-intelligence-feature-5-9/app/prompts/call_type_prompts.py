"""
Call Type Detection Prompts

Prompts for detecting call type (fresh_sales, follow_up_inquiry, existing_customer_service)
"""

from typing import Dict, Any, Optional
from .base_prompts import HOME_SERVICES_CONTEXT, JSON_OUTPUT_INSTRUCTION


def get_call_type_detection_prompt(
    transcript: str,
    customer_history: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for detecting call type"""
    history_context = ""
    if customer_history and customer_history.get("is_existing_customer"):
        history_context = f"""
**CUSTOMER HISTORY:**
- Existing customer: Yes
- Previous calls: {customer_history.get('total_calls', 0)}
- Last call date: {customer_history.get('last_call_date', 'Unknown')}
- Last status: {customer_history.get('last_booking_status', 'Unknown')}
- Last service: {customer_history.get('last_service_type', 'Unknown')}
"""
    
    return f"""Analyze this call and determine the call type.

{HOME_SERVICES_CONTEXT}

**TRANSCRIPT:**
{transcript}

{history_context}

**CALL TYPES:**
1. **fresh_sales** - New customer inquiry or new opportunity (even from existing customer for different property/need)
2. **follow_up_inquiry** - Existing customer following up on their pending job/appointment
3. **existing_customer_service** - Existing customer calling about service/issue with completed work

**DECISION LOGIC:**
- If customer mentions "I called before about X" or "following up on my appointment" → follow_up_inquiry
- If customer mentions issue with completed work or warranty → existing_customer_service  
- If customer is calling about a NEW property or NEW need (even if existing customer) → fresh_sales
- If no history and new inquiry → fresh_sales

**TASK:**
Determine the call type and provide reasoning.

**OUTPUT FORMAT (JSON):**
{{
  "call_type": "fresh_sales|follow_up_inquiry|existing_customer_service",
  "confidence": <0.0-1.0>,
  "reasoning": "Brief explanation of classification",
  "key_indicators": ["List of phrases or context that led to this classification"]
}}

{JSON_OUTPUT_INSTRUCTION}"""


__all__ = [
    'get_call_type_detection_prompt',
]

