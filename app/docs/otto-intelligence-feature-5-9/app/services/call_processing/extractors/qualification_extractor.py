"""
Qualification Extractor - Focused on BANT, booking status, and appointment details.

This is the most comprehensive extractor, handling:
- BANT scores (Budget, Authority, Need, Timeline)
- Booking and appointment details
- Customer information
- Address extraction
- Follow-up intelligence
- Property details (roof type, HOA, pets, etc.) - NEW
"""

from typing import Dict, Any, Optional
import json
import re
from ....config import get_settings
from ....core.llm import get_llm_client, get_active_model
from .home_services_context import (
    HOME_SERVICES_CONTEXT,
    PROPERTY_DETAILS_EXTRACTION,
    DECISION_MAKER_CONTEXT,
    URGENCY_EXTRACTION_CONTEXT
)
from ....utils.address_parser import parse_and_validate_address, enhance_address_with_validation
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class QualificationExtractor:
    """Extracts qualification, booking, and customer details using 3 specialized calls."""
    
    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.3  # Slightly higher for inference
        self.max_retries = 3  # Retry up to 3 times per extraction
    
    async def extract(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        customer_history: Optional[Dict[str, Any]] = None,
        previous_qualification: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract qualification section using MULTIPLE specialized calls for completeness.
        
        NEW APPROACH: Split into 4 focused calls to ensure all fields are extracted:
        1. Core Qualification (BANT, status, booking)
        2. Appointment Details (all appointment fields)
        3. Customer Intelligence (address, decision makers, follow-up)
        4. Property Details (roof type, HOA, pets, solar, etc.) - NEW
        
        Args:
            chunk_text: Transcript text
            call_context: Context about the call (date, timezone, company info)
            customer_history: Historical data about this customer from RAG
            previous_qualification: Previous qualification for merging
        
        Returns:
            Qualification section dictionary with ALL fields
        """
        # Validate chunk_text is not None
        if chunk_text is None:
            logger.error("chunk_text is None - cannot extract qualification")
            raise ValueError("chunk_text cannot be None")
        
        # Convert to string if not already (safety check)
        if not isinstance(chunk_text, str):
            logger.warning(f"chunk_text is not a string (type: {type(chunk_text)}), converting to string")
            chunk_text = str(chunk_text) if chunk_text else ""
        
        try:
            # Execute 4 specialized extractions in parallel
            import asyncio
            
            core_task = self._extract_core_qualification(
                chunk_text, call_context, customer_history, previous_qualification
            )
            
            appointment_task = self._extract_appointment_details(
                chunk_text, call_context, previous_qualification
            )
            
            intelligence_task = self._extract_customer_intelligence(
                chunk_text, call_context, customer_history, previous_qualification
            )
            
            property_task = self._extract_property_details(
                chunk_text, call_context, previous_qualification
            )
            
            # Wait for all 4 to complete
            core_result, appointment_result, intelligence_result, property_result = await asyncio.gather(
                core_task,
                appointment_task,
                intelligence_task,
                property_task,
                return_exceptions=True
            )
            
            # Handle failures
            if isinstance(core_result, Exception):
                logger.error(f"Core qualification extraction failed: {core_result}")
                core_result = self._get_default_core()
            
            if isinstance(appointment_result, Exception):
                logger.error(f"Appointment extraction failed: {appointment_result}")
                appointment_result = self._get_default_appointment(call_context)
            
            if isinstance(intelligence_result, Exception):
                logger.error(f"Intelligence extraction failed: {intelligence_result}")
                intelligence_result = self._get_default_intelligence()
            
            if isinstance(property_result, Exception):
                logger.error(f"Property details extraction failed: {property_result}")
                property_result = self._get_default_property_details()
            
            # Merge all 4 results
            result = {**core_result, **appointment_result, **intelligence_result, **property_result}
            
            # FIX 1: Cross-validate booking status with appointment confirmation
            result = self._cross_validate_booking_status(result)
            
            # FIX 2: Infer preferred_time_window from appointment_date
            result = self._infer_time_window(result)
            
            # FIX 3: Adjust BANT scores based on extracted signals
            try:
                result = self._adjust_bant_from_signals(result)
            except Exception as e:
                logger.error(f"_adjust_bant_from_signals failed: {e}", exc_info=True)
            
            # FIX 4: Validate customer name against transcript (prevent rep/customer confusion)
            try:
                result = self._validate_customer_name(result, chunk_text)
            except Exception as e:
                logger.error(f"_validate_customer_name failed: {e}", exc_info=True)
            
            # FIX 5: Validate follow_up_reason against transcript (prevent hallucination)
            try:
                result = self._validate_follow_up_reason(result, chunk_text)
            except Exception as e:
                logger.error(f"_validate_follow_up_reason failed: {e}", exc_info=True)
            
            # FIX 6: Flatten contact information from nested structure
            try:
                result = self._flatten_contact_info(result)
            except Exception as e:
                logger.error(f"_flatten_contact_info failed: {e}", exc_info=True)
            
            # FIX 7: Validate property details for common errors
            try:
                result = self._validate_property_details(result, chunk_text)
            except Exception as e:
                logger.error(f"_validate_property_details failed: {e}", exc_info=True)
            
            logger.info(f"Qualification extracted via 4 specialized calls (fields: {len(result)})")
            
            return result
            
        except Exception as e:
            logger.error(f"Qualification extraction failed: {e}")
            raise
    
    async def _extract_core_qualification(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        customer_history: Optional[Dict[str, Any]],
        previous_qualification: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract CORE qualification: BANT scores, qualification status, booking status.
        
        WITH RETRY LOGIC for JSON parsing and enum validation issues.
        """
        import re
        
        history_context = ""
        if customer_history:
            history_context = f"\n**CUSTOMER HISTORY:** {customer_history.get('last_interaction', {}).get('status', 'No history')}\n"
        
        prev_context = ""
        if previous_qualification:
            prev_context = f"""
**PREVIOUS QUALIFICATION:**
- Status: {previous_qualification.get('qualification_status', 'unknown')}
- Booking: {previous_qualification.get('booking_status', 'unknown')}
- BANT: Need={previous_qualification.get('bant_scores', {}).get('need', 0.5)}

UPDATE the above if new information is found, otherwise keep the same.
"""
        
        # Retry loop
        for attempt in range(self.max_retries):
            try:
                prompt = f"""Analyze this call and extract CORE QUALIFICATION DATA.

**TRANSCRIPT:**
{chunk_text}
{history_context}
{prev_context}

Extract ONLY these fields in JSON:

{{
  "bant_scores": {{
    "need": 0.8,
    "budget": 0.0,
    "timeline": 0.9,
    "authority": 1.0
  }},
  "overall_score": 0.675,
  "qualification_status": "warm",
  "booking_status": "not_booked",
  "call_outcome_category": "qualified_but_unbooked"
}}

**BANT SCORING (0.0-1.0):**

**1. NEED (0.0-1.0):**
- 1.0 = urgent need: "leak", "emergency", "urgent", "asap", "right away"
- 0.8 = clear need: specific problem described
- 0.5 = moderate need: general inquiry
- 0.0 = no clear need

**2. BUDGET (0.0-1.0):**
- 1.0 = budget confirmed: specific amount mentioned, approved budget
- 0.8 = budget available: "willing to pay", "I'll pay", "happy to pay extra", "money is not an issue"
- 0.5 = some budget discussion: asked about payment, pricing discussed
- 0.0 = NO budget signals: no mention of money, payment, or willingness to pay

⚠️ **CRITICAL:** "willing to pay extra" = 0.8-1.0 budget score (shows budget availability!)

**3. TIMELINE (0.0-1.0):**
- 1.0 = specific urgent timeline: "same-day", "today", "tomorrow", "this week", "10-day inspection period"
- 0.8 = specific timeline: "next week", "Friday", specific date mentioned
- 0.5 = general timeline: "soon", "when you can", "not urgent"
- 0.0 = NO timeline: no mention of when service is needed

⚠️ **CRITICAL:** "same-day repair", "10-day inspection period" = 1.0 timeline score (specific urgent need!)

**4. AUTHORITY (0.0-1.0):**
- 1.0 = decision maker: homeowner, business owner, can decide now
- 0.5 = needs to consult: "need to talk to spouse", "let me check with my boss"
- 0.0 = not decision maker: tenant (needs landlord), assistant (needs manager)

**overall_score**: Average of all 4 BANT scores

**qualification_status** (EXACT ENUM):
- hot: 3+ BANT scores > 0.7, ready to buy
- warm: 2+ BANT scores > 0.5, qualified
- cold: Low scores, needs nurturing
- unqualified: Not a good fit

**booking_status** (EXACT ENUM):
- booked: Appointment scheduled
- not_booked: No appointment yet
- service_not_offered: We can't help them

**call_outcome_category** (EXACT ENUM):
- qualified_and_booked
- qualified_but_unbooked
- unqualified
- callback_scheduled
- information_gathered
- unknown

Output ONLY JSON with these 5 fields:"""
                
                # Refresh client/model inside retry loop to ensure freshness (optional but safe)
                self.model = get_active_model()
                self.client = get_llm_client()

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a BANT qualification specialist. Always respond in valid JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content
                
                # Try to parse JSON
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Core qualification JSON parse error (attempt {attempt + 1}/{self.max_retries}): {e}")
                    
                    # Attempt JSON repair
                    result_text = re.sub(r',\s*}', '}', result_text)  # Remove trailing commas
                    result_text = re.sub(r',\s*]', ']', result_text)
                    result_text = re.sub(r'[\x00-\x1f\x7f]', ' ', result_text)  # Remove control chars
                    
                    try:
                        result = json.loads(result_text)
                        logger.info(f"Core qualification JSON repaired successfully (attempt {attempt + 1})")
                    except:
                        if attempt < self.max_retries - 1:
                            logger.warning(f"JSON repair failed, retrying... (attempt {attempt + 1})")
                            continue
                        raise
                
                # Validate and fix enums
                result = self._validate_and_fix_core_enums(result)
                
                return result
                
            except Exception as e:
                logger.error(f"Core qualification extraction failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)  # Brief delay before retry
                    continue
                raise
        
        raise Exception(f"Core qualification extraction failed after {self.max_retries} attempts")
    
    async def _extract_appointment_details(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_qualification: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract APPOINTMENT details: All appointment-related fields.
        
        WITH RETRY LOGIC for JSON parsing and enum validation issues.
        """
        import re
        
        call_date = call_context.get("call_date", "")
        timezone = call_context.get("timezone", "UTC")
        
        prev_context = ""
        if previous_qualification:
            prev_appt = previous_qualification.get('appointment_date')
            if prev_appt:
                prev_context = f"\n**PREVIOUS APPOINTMENT:** {prev_appt}\n"
        
        # Retry loop
        for attempt in range(self.max_retries):
            try:
                prompt = f"""Analyze this call and extract ALL APPOINTMENT DETAILS.

**CALL CONTEXT:**
- Call Date: {call_date}
- Timezone: {timezone}

**TRANSCRIPT:**
{chunk_text}
{prev_context}

Extract ONLY appointment fields in JSON:

{{
  "appointment_confirmed": false,
  "appointment_date": null,
  "appointment_type": null,
  "appointment_timezone": "{timezone}",
  "appointment_time_confidence": 0.0,
  "preferred_time_window": null,
  "appointment_intent": null,
  "original_appointment_datetime": null,
  "new_requested_time": null,
  "service_requested": null,
  "service_not_offered_reason": null
}}

**FIELD INSTRUCTIONS:**

**appointment_confirmed** (boolean):
- true if specific date/time agreed
- false otherwise

**appointment_date** (ISO 8601 or null):
- RESOLVE relative dates using call date {call_date}:
  - "tomorrow" = {call_date} + 1 day
  - "next Thursday" = calculate next Thursday from {call_date}
  - "next week" = {call_date} + 7 days
- Format: "2026-01-21T10:00:00"
- null if no appointment

**appointment_type** (enum or null):
- "in-person" for physical visits
- "virtual" for video calls
- "phone" for phone consultations
- null if no appointment

**appointment_timezone**: "{timezone}"

**appointment_time_confidence** (0.0-1.0):
- 1.0 = exact date and time stated
- 0.7 = date stated, time vague
- 0.3 = "next week" - very vague
- 0.0 = no appointment

**preferred_time_window** (string or null):
- "morning", "afternoon", "evening", "any"
- null if not mentioned

**appointment_intent** (enum or null):
- "new" = scheduling new appointment
- "reschedule" = changing existing appointment
- "cancel" = canceling appointment
- "confirm" = confirming existing appointment
- null if no appointment discussion

**original_appointment_datetime** (ISO 8601 or null):
- ONLY for reschedules: the old appointment
- null otherwise

**new_requested_time** (ISO 8601 or null):
- ONLY for reschedules: the requested new time
- null otherwise

**service_requested** (string or null):
- What service does customer need?
- Example: "Roof repair", "AC installation"

**service_not_offered_reason** (string or null):
- ONLY if we can't help
- Why? "Outside service area", "Don't offer that service"

Output ONLY JSON with these 11 appointment fields:"""
                
                # Refresh client/model
                self.model = get_active_model()
                self.client = get_llm_client()

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an appointment scheduling specialist focused on extracting complete appointment details. Always respond in valid JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content
                
                # Try to parse JSON
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Appointment details JSON parse error (attempt {attempt + 1}/{self.max_retries}): {e}")
                    
                    # Attempt JSON repair
                    result_text = re.sub(r',\s*}', '}', result_text)
                    result_text = re.sub(r',\s*]', ']', result_text)
                    result_text = re.sub(r'[\x00-\x1f\x7f]', ' ', result_text)
                    
                    try:
                        result = json.loads(result_text)
                        logger.info(f"Appointment details JSON repaired successfully (attempt {attempt + 1})")
                    except:
                        if attempt < self.max_retries - 1:
                            logger.warning(f"JSON repair failed, retrying... (attempt {attempt + 1})")
                            continue
                        raise
                
                # Validate and fix enums
                result = self._validate_and_fix_appointment_enums(result)
                
                return result
                
            except Exception as e:
                logger.error(f"Appointment details extraction failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise
        
        raise Exception(f"Appointment details extraction failed after {self.max_retries} attempts")
    
    async def _extract_customer_intelligence(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        customer_history: Optional[Dict[str, Any]],
        previous_qualification: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract CUSTOMER INTELLIGENCE: Address, customer info, decision makers, urgency, follow-up.
        
        WITH RETRY LOGIC for JSON parsing issues.
        """
        import re
        
        company_service_area = call_context.get("company_service_area", "")
        
        prev_context = ""
        if previous_qualification:
            prev_name = previous_qualification.get('customer_name')
            prev_address = previous_qualification.get('service_address_raw')
            if prev_name or prev_address:
                prev_context = f"\n**PREVIOUS DATA:** Name={prev_name}, Address={prev_address}\n"
        
        # Retry loop
        for attempt in range(self.max_retries):
            try:
                prompt = f"""Analyze this call and extract CUSTOMER INTELLIGENCE.

**COMPANY SERVICE AREA:** {company_service_area}

**TRANSCRIPT:**
{chunk_text}
{prev_context}

Extract customer intelligence fields in JSON:

{{
  "service_address_raw": null,
  "service_address_structured": {{
    "line1": null,
    "city": null,
    "state": null,
    "postal_code": null,
    "country": "US"
  }},
  "address_confidence": 0.0,
  "customer_name": null,
  "customer_name_confidence": 0.0,
  "decision_makers": [],
  "urgency_signals": [],
  "budget_indicators": [],
  "confidence_score": 0.5,
  "follow_up_required": false,
  "follow_up_reason": null,
  "is_existing_customer": false
}}

**FIELD INSTRUCTIONS:**

**service_address_raw** (string or null):
- Full address as mentioned in call
- Example: "1384 East Natasha Drive, Casagrande, Arizona"

**service_address_structured** (object):
- Parse address into components:
  - line1: "1384 East Natasha Drive"
  - city: "Casagrande"
  - state: "Arizona"
  - postal_code: "85122" (if mentioned)
  - country: "US"

**address_confidence** (0.0-1.0):
- 1.0 = complete address with street, city, state
- 0.7 = partial address
- 0.0 = no address

**customer_name** (string or null):
- Extract the CUSTOMER/HOME_OWNER's name (NOT the rep's name)
- ⚠️⚠️⚠️ CRITICAL: REP vs CUSTOMER NAME IDENTIFICATION ⚠️⚠️⚠️

**HOW TO IDENTIFY CUSTOMER NAME:**
1. Look for home_owner line: "My name is X" → X is customer
2. Look for rep greeting: "Hi X" or "Hey X" → X is customer  
3. Look for rep calling back: "Hey X, it's [rep name]" → X is customer, [rep name] is NOT customer

**HOW TO IDENTIFY REP NAME (DO NOT USE AS CUSTOMER):**
1. "it's [name]" after greeting = REP introducing themselves
2. "this is [name]" in rep line = REP introducing themselves
3. "My name is [name]" in customer_rep line = REP introducing themselves

**EXAMPLE:**
- "customer_rep: Hey Jim, it's Raven again" 
  → "Jim" = CUSTOMER (being greeted)
  → "Raven" = REP (introducing self) - DO NOT use as customer name!

- First name sufficient if full name not given

**customer_name_confidence** (0.0-1.0):
- 1.0 = name clearly stated by home_owner
- 0.5 = possible name (rep used a name)
- 0.0 = no name

**decision_makers** (array):
- List people with decision authority
- Example: ["John (homeowner)", "Sarah (wife)"]
- Empty if none identified

**urgency_signals** (array):
- ONLY extract phrases that are ACTUALLY IN THE TRANSCRIPT
- ⚠️ DO NOT include "same-day", "ASAP", "urgent" unless customer LITERALLY said these words
- ⚠️ DO NOT copy examples from this prompt - extract ACTUAL phrases from transcript
- Look for: timeline mentions, deadline references, urgency language
- Empty if no urgency signals are found in the transcript

**budget_indicators** (array):
- ONLY extract phrases that are ACTUALLY IN THE TRANSCRIPT
- ⚠️ DO NOT include "willing to pay extra" unless customer LITERALLY said these words
- ⚠️ DO NOT copy examples from this prompt - extract ACTUAL phrases from transcript
- Look for: budget mentions, payment willingness, price discussions
- Empty if no budget indicators are found in the transcript

**confidence_score** (0.0-1.0):
- Overall confidence in this intelligence

**follow_up_required** (boolean):
- true if lead needs follow-up
- false if closed/booked/disqualified

**follow_up_reason** (string or null):
- Brief sales briefing for next caller
- ONLY include information EXPLICITLY mentioned in the transcript
- ⚠️ DO NOT assume or hallucinate details not in transcript
- ⚠️ DO NOT include "leak" unless customer mentioned a leak
- ⚠️ DO NOT include "worsening" unless customer said something is getting worse
- Example: "Customer qualified but needs faster timeline. Currently quoted 7-9 weeks, may look elsewhere. Strong need (leak worsening) but timing concern."
- null if no follow-up needed

**is_existing_customer** (boolean):
- true if customer mentions they are an existing/previous/returning customer
- true if customer refers to previous service, jobs, or interactions with the company
- false if this appears to be a new customer or first-time caller
- Look for phrases like: "I'm a customer", "you did work for me before", "I used your service before", "last time you came out", "previous job"

Output ONLY JSON with these 11 intelligence fields:"""
                
                # Refresh client/model
                self.model = get_active_model()
                self.client = get_llm_client()

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a customer intelligence analyst focused on extracting strategic customer data. Always respond in valid JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content
                
                # Try to parse JSON
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Customer intelligence JSON parse error (attempt {attempt + 1}/{self.max_retries}): {e}")
                    
                    # Attempt JSON repair
                    result_text = re.sub(r',\s*}', '}', result_text)
                    result_text = re.sub(r',\s*]', ']', result_text)
                    result_text = re.sub(r'[\x00-\x1f\x7f]', ' ', result_text)
                    
                    try:
                        result = json.loads(result_text)
                        logger.info(f"Customer intelligence JSON repaired successfully (attempt {attempt + 1})")
                    except:
                        if attempt < self.max_retries - 1:
                            logger.warning(f"JSON repair failed, retrying... (attempt {attempt + 1})")
                            continue
                        raise
                
                # No enum validation needed for intelligence fields (all strings/arrays)
                
                # FIX 4: Post-process to be more aggressive in extraction
                result = self._enhance_intelligence_extraction(result, chunk_text, call_context)
                
                return result
                
            except Exception as e:
                logger.error(f"Customer intelligence extraction failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise
        
        raise Exception(f"Customer intelligence extraction failed after {self.max_retries} attempts")
    
    def _get_default_core(self) -> Dict[str, Any]:
        """Default core qualification"""
        return {
            "bant_scores": {"need": 0.5, "budget": 0.0, "timeline": 0.5, "authority": 0.5},
            "overall_score": 0.375,
            "qualification_status": "cold",
            "booking_status": "not_booked",
            "call_outcome_category": "unknown"
        }
    
    def _get_default_appointment(self, call_context: Dict[str, Any]) -> Dict[str, Any]:
        """Default appointment details"""
        # FIX 3: Use actual timezone from call_context
        timezone = call_context.get("timezone", "UTC")
        return {
            "appointment_confirmed": False,
            "appointment_date": None,
            "appointment_type": None,
            "appointment_timezone": timezone,
            "appointment_time_confidence": 0.0,
            "preferred_time_window": None,
            "appointment_intent": None,
            "original_appointment_datetime": None,
            "new_requested_time": None,
            "service_requested": None,
            "service_not_offered_reason": None
        }
    
    def _cross_validate_booking_status(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        FIX 1: Ensure booking_status and call_outcome_category sync with appointment_confirmed.
        
        If appointment is confirmed, booking must be 'booked' and outcome 'qualified_and_booked'.
        """
        if result.get("appointment_confirmed") == True:
            if result.get("booking_status") != "booked":
                logger.warning(f"Cross-validation: appointment_confirmed=True but booking_status={result.get('booking_status')}. Fixing to 'booked'")
                result["booking_status"] = "booked"
            
            if result.get("call_outcome_category") != "qualified_and_booked":
                logger.warning(f"Cross-validation: appointment_confirmed=True but call_outcome_category={result.get('call_outcome_category')}. Fixing to 'qualified_and_booked'")
                result["call_outcome_category"] = "qualified_and_booked"
        
        return result
    
    def _infer_time_window(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        FIX 2: Infer preferred_time_window from appointment_date if it has a time component.
        
        Morning: 5am-12pm, Afternoon: 12pm-5pm, Evening: 5pm-9pm
        """
        from datetime import datetime
        
        # If time_window is already set, don't override
        if result.get("preferred_time_window"):
            return result
        
        # Try to infer from appointment_date
        appointment_date = result.get("appointment_date")
        if appointment_date:
            try:
                # Parse if it's a string
                if isinstance(appointment_date, str):
                    dt = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
                else:
                    dt = appointment_date
                
                hour = dt.hour
                
                # Infer window from hour
                if 5 <= hour < 12:
                    result["preferred_time_window"] = "morning"
                    logger.info(f"Inferred time_window='morning' from appointment hour {hour}")
                elif 12 <= hour < 17:
                    result["preferred_time_window"] = "afternoon"
                    logger.info(f"Inferred time_window='afternoon' from appointment hour {hour}")
                elif 17 <= hour < 21:
                    result["preferred_time_window"] = "evening"
                    logger.info(f"Inferred time_window='evening' from appointment hour {hour}")
                
            except Exception as e:
                logger.debug(f"Could not infer time_window from appointment_date: {e}")
        
        return result
    
    def _adjust_bant_from_signals(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        FIX 3: Adjust BANT scores based on extracted urgency_signals and budget_indicators.
        
        The problem: Core BANT extraction happens in a separate LLM call from intelligence extraction.
        The BANT scorer might miss signals that were captured in urgency_signals/budget_indicators.
        
        This post-processor ensures consistency:
        - If urgency_signals exist but timeline=0.0, boost timeline
        - If budget_indicators exist but budget=0.0, boost budget
        """
        bant_scores = result.get("bant_scores", {})
        urgency_signals = result.get("urgency_signals", [])
        budget_indicators = result.get("budget_indicators", [])
        
        original_timeline = bant_scores.get("timeline", 0.0)
        original_budget = bant_scores.get("budget", 0.0)
        
        adjusted = False
        
        # TIMELINE ADJUSTMENT
        if urgency_signals and original_timeline < 0.5:
            # Check for high-urgency signals
            high_urgency = ["same-day", "today", "tomorrow", "urgent", "asap", "emergency", "inspection period"]
            medium_urgency = ["this week", "next week", "friday", "saturday", "monday"]
            
            has_high_urgency = any(
                any(signal_word in sig.lower() for signal_word in high_urgency)
                for sig in urgency_signals
                if isinstance(sig, str)
            )
            
            has_medium_urgency = any(
                any(signal_word in sig.lower() for signal_word in medium_urgency)
                for sig in urgency_signals
                if isinstance(sig, str)
            )
            
            if has_high_urgency:
                bant_scores["timeline"] = max(original_timeline, 1.0)
                logger.warning(f"BANT Adjustment: timeline {original_timeline} → 1.0 (high urgency signals: {urgency_signals})")
                adjusted = True
            elif has_medium_urgency:
                bant_scores["timeline"] = max(original_timeline, 0.8)
                logger.warning(f"BANT Adjustment: timeline {original_timeline} → 0.8 (medium urgency signals: {urgency_signals})")
                adjusted = True
        
        # BUDGET ADJUSTMENT
        if budget_indicators and original_budget < 0.5:
            # Check for budget availability signals
            budget_available = ["willing to pay", "i'll pay", "happy to pay", "can pay", "money is not", "have budget"]
            budget_discussed = ["payment", "price", "cost", "estimate", "quote"]
            
            has_budget_available = any(
                any(signal_word in indicator.lower() for signal_word in budget_available)
                for indicator in budget_indicators
                if isinstance(indicator, str)
            )
            
            has_budget_discussed = any(
                any(signal_word in indicator.lower() for signal_word in budget_discussed)
                for indicator in budget_indicators
                if isinstance(indicator, str)
            )
            
            if has_budget_available:
                bant_scores["budget"] = max(original_budget, 0.8)
                logger.warning(f"BANT Adjustment: budget {original_budget} → 0.8 (budget available: {budget_indicators})")
                adjusted = True
            elif has_budget_discussed:
                bant_scores["budget"] = max(original_budget, 0.5)
                logger.warning(f"BANT Adjustment: budget {original_budget} → 0.5 (budget discussed: {budget_indicators})")
                adjusted = True
        
        # RECALCULATE OVERALL SCORE if adjusted
        if adjusted:
            need = bant_scores.get("need", 0.0)
            budget = bant_scores.get("budget", 0.0)
            timeline = bant_scores.get("timeline", 0.0)
            authority = bant_scores.get("authority", 0.0)
            
            original_overall = result.get("overall_score", 0.0)
            new_overall = (need + budget + timeline + authority) / 4.0
            
            result["overall_score"] = new_overall
            result["bant_scores"] = bant_scores
            
            logger.info(f"BANT Overall Score adjusted: {original_overall:.2f} → {new_overall:.2f}")
            
            # Re-evaluate qualification_status based on new scores
            high_scores = sum(1 for score in [need, budget, timeline, authority] if score > 0.7)
            medium_scores = sum(1 for score in [need, budget, timeline, authority] if score > 0.5)
            
            if high_scores >= 3:
                result["qualification_status"] = "hot"
            elif medium_scores >= 2:
                result["qualification_status"] = "warm"
            else:
                result["qualification_status"] = "cold"
        
        return result
    
    def _validate_customer_name(self, result: Dict[str, Any], transcript: str) -> Dict[str, Any]:
        """
        FIX 4: Validate customer name against transcript patterns.
        
        Problem: LLM confuses rep name with customer name (e.g., "Hey Jim, it's Raven" → LLM picks "Raven" as customer)
        
        Solution: Use pattern matching to identify:
        - Rep self-introduction: "it's [name]", "this is [name]" in customer_rep lines
        - Customer name patterns: "my name is [name]" in home_owner lines, greeting patterns
        """
        import re
        
        customer_name = result.get("customer_name")
        
        # Ensure customer_name exists and is a string
        if not customer_name or not isinstance(customer_name, str):
            if customer_name:  # Log only if it exists but wrong type
                logger.warning(f"customer_name is not a valid string (type: {type(customer_name)}), skipping validation")
            return result
        
        if not transcript or not isinstance(transcript, str):
            logger.warning("Transcript is None or not a string, skipping customer name validation")
            return result
        
        customer_name_lower = customer_name.lower().strip()
        transcript_lower = transcript.lower()
        
        # Pattern 1: Check if name appears after "it's" (likely rep introducing themselves)
        rep_intro_patterns = [
            rf"it's\s+{re.escape(customer_name_lower)}",  # "it's Raven"
            rf"this\s+is\s+{re.escape(customer_name_lower)}",  # "this is Raven"
            rf"my\s+name\s+is\s+{re.escape(customer_name_lower)}.*customer_rep",  # rep saying their name
        ]
        
        is_likely_rep_name = False
        for pattern in rep_intro_patterns:
            if re.search(pattern, transcript_lower):
                is_likely_rep_name = True
                break
        
        # Pattern 2: Check for actual customer name indicators
        # Look for patterns where rep greets someone BEFORE introducing themselves
        greeting_pattern = rf"(hey|hi)\s+(\w+).*it's\s+{re.escape(customer_name_lower)}"
        greeting_match = re.search(greeting_pattern, transcript_lower)
        
        if greeting_match and is_likely_rep_name:
            # The name after "hey/hi" is likely the customer
            actual_customer_name = greeting_match.group(2)
            logger.warning(f"Customer name correction: '{customer_name}' appears to be rep name. "
                          f"Found actual customer name: '{actual_customer_name}'")
            result["customer_name"] = actual_customer_name.title()
            result["customer_name_confidence"] = 0.7
            
            # Also update decision_makers if present
            if result.get("decision_makers"):
                result["decision_makers"] = [
                    dm.replace(customer_name, actual_customer_name.title()) 
                    for dm in result["decision_makers"]
                ]
        
        # Pattern 3: Check for "my name is X" in home_owner lines
        homeowner_name_pattern = r"home_owner:.*my\s+name\s+is\s+(\w+)"
        homeowner_match = re.search(homeowner_name_pattern, transcript_lower)
        
        if homeowner_match:
            actual_name = homeowner_match.group(1).title()
            if actual_name.lower() != customer_name_lower:
                logger.warning(f"Customer name correction: Found 'my name is {actual_name}' in home_owner line")
                result["customer_name"] = actual_name
                result["customer_name_confidence"] = 1.0
        
        return result
    
    def _validate_follow_up_reason(self, result: Dict[str, Any], transcript: str) -> Dict[str, Any]:
        """
        FIX 5: Validate follow_up_reason against transcript.
        
        Problem: LLM hallucinates details like "leak worsening" when no leak is mentioned.
        
        Solution: Check key claims in follow_up_reason against transcript.
        """
        follow_up_reason = result.get("follow_up_reason")
        
        # Ensure follow_up_reason exists and is a string
        if not follow_up_reason or not isinstance(follow_up_reason, str):
            if follow_up_reason:  # Log only if it exists but wrong type
                logger.warning(f"follow_up_reason is not a valid string (type: {type(follow_up_reason)}), skipping validation")
            return result
        
        if not transcript or not isinstance(transcript, str):
            logger.warning("Transcript is None or not a string, skipping follow-up reason validation")
            return result
        
        transcript_lower = transcript.lower()
        reason_lower = follow_up_reason.lower()
        
        # List of commonly hallucinated phrases and their required transcript evidence
        hallucination_checks = [
            ("leak", ["leak", "leaking", "water coming"]),
            ("worsening", ["worsening", "getting worse", "worse"]),
            ("emergency", ["emergency", "urgent", "asap"]),
            ("insurance deadline", ["insurance", "deadline"]),
            ("7-9 weeks", ["7", "9", "weeks", "week"]),
            ("4-6 weeks", ["4", "6", "weeks", "week"]),
        ]
        
        cleaned_reason = follow_up_reason
        
        for hallucinated_phrase, required_evidence in hallucination_checks:
            if hallucinated_phrase in reason_lower:
                # Check if ANY evidence exists in transcript
                has_evidence = any(evidence in transcript_lower for evidence in required_evidence)
                
                if not has_evidence:
                    logger.warning(f"Follow-up reason hallucination detected: '{hallucinated_phrase}' not in transcript. Removing.")
                    # Remove the hallucinated part
                    cleaned_reason = re.sub(
                        rf'\b{re.escape(hallucinated_phrase)}\b[^.]*\.?',
                        '',
                        cleaned_reason,
                        flags=re.IGNORECASE
                    )
        
        # Clean up the result
        cleaned_reason = re.sub(r'\s+', ' ', cleaned_reason).strip()
        cleaned_reason = re.sub(r'\s*\.\s*\.', '.', cleaned_reason)
        
        if cleaned_reason and len(cleaned_reason) > 10:
            result["follow_up_reason"] = cleaned_reason
        else:
            result["follow_up_reason"] = None
            result["follow_up_required"] = False
        
        return result
    
    def _get_default_intelligence(self) -> Dict[str, Any]:
        """Default customer intelligence"""
        return {
            "service_address_raw": None,
            "service_address_structured": {
                "line1": None,
                "city": None,
                "state": None,
                "postal_code": None,
                "country": "US"
            },
            "address_confidence": 0.0,
            "customer_name": None,
            "customer_name_confidence": 0.0,
            "decision_makers": [],
            "urgency_signals": [],
            "budget_indicators": [],
            "confidence_score": 0.5,
            "follow_up_required": False,
            "follow_up_reason": None,
            "is_existing_customer": False
        }
    
    def _get_default_property_details(self) -> Dict[str, Any]:
        """Default property details for home services"""
        return {
            "property_details": {
                "roof_type": None,
                "roof_age_years": None,
                "stories": None,
                "hoa_status": None,
                "gated_community": None,
                "has_solar": None,
                "pets": None,
                "property_access_notes": None,
                "roof_condition": None,
                "special_features": []
            }
        }
    
    async def _extract_property_details(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_qualification: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract PROPERTY details specific to home services.
        
        Extracts: roof type, age, HOA status, pets, solar panels, access notes, etc.
        """
        import re
        
        prev_context = ""
        if previous_qualification:
            prev_props = previous_qualification.get('property_details', {})
            if prev_props:
                prev_context = f"\n**PREVIOUS PROPERTY INFO:** {json.dumps(prev_props)}\n"
        
        for attempt in range(self.max_retries):
            try:
                prompt = f"""Extract PROPERTY DETAILS from this home services call.

{HOME_SERVICES_CONTEXT}

**TRANSCRIPT:**
{chunk_text}
{prev_context}

{PROPERTY_DETAILS_EXTRACTION}

Extract ONLY these fields in JSON:

{{
  "property_details": {{
    "roof_type": "tile" | "shingle" | "flat" | "metal" | "foam" | null,
    "roof_age_years": 14,
    "stories": "single" | "two" | "multi" | null,
    "hoa_status": "yes" | "no" | null,
    "gated_community": true | false | null,
    "has_solar": true | false | null,
    "pets": "indoor cat" | "dog in backyard" | null,
    "property_access_notes": "Gate code 1234" | null,
    "roof_condition": "leaking in 3 areas" | null,
    "special_features": ["skylight", "chimney"]
  }}
}}

**EXTRACTION RULES:**
- ONLY extract what is EXPLICITLY mentioned in the transcript
- DO NOT guess or infer property details
- null = not mentioned (this is fine, most fields won't be mentioned)
- Include specific details like "single story tile roof" → roof_type: "tile", stories: "single"

Output ONLY valid JSON:"""

                # Refresh client/model
                self.model = get_active_model()
                self.client = get_llm_client()

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a property details specialist for home services. Extract only what is mentioned. Always respond in valid JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,  # Low for extraction accuracy
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content
                
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Property details JSON parse error (attempt {attempt + 1}): {e}")
                    result_text = re.sub(r',\s*}', '}', result_text)
                    result_text = re.sub(r',\s*]', ']', result_text)
                    try:
                        result = json.loads(result_text)
                    except:
                        if attempt < self.max_retries - 1:
                            continue
                        raise
                
                # Ensure structure
                if "property_details" not in result:
                    result = {"property_details": result}
                
                return result
                
            except Exception as e:
                logger.error(f"Property details extraction failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise
        
        return self._get_default_property_details()
    
    def _enhance_intelligence_extraction(
        self,
        result: Dict[str, Any],
        chunk_text: str,
        call_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        FIX 4: Be more aggressive in intelligence extraction.
        
        - If customer confirmed appointment, they're likely a decision maker
        - If state is mentioned in address, confidence should be > 0
        - Extract urgency signals from common phrases
        """
        import re
        
        # If customer_name exists and no decision_makers, assume customer is decision maker
        if result.get("customer_name") and not result.get("decision_makers"):
            customer_name = result["customer_name"]
            result["decision_makers"] = [f"{customer_name} (homeowner/customer)"]
            logger.info(f"Inferred decision maker: {customer_name}")
        
        # If address has state or city, bump up confidence
        address_structured = result.get("service_address_structured", {})
        if (address_structured.get("state") or address_structured.get("city")) and result.get("address_confidence", 0) == 0:
            if address_structured.get("state") and address_structured.get("city"):
                result["address_confidence"] = 0.6
            elif address_structured.get("state"):
                result["address_confidence"] = 0.3
            elif address_structured.get("city"):
                result["address_confidence"] = 0.4
            logger.info(f"Adjusted address_confidence to {result['address_confidence']}")
        
        # Extract urgency signals from text if not already populated
        if not result.get("urgency_signals"):
            urgency_signals = []
            urgency_patterns = [
                r"(asap|urgent|emergency|immediately)",
                r"(need.{0,20}(soon|quickly|fast))",
                r"(getting worse|leak|damage)",
                r"(deadline|insurance|claim)",
            ]
            
            for pattern in urgency_patterns:
                matches = re.findall(pattern, chunk_text.lower(), re.IGNORECASE)
                if matches:
                    # Extract surrounding context (20 chars before and after)
                    for match in matches:
                        match_str = match if isinstance(match, str) else match[0]
                        idx = chunk_text.lower().find(match_str.lower())
                        if idx != -1:
                            context = chunk_text[max(0, idx-20):min(len(chunk_text), idx+len(match_str)+20)].strip()
                            urgency_signals.append(context)
            
            if urgency_signals:
                result["urgency_signals"] = urgency_signals[:3]  # Top 3
                logger.info(f"Extracted {len(urgency_signals)} urgency signals")
        
        return result
    
    def _validate_and_fix_core_enums(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and auto-fix enum values in core qualification."""
        
        VALID_QUALIFICATION_STATUS = {"hot", "warm", "cold", "unqualified"}
        VALID_BOOKING_STATUS = {"booked", "not_booked", "service_not_offered"}
        VALID_CALL_OUTCOME = {
            "qualified_and_booked", "qualified_but_unbooked", "unqualified",
            "callback_scheduled", "information_gathered", "unknown"
        }
        
        # Fix qualification_status
        if "qualification_status" in result:
            status = result["qualification_status"]
            if status and isinstance(status, str) and status not in VALID_QUALIFICATION_STATUS:
                # Try fuzzy match
                if "hot" in status.lower():
                    result["qualification_status"] = "hot"
                elif "warm" in status.lower():
                    result["qualification_status"] = "warm"
                elif "cold" in status.lower():
                    result["qualification_status"] = "cold"
                else:
                    result["qualification_status"] = "cold"
                logger.warning(f"Auto-fixed qualification_status: '{status}' → '{result['qualification_status']}'")
        
        # Fix booking_status
        if "booking_status" in result:
            status = result["booking_status"]
            if status and isinstance(status, str) and status not in VALID_BOOKING_STATUS:
                if "book" in status.lower() or "scheduled" in status.lower():
                    result["booking_status"] = "booked"
                elif "not" in status.lower():
                    result["booking_status"] = "not_booked"
                else:
                    result["booking_status"] = "not_booked"
                logger.warning(f"Auto-fixed booking_status: '{status}' → '{result['booking_status']}'")
        
        # Fix call_outcome_category
        if "call_outcome_category" in result:
            outcome = result["call_outcome_category"]
            if outcome and isinstance(outcome, str) and outcome not in VALID_CALL_OUTCOME:
                # Map common variations
                if "qualified" in outcome.lower() and "book" in outcome.lower():
                    result["call_outcome_category"] = "qualified_and_booked"
                elif "qualified" in outcome.lower():
                    result["call_outcome_category"] = "qualified_but_unbooked"
                elif "unqualified" in outcome.lower():
                    result["call_outcome_category"] = "unqualified"
                else:
                    result["call_outcome_category"] = "unknown"
                logger.warning(f"Auto-fixed call_outcome_category: '{outcome}' → '{result['call_outcome_category']}'")
        
        return result
    
    def _validate_and_fix_appointment_enums(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and auto-fix enum values in appointment details."""
        
        VALID_APPOINTMENT_TYPE = {"in-person", "virtual", "phone"}
        VALID_APPOINTMENT_INTENT = {"new", "reschedule", "cancel", "confirm"}
        VALID_TIME_WINDOW = {"morning", "afternoon", "evening", "any"}
        
        # Fix appointment_type
        if "appointment_type" in result and result["appointment_type"]:
            appt_type = result["appointment_type"]
            if appt_type not in VALID_APPOINTMENT_TYPE:
                # Map common variations
                mapping = {
                    "site_visit": "in-person",
                    "in_person": "in-person",
                    "inperson": "in-person",
                    "on-site": "in-person",
                    "physical": "in-person",
                    "phone_call": "phone",
                    "call": "phone",
                    "telephone": "phone",
                    "video": "virtual",
                    "video_call": "virtual",
                    "zoom": "virtual",
                    "online": "virtual",
                }
                
                if appt_type in mapping:
                    result["appointment_type"] = mapping[appt_type]
                    logger.warning(f"Auto-fixed appointment_type: '{appt_type}' → '{result['appointment_type']}'")
                else:
                    result["appointment_type"] = "in-person"  # Default
                    logger.warning(f"Auto-fixed appointment_type: '{appt_type}' → 'in-person' (default)")
        
        # Fix appointment_intent
        if "appointment_intent" in result and result["appointment_intent"]:
            intent = result["appointment_intent"]
            if intent not in VALID_APPOINTMENT_INTENT:
                mapping = {
                    "schedule": "new",
                    "book": "new",
                    "new_appointment": "new",
                    "reschedule_appointment": "reschedule",
                    "change": "reschedule",
                    "move": "reschedule",
                    "cancel_appointment": "cancel",
                    "confirm_appointment": "confirm",
                }
                
                if intent in mapping:
                    result["appointment_intent"] = mapping[intent]
                    logger.warning(f"Auto-fixed appointment_intent: '{intent}' → '{result['appointment_intent']}'")
                else:
                    result["appointment_intent"] = "new"  # Default
                    logger.warning(f"Auto-fixed appointment_intent: '{intent}' → 'new' (default)")
        
        # Fix preferred_time_window
        if "preferred_time_window" in result and result["preferred_time_window"]:
            window = result["preferred_time_window"]
            if isinstance(window, str) and window not in VALID_TIME_WINDOW:
                if "morning" in window.lower() or "am" in window.lower():
                    result["preferred_time_window"] = "morning"
                elif "afternoon" in window.lower() or "pm" in window.lower():
                    result["preferred_time_window"] = "afternoon"
                elif "evening" in window.lower() or "night" in window.lower():
                    result["preferred_time_window"] = "evening"
                else:
                    result["preferred_time_window"] = "any"
                logger.warning(f"Auto-fixed preferred_time_window: '{window}' → '{result['preferred_time_window']}'")
        
        return result
    
    def _flatten_contact_info(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract contact info from nested structure and flatten to top-level.
        
        Handles:
        - contact_information.email → customer_email
        - contact_information.phone → customer_phone
        - Extract from customer_name.email if present
        - Extract from address.email if somehow nested there
        - Validate and enhance addresses with Arizona geography
        """
        contact_info = result.get('contact_information', {})
        
        # Extract email
        if not result.get('customer_email'):
            customer_name_obj = result.get('customer_name')
            email_from_customer_name = None
            if isinstance(customer_name_obj, dict):
                email_from_customer_name = customer_name_obj.get('email')
            
            result['customer_email'] = (
                contact_info.get('email') or
                email_from_customer_name or
                None
            )
            if result['customer_email']:
                logger.info(f"Extracted customer_email from nested structure: {result['customer_email']}")
        
        # Extract phone
        if not result.get('customer_phone'):
            customer_name_obj = result.get('customer_name')
            phone_from_customer_name = None
            if isinstance(customer_name_obj, dict):
                phone_from_customer_name = customer_name_obj.get('phone')
            
            result['customer_phone'] = (
                contact_info.get('phone') or
                phone_from_customer_name or
                None
            )
            if result['customer_phone']:
                logger.info(f"Extracted customer_phone from nested structure: {result['customer_phone']}")
        
        # Extract permissions (bonus)
        if contact_info.get('text_permission') is not None:
            result['text_permission'] = contact_info.get('text_permission')
        if contact_info.get('email_permission') is not None:
            result['email_permission'] = contact_info.get('email_permission')
        if contact_info.get('preferred_contact_method'):
            result['preferred_contact_method'] = contact_info.get('preferred_contact_method')
        
        # Validate and enhance address
        raw_address = result.get('service_address_raw')
        structured_address = result.get('service_address_structured')
        
        if raw_address:
            # Parse and validate the raw address
            parsed = parse_and_validate_address(raw_address)
            if parsed["corrections"]:
                logger.info(f"Address corrections: {parsed['corrections']}")
                result['address_corrections'] = parsed["corrections"]
                result['address_confidence'] = parsed["confidence"]
                
                # Update structured address with corrections
                if structured_address:
                    structured_address.update(parsed["parsed"])
                    result['service_address_structured'] = structured_address
                else:
                    # Create structured address from parsed data
                    result['service_address_structured'] = {
                        **parsed["parsed"],
                        "country": "US"
                    }
        
        elif structured_address:
            # Enhance existing structured address
            enhanced = enhance_address_with_validation(structured_address, raw_address)
            if enhanced.get("_corrections"):
                logger.info(f"Address enhancements: {enhanced['_corrections']}")
                result['address_corrections'] = enhanced["_corrections"]
                result['address_confidence'] = enhanced["_confidence"]
            
            # Remove metadata fields before storing
            enhanced.pop("_corrections", None)
            enhanced.pop("_confidence", None)
            result['service_address_structured'] = enhanced
        
        return result
    
    def _validate_property_details(self, result: Dict[str, Any], transcript: str) -> Dict[str, Any]:
        """
        Validate property details against common errors.
        
        Common issues:
        - "piled roof" → should be "tiled roof"
        - Missing "no solar" statements
        - Partial gate codes
        """
        property_details = result.get('property_details', {})
        if not property_details:
            return result
        
        if not transcript or not isinstance(transcript, str):
            logger.warning("Transcript is None or not a string, skipping property validation")
            return result
        
        transcript_lower = transcript.lower()
        
        # Fix "piled" → "tiled"
        if property_details.get('roof_type') == 'piled':
            if 'tile' in transcript_lower or 'tiled' in transcript_lower:
                property_details['roof_type'] = 'tile'
                logger.info("Corrected 'piled roof' to 'tiled roof'")
        
        # Detect "no solar" mentions
        if property_details.get('has_solar') is None:
            if any(phrase in transcript_lower for phrase in ['no solar', "don't have solar", 'without solar', "doesn't have solar", "does not have solar"]):
                property_details['has_solar'] = False
                logger.info("Detected 'no solar' statement")
        
        # Validate gate codes (should start with # or be all digits)
        gate_access = property_details.get('gate_access')
        if gate_access and len(gate_access) < 3:
            # Partial gate code - flag it
            property_details['gate_access_incomplete'] = True
            logger.warning(f"Detected partial gate code: {gate_access}")
        
        result['property_details'] = property_details
        return result


# Singleton instance
_qualification_extractor: Optional[QualificationExtractor] = None


def get_qualification_extractor() -> QualificationExtractor:
    """Get singleton qualification extractor instance."""
    global _qualification_extractor
    if _qualification_extractor is None:
        _qualification_extractor = QualificationExtractor()
    return _qualification_extractor

