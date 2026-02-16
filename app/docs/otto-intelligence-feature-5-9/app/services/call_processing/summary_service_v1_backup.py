"""
Summary Service

Service for generating call summaries using LLM.
Includes SOP evaluation integration.
"""

from typing import Dict, Any, List, Optional
import json
from openai import AsyncOpenAI
from ...config import get_settings
from ...core.llm import get_max_tokens_param
from .validation_service import get_validation_service
from ...core.database import get_database
from ...services.sop.document_service import DocumentService
from ...services.sop.evaluation_service import EvaluationService

settings = get_settings()

# Initialize GROQ client with OpenAI-compatible API
client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url=settings.GROQ_API_BASE
)


class SummaryService:
    """Service for call summary generation using GROQ"""
    
    def __init__(self):
        self.model = settings.GROQ_MODEL
        self.validation_service = get_validation_service()
        self.evaluation_service = EvaluationService()
        self.max_retries = 3
    
    async def generate_summary(
        self,
        chunks: List[Dict[str, Any]],
        call_id: str,
        company_id: str = "",
        rep_role: Optional[str] = None
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Generate summary using rolling summarization.
        
        Args:
            chunks: List of text chunks
            call_id: Call identifier
            company_id: Company identifier (optional, can be set later)
            rep_role: Representative role for SOP matching
            
        Returns:
            Tuple of (final_summary, chunk_summaries_list)
        """
        if not chunks:
            raise ValueError("No chunks provided")
        
        # Get SOP metrics if available
        sop_metrics = None
        sop_id = None
        sop_name = None
        
        if company_id:
            try:
                db = await get_database()
                doc_service = DocumentService(db)
                sop_metrics_doc = await doc_service.get_sop_metrics(company_id, rep_role)
                
                if sop_metrics_doc:
                    sop_metrics = sop_metrics_doc.get("metrics", [])
                    sop_id = sop_metrics_doc.get("sop_id")
                    
                    # Get SOP name
                    sop_doc = await doc_service.get_sop_document(sop_id)
                    if sop_doc:
                        sop_name = sop_doc.get("sop_name")
                    
                    from ...models.sop import SOPMetric
                    sop_metrics = [SOPMetric(**m) for m in sop_metrics]
            except Exception as e:
                # Log but don't fail if SOP retrieval fails
                import logging
                logging.getLogger(__name__).warning(f"Failed to get SOP metrics: {e}")
        
        previous_summary = None
        chunk_summaries = []  # Store all intermediate summaries
        chunk_evaluations = []  # Store SOP evaluations per chunk
        
        for i, chunk in enumerate(chunks):
            # Generate chunk summary
            chunk_summary = await self._summarize_chunk(
                chunk["text"],
                previous_summary,
                is_first_chunk=(i == 0),
                is_last_chunk=(i == len(chunks) - 1)
            )
            
            # Validate merge quality if not first chunk
            if previous_summary and not await self._validate_merge_quality(chunk_summary, previous_summary, chunk["text"]):
                # Retry with stronger instructions
                import logging
                logging.getLogger(__name__).warning(f"Merge quality check failed for chunk {i}, retrying...")
                chunk_summary = await self._summarize_chunk(
                    chunk["text"],
                    previous_summary,
                    is_first_chunk=False,
                    is_last_chunk=(i == len(chunks) - 1)
                )
            
            # Deduplicate overlapping content
            if previous_summary:
                chunk_summary = self._deduplicate_summary(chunk_summary, previous_summary)
            
            # Store this chunk's summary with metadata
            chunk_summaries.append({
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "summary": chunk_summary
            })
            
            # Evaluate against SOP if available
            if sop_metrics:
                try:
                    chunk_eval = await self.evaluation_service.evaluate_call_against_sop(
                        chunk["text"],
                        sop_metrics,
                        chunk_evaluations if chunk_evaluations else None
                    )
                    chunk_evaluations.append(chunk_eval)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"SOP evaluation failed for chunk {i}: {e}")
            
            # Update previous summary for next iteration
            previous_summary = chunk_summary
        
        # Final summary is the last one (contains merged info from all chunks)
        final_summary = previous_summary
        final_summary["call_id"] = call_id
        final_summary["company_id"] = company_id  # Add company_id before validation
        
        # Merge SOP evaluations if available
        if sop_metrics and chunk_evaluations and sop_id:
            try:
                sop_evaluation = await self.evaluation_service.merge_chunk_evaluations(
                    chunk_evaluations,
                    sop_metrics,
                    sop_id,
                    sop_name or "Unknown SOP"
                )
                
                # Add SOP evaluation to summary
                # Use mode='json' to properly serialize datetime objects
                final_summary["sop_evaluation"] = sop_evaluation.model_dump(mode='json')
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to merge SOP evaluations: {e}")
        
        # Post-process to fix common issues
        final_summary = self._post_process_summary(final_summary)
        
        # Validate
        is_valid, errors = self.validation_service.validate_summary(final_summary)
        if not is_valid:
            # Try to fix common issues
            final_summary = self._attempt_fix(final_summary, errors)
            
            # Re-validate
            is_valid, errors = self.validation_service.validate_summary(final_summary)
            if not is_valid:
                raise ValueError(f"Summary validation failed: {errors}")
        
        return final_summary, chunk_summaries
    
    async def _summarize_chunk(
        self,
        chunk_text: str,
        previous_summary: Optional[Dict[str, Any]],
        is_first_chunk: bool,
        is_last_chunk: bool
    ) -> Dict[str, Any]:
        """Summarize a single chunk with self-reflection and validation"""
        import logging
        logger = logging.getLogger(__name__)
        
        if is_first_chunk:
            prompt = self._build_first_chunk_prompt(chunk_text)
        else:
            prompt = self._build_subsequent_chunk_prompt(chunk_text, previous_summary)
        
        # Call LLM with retries and self-reflection
        for attempt in range(self.max_retries):
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert call analyst. Generate structured JSON summaries of sales calls with perfect adherence to enum values."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                summary_text = response.choices[0].message.content
                
                # Try to parse JSON with error recovery
                try:
                    summary_json = json.loads(summary_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
                    # Try to fix common JSON issues
                    summary_text_fixed = self._repair_json(summary_text)
                    try:
                        summary_json = json.loads(summary_text_fixed)
                        logger.info("Successfully repaired JSON")
                    except:
                        if attempt < self.max_retries - 1:
                            logger.warning(f"JSON repair failed, retrying... (attempt {attempt + 1}/{self.max_retries})")
                            continue
                        raise Exception(f"Failed to parse LLM response as JSON after {self.max_retries} attempts: {str(e)}")
                
                # STEP 4: SELF-REFLECTION + VALIDATION (per architecture)
                # Validate enum values and fix if possible
                summary_json, validation_errors = self._validate_and_fix_enums(summary_json)
                
                if validation_errors:
                    logger.warning(f"Validation errors (attempt {attempt + 1}): {validation_errors}")
                    
                    if attempt < self.max_retries - 1:
                        # Retry with specific feedback about the errors
                        logger.info(f"Retrying with validation feedback... (attempt {attempt + 1}/{self.max_retries})")
                        
                        # Add validation feedback to prompt for next attempt
                        prompt = self._add_validation_feedback(prompt, validation_errors)
                        continue
                    else:
                        # Last attempt - use fixed version if critical errors remain
                        if any("CRITICAL" in err for err in validation_errors):
                            raise ValueError(f"Critical validation errors after {self.max_retries} attempts: {validation_errors}")
                        else:
                            logger.warning(f"Using auto-fixed summary after {self.max_retries} attempts. Errors: {validation_errors}")
                
                # SELF-REFLECTION: Ask LLM to verify its own output
                if is_last_chunk:
                    reflection_result = await self._self_reflection_check(summary_json, chunk_text)
                    if not reflection_result["complete"]:
                        logger.warning(f"Self-reflection check failed: {reflection_result['issues']}")
                        if attempt < self.max_retries - 1:
                            # Retry with self-reflection feedback
                            prompt = f"{prompt}\n\n**FEEDBACK FROM PREVIOUS ATTEMPT:**\n{reflection_result['issues']}\n\nPlease fix these issues and try again."
                            continue
                
                return summary_json
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"LLM call failed (attempt {attempt + 1}): {str(e)}")
                    continue
                raise Exception(f"LLM call failed after {self.max_retries} attempts: {str(e)}")
    
    def _build_first_chunk_prompt(self, chunk_text: str) -> str:
        """Build prompt for first chunk"""
        return f"""Analyze this call transcript and generate a structured JSON summary.

TRANSCRIPT:
{chunk_text}

Generate JSON with these sections:

1. summary: {{
   "summary": "Brief paragraph summarizing the call",
   "key_points": ["list", "of", "key", "points"],
   "action_items": ["list", "of", "action", "items"],
   "next_steps": ["list", "of", "next", "steps"],
   "pending_actions": [
     {{
       "type": "MUST USE ONE OF THESE EXACT VALUES ONLY",
       "owner": "who_does_it",
       "raw_text": "original text",
       "confidence": 0.9,
       "contact_method": "phone"
     }}
   ],
   "sentiment_score": 0.7,
   "confidence_score": 0.8
}}

**VALID ACTION TYPES (use EXACTLY as shown, no variations):**
- call_back
- follow_up_call
- check_in
- send_quote
- send_estimate
- send_contract
- send_info
- send_photos
- send_details
- schedule_appointment
- schedule_visit
- reschedule
- confirm_appointment
- site_visit
- inspection
- measurement
- verify_insurance
- verify_details
- check_availability
- confirm_address
- prepare_contract
- collect_documents
- send_invoice
- escalate
- manager_review

**CRITICAL:** Do NOT use "send_email", "send_confirmation_email", "email_customer", or any other variations. 
If action is to send information via email, use "send_info".
If confirming appointment, use "confirm_appointment".

2. compliance: {{
   "target_role": "customer_rep",
   "evaluation_mode": "sop_only",
   "sop_compliance": {{
     "score": 0.9,
     "compliance_rate": 0.9,
     "stages": {{"total": 2, "followed": ["Intake", "Qualify"], "missed": []}},
     "issues": [],
     "positive_behaviors": ["list of good things"],
     "confidence": 0.8
   }},
   "timestamps": {{}}
}}

3. objections: {{
   "objections": [
     {{
       "category_id": 2,
       "category_text": "Timing",
       "objection_text": "actual objection",
       "overcome": false,
       "speaker_id": "home_owner",
       "confidence_score": 0.9,
       "severity": "medium",
       "response_suggestions": []
     }}
   ],
   "total_count": 1
}}

**VALID SPEAKER_ID VALUES:** home_owner, customer_rep, manager, unknown
**VALID SEVERITY VALUES:** low, medium, high, critical

4. qualification: {{
   "bant_scores": {{
     "need": 1.0,
     "budget": 0.0,
     "timeline": 0.9,
     "authority": 1.0
   }},
   "overall_score": 0.75,
   "qualification_status": "warm",
   "booking_status": "not_booked",
   "call_outcome_category": "qualified_but_unbooked",
   "appointment_confirmed": false,
   "appointment_date": null,
   "appointment_type": null,
   "service_requested": "service name",
   "customer_name": "customer name",
   "customer_name_confidence": 0.9
}}

**ENUM VALUES (use EXACTLY as shown):**

Objection categories (1-10):
1=Price/Budget, 2=Timing, 3=Competitor, 4=Trust/Credibility, 5=Need/Fit, 
6=Decision Authority, 7=Technical, 8=Contract Terms, 9=DIY Alternative, 10=No Response

Qualification status (EXACT VALUES): hot, warm, cold, unqualified
Booking status (EXACT VALUES): booked, not_booked, service_not_offered
Appointment type (EXACT VALUES - if appointment is booked): in-person, virtual, phone

**VALIDATION RULES:**
- All scores must be 0.0 to 1.0
- category_id must be 1-10 (integer)
- Use ONLY the exact enum values listed above
- NO custom enum values allowed

Output ONLY valid JSON. Double-check all enum values before responding."""
    
    def _build_subsequent_chunk_prompt(
        self,
        chunk_text: str,
        previous_summary: Dict[str, Any]
    ) -> str:
        """Build prompt for subsequent chunks with explicit merge instructions"""
        return f"""You previously summarized the first part of this call.

PREVIOUS SUMMARY:
{json.dumps(previous_summary, indent=2)}

Now analyze the next part and UPDATE the summary using these STRICT RULES:

**CRITICAL: ARRAY HANDLING**
1. **APPEND** to all arrays, NEVER replace them:
   - key_points: Add NEW points only, keep ALL previous points
   - action_items: Add NEW items only, keep ALL previous items
   - objections.objections: Add NEW objections only, keep ALL previous objections
   - pending_actions: Add NEW actions only, keep ALL previous actions
   - compliance.sop_compliance.stages.followed: Add NEW stages, keep ALL previous
   - compliance.sop_compliance.positive_behaviors: Add NEW behaviors, keep ALL previous

2. **UPDATE scores** only when new chunk provides better information:
   - sentiment_score: Compute weighted average (previous chunks + this chunk)
   - BANT scores: Update only if new explicit information found
   - qualification_status: Update only if status clearly changes
   - confidence_score: Weighted average

3. **MERGE text fields** (do NOT condense):
   - summary: Append new information to existing summary paragraph
   - Do NOT summarize or lose details from previous summary
   - Maintain chronological flow

4. **PRESERVE everything**:
   - All timestamps, IDs, metadata from previous summary
   - All previous details MUST remain in the output
   - call_id, company_id, target_role must stay unchanged

NEXT TRANSCRIPT PART:
{chunk_text}

**VERIFICATION CHECKLIST before outputting:**
- [ ] All previous objections are in the output
- [ ] All previous key_points are in the output  
- [ ] All previous action_items are in the output
- [ ] Summary paragraph includes previous + new information
- [ ] No information from previous summary was lost

Output the COMPLETE updated JSON with ALL previous information PLUS new findings."""
    
    def _post_process_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process summary to fix common issues.
        
        Args:
            summary: Raw summary from LLM
            
        Returns:
            Cleaned up summary
        """
        from datetime import datetime
        
        # Fix next_steps if it contains "None" or similar
        if "summary" in summary and "next_steps" in summary["summary"]:
            next_steps = summary["summary"]["next_steps"]
            if isinstance(next_steps, list):
                # Remove "None", "N/A", empty strings
                cleaned = [
                    step for step in next_steps 
                    if step and step.lower() not in ["none", "n/a", "null", ""]
                ]
                summary["summary"]["next_steps"] = cleaned
        
        # Add timestamps to compliance if missing
        if "compliance" in summary:
            # Add call_id if missing
            if "call_id" not in summary["compliance"]:
                summary["compliance"]["call_id"] = summary.get("call_id", "")
            
            if "timestamps" not in summary["compliance"]:
                summary["compliance"]["timestamps"] = {}
            
            if not summary["compliance"]["timestamps"]:
                summary["compliance"]["timestamps"] = {
                    "sop_evaluated_at": datetime.utcnow().isoformat()
                }
        
        # Fix speaker_id enum values in objections
        if "objections" in summary and "objections" in summary["objections"]:
            for objection in summary["objections"]["objections"]:
                if "speaker_id" in objection:
                    speaker = objection["speaker_id"].lower()
                    # Map common values to enum
                    if "customer" in speaker or "home" in speaker or "owner" in speaker:
                        objection["speaker_id"] = "home_owner"
                    elif "rep" in speaker or "sales" in speaker:
                        objection["speaker_id"] = "customer_rep"
                    elif "manager" in speaker:
                        objection["speaker_id"] = "manager"
                    else:
                        objection["speaker_id"] = "unknown"
        
        return summary

    
    async def _validate_merge_quality(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any],
        chunk_text: str
    ) -> bool:
        """
        Validate that merge didn't lose information from previous summary.
        
        Returns True if merge quality is acceptable, False to retry.
        """
        try:
            # Check 1: Array lengths should not decrease
            if "objections" in current and "objections" in previous:
                curr_obj_count = len(current.get("objections", {}).get("objections", []))
                prev_obj_count = len(previous.get("objections", {}).get("objections", []))
                if curr_obj_count < prev_obj_count:
                    return False
            
            if "summary" in current and "summary" in previous:
                # Check key_points
                curr_kp_count = len(current.get("summary", {}).get("key_points", []))
                prev_kp_count = len(previous.get("summary", {}).get("key_points", []))
                if curr_kp_count < prev_kp_count:
                    return False
                
                # Check action_items
                curr_ai_count = len(current.get("summary", {}).get("action_items", []))
                prev_ai_count = len(previous.get("summary", {}).get("action_items", []))
                if curr_ai_count < prev_ai_count:
                    return False
            
            # Check 2: Sentiment score shouldn't change drastically
            if "summary" in current and "summary" in previous:
                curr_sentiment = current.get("summary", {}).get("sentiment_score", 0.5)
                prev_sentiment = previous.get("summary", {}).get("sentiment_score", 0.5)
                if abs(curr_sentiment - prev_sentiment) > 0.4:
                    # Large sentiment shift suspicious - might indicate info loss
                    return False
            
            # All checks passed
            return True
            
        except Exception as e:
            # If validation itself fails, allow the merge
            import logging
            logging.getLogger(__name__).warning(f"Merge validation error: {e}")
            return True
    
    def _deduplicate_summary(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Remove duplicate entries that may have been extracted from chunk overlap.
        
        Uses fuzzy text matching to identify duplicates.
        """
        try:
            # Deduplicate objections
            if "objections" in current and "objections" in previous:
                prev_objections = previous.get("objections", {}).get("objections", [])
                curr_objections = current.get("objections", {}).get("objections", [])
                
                # Create set of previous objection texts (lowercased for comparison)
                prev_texts = {obj.get("objection_text", "").lower() for obj in prev_objections}
                
                # Filter out duplicates from current
                unique_curr_objections = []
                for obj in curr_objections:
                    obj_text = obj.get("objection_text", "").lower()
                    # Check for exact match or very similar (>80% overlap)
                    is_duplicate = False
                    for prev_text in prev_texts:
                        if obj_text == prev_text or self._text_similarity(obj_text, prev_text) > 0.8:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_curr_objections.append(obj)
                
                # Update current with deduplicated objections (preserving previous ones)
                if "objections" not in current:
                    current["objections"] = {}
                current["objections"]["objections"] = unique_curr_objections
            
            # Deduplicate key_points
            if "summary" in current and "summary" in previous:
                prev_kps = previous.get("summary", {}).get("key_points", [])
                curr_kps = current.get("summary", {}).get("key_points", [])
                
                prev_kps_lower = {kp.lower() for kp in prev_kps}
                unique_curr_kps = []
                for kp in curr_kps:
                    is_duplicate = False
                    kp_lower = kp.lower()
                    for prev_kp in prev_kps_lower:
                        if kp_lower == prev_kp or self._text_similarity(kp_lower, prev_kp) > 0.85:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_curr_kps.append(kp)
                
                current["summary"]["key_points"] = unique_curr_kps
            
            # Deduplicate action_items
            if "summary" in current and "summary" in previous:
                prev_ais = previous.get("summary", {}).get("action_items", [])
                curr_ais = current.get("summary", {}).get("action_items", [])
                
                prev_ais_lower = {ai.lower() for ai in prev_ais}
                unique_curr_ais = []
                for ai in curr_ais:
                    is_duplicate = False
                    ai_lower = ai.lower()
                    for prev_ai in prev_ais_lower:
                        if ai_lower == prev_ai or self._text_similarity(ai_lower, prev_ai) > 0.85:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_curr_ais.append(ai)
                
                current["summary"]["action_items"] = unique_curr_ais
            
            return current
            
        except Exception as e:
            # If deduplication fails, return current as-is
            import logging
            logging.getLogger(__name__).warning(f"Deduplication error: {e}")
            return current
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate simple text similarity ratio (0.0 to 1.0).
        Uses character-level matching.
        """
        if not text1 or not text2:
            return 0.0
        
        # Simple approach: count matching words
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _repair_json(self, json_str: str) -> str:
        """
        Attempt to repair common JSON errors.
        """
        import re
        
        # Fix trailing commas before closing brackets/braces
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # Fix missing commas between array elements (heuristic)
        json_str = re.sub(r'"\s*\n\s*"', '",\n"', json_str)
        
        # Fix unescaped quotes in strings (basic attempt)
        # This is tricky and might not catch all cases
        
        return json_str
    
    def _validate_and_fix_enums(self, summary: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
        """
        Validate enum values and attempt to fix them.
        Returns (fixed_summary, list_of_errors).
        """
        errors = []
        
        # Valid enum mappings
        ACTION_TYPE_MAPPING = {
            "send_confirmation_email": "send_info",
            "send_email": "send_info",
            "email_customer": "send_info",
            "call_customer": "call_back",
            "callback": "call_back",
            "follow_up": "follow_up_call",
            "schedule": "schedule_appointment",
            "book_appointment": "schedule_appointment",
            "send_proposal": "send_quote",
            "send_pricing": "send_quote",
        }
        
        VALID_ACTION_TYPES = {
            "call_back", "follow_up_call", "check_in",
            "send_quote", "send_estimate", "send_contract", "send_info", "send_photos", "send_details",
            "schedule_appointment", "schedule_visit", "reschedule", "confirm_appointment",
            "site_visit", "inspection", "measurement",
            "verify_insurance", "verify_details", "check_availability", "confirm_address",
            "prepare_contract", "collect_documents", "send_invoice",
            "escalate", "manager_review"
        }
        
        VALID_QUALIFICATION_STATUS = {"hot", "warm", "cold", "unqualified"}
        VALID_BOOKING_STATUS = {"booked", "not_booked", "service_not_offered"}
        VALID_APPOINTMENT_TYPE = {"in-person", "virtual", "phone"}
        VALID_SEVERITY = {"low", "medium", "high", "critical"}
        VALID_SPEAKER_ID = {"home_owner", "customer_rep", "manager", "unknown"}
        
        # Appointment type mappings
        APPOINTMENT_TYPE_MAPPING = {
            "site_visit": "in-person",
            "in_person": "in-person",
            "inperson": "in-person",
            "phone_call": "phone",
            "phone_consultation": "phone",
            "call": "phone",
            "video": "virtual",
            "video_call": "virtual",
            "zoom": "virtual",
            "online": "virtual",
            "virtual_meeting": "virtual",
        }
        
        # Fix action types
        if "summary" in summary and "pending_actions" in summary["summary"]:
            for i, action in enumerate(summary["summary"]["pending_actions"]):
                if "type" in action:
                    action_type = action["type"]
                    
                    # Check if it needs mapping
                    if action_type not in VALID_ACTION_TYPES:
                        # Try to map it
                        if action_type in ACTION_TYPE_MAPPING:
                            action["type"] = ACTION_TYPE_MAPPING[action_type]
                            errors.append(f"WARNING: Mapped action type '{action_type}' to '{action['type']}' at index {i}")
                        else:
                            # Try fuzzy matching
                            best_match = self._find_closest_enum(action_type, VALID_ACTION_TYPES)
                            if best_match:
                                action["type"] = best_match
                                errors.append(f"WARNING: Fuzzy-matched action type '{action_type}' to '{best_match}' at index {i}")
                            else:
                                # Default to send_info
                                action["type"] = "send_info"
                                errors.append(f"CRITICAL: Invalid action type '{action_type}' at index {i}, defaulted to 'send_info'")
        
        # Fix qualification status
        if "qualification" in summary:
            qual_status = summary["qualification"].get("qualification_status")
            if qual_status and qual_status not in VALID_QUALIFICATION_STATUS:
                best_match = self._find_closest_enum(qual_status, VALID_QUALIFICATION_STATUS)
                if best_match:
                    summary["qualification"]["qualification_status"] = best_match
                    errors.append(f"WARNING: Fixed qualification_status from '{qual_status}' to '{best_match}'")
                else:
                    summary["qualification"]["qualification_status"] = "cold"
                    errors.append(f"CRITICAL: Invalid qualification_status '{qual_status}', defaulted to 'cold'")
            
            booking_status = summary["qualification"].get("booking_status")
            if booking_status and booking_status not in VALID_BOOKING_STATUS:
                best_match = self._find_closest_enum(booking_status, VALID_BOOKING_STATUS)
                if best_match:
                    summary["qualification"]["booking_status"] = best_match
                    errors.append(f"WARNING: Fixed booking_status from '{booking_status}' to '{best_match}'")
                else:
                    summary["qualification"]["booking_status"] = "not_booked"
                    errors.append(f"CRITICAL: Invalid booking_status '{booking_status}', defaulted to 'not_booked'")
            
            # Fix appointment_type
            appointment_type = summary["qualification"].get("appointment_type")
            if appointment_type and appointment_type not in VALID_APPOINTMENT_TYPE:
                # Try mapping first
                if appointment_type in APPOINTMENT_TYPE_MAPPING:
                    summary["qualification"]["appointment_type"] = APPOINTMENT_TYPE_MAPPING[appointment_type]
                    errors.append(f"WARNING: Mapped appointment_type from '{appointment_type}' to '{summary['qualification']['appointment_type']}'")
                else:
                    # Try fuzzy matching
                    best_match = self._find_closest_enum(appointment_type, VALID_APPOINTMENT_TYPE)
                    if best_match:
                        summary["qualification"]["appointment_type"] = best_match
                        errors.append(f"WARNING: Fuzzy-matched appointment_type from '{appointment_type}' to '{best_match}'")
                    else:
                        # Default to in-person for physical visits, phone for calls
                        if "visit" in appointment_type.lower() or "site" in appointment_type.lower():
                            summary["qualification"]["appointment_type"] = "in-person"
                        elif "phone" in appointment_type.lower() or "call" in appointment_type.lower():
                            summary["qualification"]["appointment_type"] = "phone"
                        else:
                            summary["qualification"]["appointment_type"] = "in-person"
                        errors.append(f"CRITICAL: Invalid appointment_type '{appointment_type}', defaulted to '{summary['qualification']['appointment_type']}'")

        
        # Fix objection severity and speaker_id
        if "objections" in summary and "objections" in summary["objections"]:
            for i, obj in enumerate(summary["objections"]["objections"]):
                if "severity" in obj and obj["severity"] not in VALID_SEVERITY:
                    best_match = self._find_closest_enum(obj["severity"], VALID_SEVERITY)
                    if best_match:
                        obj["severity"] = best_match
                        errors.append(f"WARNING: Fixed objection severity at index {i}")
                    else:
                        obj["severity"] = "medium"
                        errors.append(f"CRITICAL: Invalid objection severity at index {i}")
                
                if "speaker_id" in obj and obj["speaker_id"] not in VALID_SPEAKER_ID:
                    best_match = self._find_closest_enum(obj["speaker_id"], VALID_SPEAKER_ID)
                    if best_match:
                        obj["speaker_id"] = best_match
                        errors.append(f"WARNING: Fixed speaker_id at index {i}")
                    else:
                        obj["speaker_id"] = "unknown"
                        errors.append(f"CRITICAL: Invalid speaker_id at index {i}")
                
                # Validate category_id is 1-10
                if "category_id" in obj:
                    cat_id = obj["category_id"]
                    if not isinstance(cat_id, int) or cat_id < 1 or cat_id > 10:
                        obj["category_id"] = 10  # Default to "No Response"
                        errors.append(f"CRITICAL: Invalid category_id {cat_id} at index {i}, defaulted to 10")
        
        return summary, errors
    
    def _find_closest_enum(self, value: str, valid_values: set) -> Optional[str]:
        """
        Find the closest matching enum value using fuzzy matching.
        """
        if not value:
            return None
        
        value_lower = value.lower().replace("_", "").replace("-", "")
        best_match = None
        best_score = 0.0
        
        for valid in valid_values:
            valid_lower = valid.lower().replace("_", "").replace("-", "")
            
            # Check for substring match
            if value_lower in valid_lower or valid_lower in value_lower:
                score = 0.9
            else:
                # Calculate similarity
                score = self._text_similarity(value_lower, valid_lower)
            
            if score > best_score and score > 0.6:  # Threshold for accepting match
                best_score = score
                best_match = valid
        
        return best_match
    
    def _add_validation_feedback(self, original_prompt: str, errors: List[str]) -> str:
        """
        Add validation error feedback to the prompt for retry.
        """
        feedback = "\n\n**VALIDATION ERRORS FROM PREVIOUS ATTEMPT:**\n"
        feedback += "\n".join(f"- {err}" for err in errors)
        feedback += "\n\n**Please correct these errors and ensure all enum values are EXACTLY as specified.**"
        
        return original_prompt + feedback
    
    async def _self_reflection_check(self, summary: Dict[str, Any], chunk_text: str) -> Dict[str, Any]:
        """
        STEP 4: Self-reflection - Ask LLM to verify its own output.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            reflection_prompt = f"""Review this call summary for completeness and accuracy:

SUMMARY JSON:
{json.dumps(summary, indent=2)}

ORIGINAL TRANSCRIPT SNIPPET (last 500 chars):
{chunk_text[-500:]}

Answer these questions:
1. Are all customer objections captured in the objections array?
2. Are all action items and next steps clearly identified?
3. Is the qualification status (hot/warm/cold) appropriate?
4. Is the booking status correct?
5. Are BANT scores reasonable based on the conversation?

Respond in JSON:
{{
  "complete": true/false,
  "issues": ["list any issues found", "or empty if complete"],
  "confidence": 0.0-1.0
}}

Output ONLY JSON."""
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a quality assurance analyst reviewing call summaries for completeness."
                    },
                    {
                        "role": "user",
                        "content": reflection_prompt
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                **get_max_tokens_param(500)
            )
            
            reflection = json.loads(response.choices[0].message.content)
            return reflection
            
        except Exception as e:
            logger.warning(f"Self-reflection check failed: {e}")
            # If self-reflection fails, assume summary is okay
            return {"complete": True, "issues": [], "confidence": 0.7}

    
    def _attempt_fix(
        self,
        summary: Dict[str, Any],
        errors: List[str]
    ) -> Dict[str, Any]:
        """Attempt to fix common validation errors"""
        fixed = summary.copy()
        
        # Ensure required top-level fields exist
        if "summary" not in fixed:
            fixed["summary"] = {}
        if "compliance" not in fixed:
            fixed["compliance"] = {"sop_compliance": {}}
        if "objections" not in fixed:
            fixed["objections"] = {"objections": [], "total_count": 0}
        if "qualification" not in fixed:
            fixed["qualification"] = {}
        
        # Fix summary section
        summary_section = fixed.get("summary", {})
        summary_section.setdefault("summary", "")
        summary_section.setdefault("key_points", [])
        summary_section.setdefault("action_items", [])
        summary_section.setdefault("sentiment_score", 0.5)
        summary_section.setdefault("confidence_score", 0.5)
        fixed["summary"] = summary_section
        
        # Fix qualification section
        qual = fixed.get("qualification", {})
        qual.setdefault("qualification_status", "cold")
        qual.setdefault("booking_status", "not_booked")
        qual.setdefault("overall_score", 0.5)
        qual.setdefault("bant_scores", {
            "need": 0.5,
            "budget": 0.0,
            "timeline": 0.5,
            "authority": 0.5
        })
        fixed["qualification"] = qual
        
        return fixed


# Singleton instance
_summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """Get singleton summary service instance"""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummaryService()
    return _summary_service

