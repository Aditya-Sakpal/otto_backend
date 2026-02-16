"""
Qualification Extraction Prompts

All prompts related to customer qualification (BANT, appointment booking, customer info)
"""

from typing import Dict, Any, Optional, List
from .base_prompts import (
    HOME_SERVICES_CONTEXT,
    PROPERTY_DETAILS_EXTRACTION,
    DECISION_MAKER_CONTEXT,
    URGENCY_EXTRACTION_CONTEXT
)


def get_core_qualification_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    previous_qualification: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for extracting BANT qualification scores"""
    
    previous_str = ""
    if previous_qualification:
        prev_scores = previous_qualification.get('bant_scores', {})
        previous_str = f"""
**PREVIOUS BANT SCORES (for context):**
- Need: {prev_scores.get('need', 'N/A')}
- Budget: {prev_scores.get('budget', 'N/A')}
- Authority: {prev_scores.get('authority', 'N/A')}
- Timeline: {prev_scores.get('timeline', 'N/A')}
"""
    
    return f"""Analyze this call chunk and assess customer qualification using BANT framework.

{HOME_SERVICES_CONTEXT}
{URGENCY_EXTRACTION_CONTEXT}

{previous_str}

**TRANSCRIPT CHUNK:**
{chunk_text}

**BANT FRAMEWORK:**

1. **Need (0.0-1.0):**
   - 1.0: Clear, urgent problem stated explicitly
   - 0.7: Problem mentioned but not urgent
   - 0.4: Exploring/researching, no immediate need
   - 0.0: No need expressed

2. **Budget (0.0-1.0):**
   - 1.0: Budget confirmed, ready to proceed
   - 0.7: Budget range mentioned, financing options discussed
   - 0.4: Price-conscious but not dismissive
   - 0.0: No budget discussion or can't afford

3. **Authority (0.0-1.0):**
   - 1.0: Decision maker on the call, can authorize work
   - 0.7: Can influence decision, will discuss with others
   - 0.4: Information gatherer, multiple stakeholders involved
   - 0.0: No authority to make decision

4. **Timeline (0.0-1.0):**
   - 1.0: Immediate (within 1-2 weeks)
   - 0.7: Soon (within 1 month)
   - 0.4: Future (1-3 months)
   - 0.0: No timeline or far future

**OUTPUT FORMAT (JSON):**
{{
  "bant_scores": {{
    "need": <0.0-1.0>,
    "budget": <0.0-1.0>,
    "authority": <0.0-1.0>,
    "timeline": <0.0-1.0>
  }},
  "overall_score": <0.0-1.0>,
  "qualification_notes": {{
    "need_evidence": "Quote or evidence from transcript",
    "budget_evidence": "Quote or evidence from transcript",
    "authority_evidence": "Quote or evidence from transcript",
    "timeline_evidence": "Quote or evidence from transcript"
  }},
  "urgency_signals": ["Signal 1", "Signal 2"],
  "budget_indicators": ["Indicator 1", "Indicator 2"]
}}

**IMPORTANT:**
- Score based on evidence in the transcript
- Provide actual quotes for evidence fields
- Don't infer beyond what is said

Output ONLY valid JSON."""


def get_appointment_details_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    previous_appointment: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for extracting appointment/booking information"""
    
    previous_str = ""
    if previous_appointment:
        previous_str = f"""
**PREVIOUS APPOINTMENT INFO (for context):**
- Status: {previous_appointment.get('booking_status', 'N/A')}
- Date: {previous_appointment.get('appointment_date', 'N/A')}
- Confirmed: {previous_appointment.get('appointment_confirmed', 'N/A')}
"""
    
    return f"""Extract appointment and booking information from this call chunk.

{HOME_SERVICES_CONTEXT}

{previous_str}

**TRANSCRIPT CHUNK:**
{chunk_text}

**BOOKING STATUSES:**
- **booked**: Appointment scheduled and confirmed with date/time
- **pending_scheduling**: Interested, will schedule later
- **declined**: Customer declined appointment
- **not_needed**: Call type doesn't require appointment (e.g., follow-up question)
- **unknown**: No booking discussion

**APPOINTMENT TYPES:**
- in_home_consultation
- inspection
- estimate
- service_call
- follow_up
- other

**OUTPUT FORMAT (JSON):**
{{
  "booking_status": "booked|pending_scheduling|declined|not_needed|unknown",
  "appointment_type": "type from list above or null",
  "appointment_date": "ISO 8601 datetime or null",
  "appointment_confirmed": true|false,
  "appointment_details": {{
    "date_mentioned": "Exact phrase used (e.g., 'next Thursday', 'January 15th at 2pm')",
    "time_window": "Time window if mentioned",
    "location": "Address or location",
    "special_instructions": "Any special notes (e.g., 'gate code is 1234', 'back door')"
  }},
  "scheduling_notes": "Any relevant notes about scheduling"
}}

**IMPORTANT:**
- Capture the FULL datetime if mentioned (both day AND time)
- If only day mentioned without time, note that in appointment_details.date_mentioned
- Mark appointment_confirmed as true ONLY if explicitly confirmed by both parties
- If "next Monday" or similar, note the relative date in date_mentioned

Output ONLY valid JSON."""


def get_customer_intelligence_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    customer_history: Optional[Dict[str, Any]] = None,
    previous_intelligence: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for extracting customer information and intelligence"""
    
    history_str = ""
    if customer_history:
        history_str = f"""
**KNOWN CUSTOMER INFORMATION:**
- Name: {customer_history.get('name', 'Unknown')}
- Phone: {customer_history.get('phone', 'Unknown')}
- Email: {customer_history.get('email', 'Unknown')}
- Address: {customer_history.get('address', 'Unknown')}
"""
    
    return f"""Extract customer information and intelligence from this call chunk.

{HOME_SERVICES_CONTEXT}
{DECISION_MAKER_CONTEXT}

{history_str}

**TRANSCRIPT CHUNK:**
{chunk_text}

**TASK:**
Extract customer details with extreme accuracy. Pay special attention to:
- Names that are SPELLED OUT letter by letter
- Addresses that are SPELLED OUT or carefully enunciated
- Email addresses
- Phone numbers (don't extract the FROM number, extract MENTIONED numbers)
- Postal codes (get ALL digits)

**OUTPUT FORMAT (JSON):**
{{
  "customer_name": {{
    "full_name": "Full name as mentioned",
    "first_name": "First name",
    "last_name": "Last name",
    "spelled_out": true|false,
    "spelling": "If spelled: 'J-O-H-N S-M-I-T-H'",
    "confidence": <0.0-1.0>
  }},
  "contact_information": {{
    "phone": "Phone number if mentioned (not the caller ID)",
    "email": "Email address if provided",
    "preferred_contact_method": "phone|email|text|not_specified"
  }},
  "address": {{
    "full_address": "Complete address string",
    "street_address": "Street address (if spelled out, use spelled version)",
    "city": "City name",
    "state": "State",
    "postal_code": "COMPLETE postal code (all digits)",
    "spelled_out": true|false,
    "confidence": <0.0-1.0>
  }},
  "decision_makers": [
    {{
      "name": "Decision maker name",
      "relationship": "homeowner|spouse|parent|property_manager|other",
      "is_caller": true|false,
      "contact_info": "Contact info if different from main"
    }}
  ],
  "additional_contacts": [
    {{
      "name": "Name (e.g., 'my agent Deshay')",
      "role": "real_estate_agent|hoa_contact|family_member|other",
      "contact_info": "Phone/email if mentioned",
      "notes": "Relevant context"
    }}
  ],
  "notes": "Any other relevant customer intelligence"
}}

**CRITICAL:**
- If address/name is SPELLED OUT, capture the spelling and use it
- Get FULL postal code (85382, not 8538)
- Identify decision maker correctly (not just the caller)
- Don't use phone_number from call metadata - only extract if mentioned in call

Output ONLY valid JSON."""


def get_property_details_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    previous_property: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for extracting property-specific details"""
    
    return f"""Extract property details from this call chunk.

{HOME_SERVICES_CONTEXT}
{PROPERTY_DETAILS_EXTRACTION}

**TRANSCRIPT CHUNK:**
{chunk_text}

**TASK:**
Extract detailed property information relevant to home services.

**OUTPUT FORMAT (JSON):**
{{
  "property_details": {{
    "roof_type": "tile|shingle|metal|flat|tpo|epdm|unknown",
    "roof_age_years": <number or null>,
    "stories": "single|two|three|split_level|unknown",
    "hoa_status": "yes|no|unknown",
    "hoa_name": "HOA name if mentioned",
    "gated_community": true|false|null,
    "gate_access": "Gate code or access instructions",
    "has_solar": true|false|null,
    "solar_details": "Number of panels, location, etc.",
    "pets": "Description of pets (e.g., 'indoor cat', 'large dog')",
    "pet_notes": "Special notes (e.g., 'make sure rep likes cats')",
    "property_size": "Square footage or bedroom count if mentioned",
    "property_access_notes": "Any special access instructions",
    "current_issues": ["List of current problems or concerns"],
    "property_age": "Age of property if mentioned",
    "additional_details": "Any other relevant property information"
  }}
}}

**IMPORTANT:**
- Only extract what is explicitly mentioned
- Use null for unknown fields
- Capture contextual notes (e.g., pet preferences, access codes)
- Pay attention to details that help the service rep

Output ONLY valid JSON."""


__all__ = [
    'get_core_qualification_prompt',
    'get_appointment_details_prompt',
    'get_customer_intelligence_prompt',
    'get_property_details_prompt',
]

