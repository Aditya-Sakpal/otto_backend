"""
Summary Service - V2 with Parallel Extraction

NEW ARCHITECTURE:
- Uses 4 specialized extractors running in parallel
- Better quality through focused prompts
- Individual retry per section
- Customer history context integration
- Call date context for relative date resolution
"""

from typing import Dict, Any, List, Optional
import json
import asyncio
from datetime import datetime
import logging

from .validation_service import get_validation_service
from ...core.database import get_database
from ...services.sop.document_service import DocumentService
from ...services.sop.evaluation_service import EvaluationService
from .customer_history_service import get_customer_history_service
from .extractors import (
    SummaryExtractor,
    ComplianceExtractor,
    ObjectionExtractor,
    QualificationExtractor,
)

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for call summary generation using parallel specialized extractors."""
    
    def __init__(self):
        self.validation_service = get_validation_service()
        self.evaluation_service = EvaluationService()
        self.customer_history_service = get_customer_history_service()
        self.max_retries = 3
        
        # Initialize extractors
        self.summary_extractor = SummaryExtractor()
        self.compliance_extractor = ComplianceExtractor()
        self.objection_extractor = ObjectionExtractor()
        self.qualification_extractor = QualificationExtractor()
    
    async def generate_summary(
        self,
        chunks: List[Dict[str, Any]],
        call_id: str,
        company_id: str = "",
        rep_role: Optional[str] = None,
        call_context: Optional[Dict[str, Any]] = None
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Generate summary using parallel extraction and rolling summarization.
        
        Args:
            chunks: List of text chunks
            call_id: Call identifier
            company_id: Company identifier
            rep_role: Representative role for SOP matching
            call_context: Context about the call (date, time, timezone, etc.)
        
        Returns:
            Tuple of (final_summary, chunk_summaries_list)
        """
        if not chunks:
            raise ValueError("No chunks provided")
        
        # Build call context
        if not call_context:
            call_context = {}
        
        call_context.setdefault("call_id", call_id)
        call_context.setdefault("company_id", company_id)
        call_context.setdefault("rep_role", rep_role or "customer_rep")
        call_context.setdefault("timezone", "UTC")
        
        # Get customer history if phone number available
        customer_history = None
        phone_number = call_context.get("phone_number")
        if phone_number and company_id:
            customer_history = await self.customer_history_service.get_customer_context(
                phone_number=phone_number,
                company_id=company_id
            )
            if customer_history:
                logger.info(f"Retrieved customer history: {customer_history['previous_call_count']} previous calls")
        
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
                logger.warning(f"Failed to get SOP metrics: {e}")
        
        # Process chunks with rolling summarization
        previous_sections = {
            "summary": None,
            "compliance": None,
            "objections": None,
            "qualification": None
        }
        
        chunk_summaries = []
        chunk_evaluations = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} (call: {call_id})")
            
            # Extract all sections in parallel
            chunk_summary = await self._extract_chunk_parallel(
                chunk["text"],
                call_context,
                customer_history,
                previous_sections,
                is_first_chunk=(i == 0),
                is_last_chunk=(i == len(chunks) - 1)
            )
            
            # Store chunk summary
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
                    logger.warning(f"SOP evaluation failed for chunk {i}: {e}")
            
            # Update previous sections for next iteration
            previous_sections = {
                "summary": chunk_summary.get("summary"),
                "compliance": chunk_summary.get("compliance"),
                "objections": chunk_summary.get("objections"),
                "qualification": chunk_summary.get("qualification")
            }
        
        # Final summary is the last one
        final_summary = chunk_summaries[-1]["summary"]
        final_summary["call_id"] = call_id
        final_summary["company_id"] = company_id
        
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
                final_summary["sop_evaluation"] = sop_evaluation.model_dump(mode='json')
            except Exception as e:
                logger.warning(f"Failed to merge SOP evaluations: {e}")
        
        # Post-process
        final_summary = self._post_process_summary(final_summary)
        
        # Validate
        is_valid, errors = self.validation_service.validate_summary(final_summary)
        if not is_valid:
            logger.warning(f"Summary validation errors: {errors}")
            # Apply fixes if needed
            final_summary = self._attempt_fix(final_summary, errors)
            
            # Re-validate
            is_valid, errors = self.validation_service.validate_summary(final_summary)
            if not is_valid:
                # Log but don't fail - some errors may be acceptable
                logger.error(f"Summary still has validation errors: {errors}")
        
        return final_summary, chunk_summaries
    
    async def _extract_chunk_parallel(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        customer_history: Optional[Dict[str, Any]],
        previous_sections: Dict[str, Any],
        is_first_chunk: bool,
        is_last_chunk: bool
    ) -> Dict[str, Any]:
        """
        Extract all sections in parallel using specialized extractors.
        
        This is the core of the new parallel architecture.
        """
        logger.info("Starting parallel extraction of 4 sections...")
        
        # Create extraction tasks
        tasks = {
            "summary": self._extract_with_retry(
                self.summary_extractor.extract,
                chunk_text,
                call_context,
                previous_sections.get("summary")
            ),
            "compliance": self._extract_with_retry(
                self.compliance_extractor.extract,
                chunk_text,
                call_context,
                previous_sections.get("compliance")
            ),
            "objections": self._extract_with_retry(
                self.objection_extractor.extract,
                chunk_text,
                call_context,
                previous_sections.get("objections")
            ),
            "qualification": self._extract_with_retry(
                self.qualification_extractor.extract,
                chunk_text,
                call_context,
                customer_history,
                previous_sections.get("qualification")
            )
        }
        
        # Execute all in parallel
        try:
            results = await asyncio.gather(
                tasks["summary"],
                tasks["compliance"],
                tasks["objections"],
                tasks["qualification"],
                return_exceptions=True
            )
            
            summary_result, compliance_result, objections_result, qualification_result = results
            
            # Check for failures
            if isinstance(summary_result, Exception):
                logger.error(f"Summary extraction failed: {summary_result}")
                summary_result = self._get_default_summary()
            
            if isinstance(compliance_result, Exception):
                logger.error(f"Compliance extraction failed: {compliance_result}")
                compliance_result = self._get_default_compliance()
            
            if isinstance(objections_result, Exception):
                logger.error(f"Objections extraction failed: {objections_result}")
                objections_result = self._get_default_objections()
            
            if isinstance(qualification_result, Exception):
                logger.error(f"Qualification extraction failed: {qualification_result}")
                qualification_result = self._get_default_qualification()
            
            # Merge into final structure
            merged = {
                "summary": summary_result,
                "compliance": compliance_result,
                "objections": objections_result,
                "qualification": qualification_result
            }
            
            # Self-reflection on last chunk
            if is_last_chunk:
                reflection = await self._self_reflection_check(merged, chunk_text)
                if not reflection.get("complete", True):
                    logger.warning(f"Self-reflection identified issues: {reflection.get('issues')}")
                    # Could trigger retry here if needed
            
            logger.info("Parallel extraction completed successfully")
            return merged
            
        except Exception as e:
            logger.error(f"Parallel extraction failed: {e}")
            raise
    
    async def _extract_with_retry(
        self,
        extract_func,
        chunk_text: str,
        call_context: Dict[str, Any],
        *args
    ):
        """
        Wrap extraction with retry logic.
        
        Args:
            extract_func: The extraction function to call
            chunk_text: Transcript text
            call_context: Call context
            *args: Additional arguments (previous_summary, customer_history, etc.)
        """
        for attempt in range(self.max_retries):
            try:
                result = await extract_func(chunk_text, call_context, *args)
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error in extraction (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)  # Brief delay before retry
                    continue
                raise
            except Exception as e:
                logger.error(f"Extraction failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
        
        raise Exception(f"Extraction failed after {self.max_retries} attempts")
    
    async def _self_reflection_check(
        self,
        merged_summary: Dict[str, Any],
        chunk_text: str
    ) -> Dict[str, Any]:
        """
        Single self-reflection on the merged output from all extractors.
        
        This checks for:
        - Completeness across all sections
        - Internal consistency
        - Missing critical information
        """
        try:
            from ...core.llm import get_llm_client, get_active_model, get_max_tokens_param
            from ...config import get_settings
            
            settings = get_settings()
            client = get_llm_client()
            
            reflection_prompt = f"""Review this complete call summary for quality and completeness:

**MERGED SUMMARY:**
{json.dumps(merged_summary, indent=2)}

**ORIGINAL TRANSCRIPT (last 500 chars):**
{chunk_text[-500:]}

Check these aspects:

1. **Summary Section:**
   - Is the narrative summary comprehensive?
   - Are all key points captured?
   - Are action items clearly defined?

2. **Compliance Section:**
   - Are positive behaviors noted?
   - Are issues properly identified?

3. **Objections Section:**
   - Are all customer concerns captured?
   - Is severity assessment appropriate?

4. **Qualification Section:**
   - Are BANT scores reasonable?
   - Is booking status correct?
   - Is address extracted (if mentioned)?
   - Is appointment info complete?

5. **Cross-Section Consistency:**
   - Do qualification status and objections align?
   - Does sentiment match objections?
   - Is follow-up logic sound?

Respond in JSON:
{{
  "complete": true/false,
  "confidence": 0.0-1.0,
  "issues": ["list any problems found", "or empty if complete"]
}}

Output ONLY JSON:"""
            
            response = await client.chat.completions.create(
                model=get_active_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a quality assurance analyst reviewing call summaries."
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
            return {"complete": True, "confidence": 0.7, "issues": []}
    
    def _post_process_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process to add timestamps and clean up data."""
        
        from datetime import datetime
        
        # Add timestamps to compliance if missing
        if "compliance" in summary:
            if "call_id" not in summary["compliance"]:
                summary["compliance"]["call_id"] = summary.get("call_id", "")
            
            if "timestamps" not in summary["compliance"]:
                summary["compliance"]["timestamps"] = {}
            
            if not summary["compliance"]["timestamps"]:
                summary["compliance"]["timestamps"] = {
                    "sop_evaluated_at": datetime.utcnow().isoformat()
                }
        
        # Ensure objections have total_count
        if "objections" in summary:
            objections_list = summary["objections"].get("objections", [])
            summary["objections"]["total_count"] = len(objections_list)
        
        return summary
    
    def _attempt_fix(
        self,
        summary: Dict[str, Any],
        errors: List[str]
    ) -> Dict[str, Any]:
        """Attempt to fix validation errors with defaults."""
        
        fixed = summary.copy()
        
        # Ensure required top-level fields exist
        if "summary" not in fixed:
            fixed["summary"] = self._get_default_summary()
        if "compliance" not in fixed:
            fixed["compliance"] = self._get_default_compliance()
        if "objections" not in fixed:
            fixed["objections"] = self._get_default_objections()
        if "qualification" not in fixed:
            fixed["qualification"] = self._get_default_qualification()
        
        return fixed
    
    def _get_default_summary(self) -> Dict[str, Any]:
        """Get default summary section."""
        return {
            "summary": "Call summary unavailable",
            "key_points": [],
            "action_items": [],
            "next_steps": [],
            "pending_actions": [],
            "sentiment_score": 0.5,
            "confidence_score": 0.3
        }
    
    def _get_default_compliance(self) -> Dict[str, Any]:
        """Get default compliance section."""
        return {
            "target_role": "customer_rep",
            "evaluation_mode": "sop_only",
            "sop_compliance": {
                "score": 0.5,
                "compliance_rate": 0.5,
                "stages": {"total": 0, "followed": [], "missed": []},
                "issues": ["Extraction failed"],
                "positive_behaviors": [],
                "confidence": 0.3
            },
            "timestamps": {}
        }
    
    def _get_default_objections(self) -> Dict[str, Any]:
        """Get default objections section."""
        return {
            "objections": [],
            "total_count": 0
        }
    
    def _get_default_qualification(self) -> Dict[str, Any]:
        """Get default qualification section."""
        return {
            "bant_scores": {"need": 0.5, "budget": 0.0, "timeline": 0.5, "authority": 0.5},
            "overall_score": 0.375,
            "qualification_status": "cold",
            "booking_status": "not_booked",
            "call_outcome_category": "unknown",
            "appointment_confirmed": False,
            "appointment_date": None,
            "appointment_type": None,
            "appointment_timezone": "UTC",
            "appointment_time_confidence": 0.0,
            "preferred_time_window": None,
            "appointment_intent": None,
            "original_appointment_datetime": None,
            "new_requested_time": None,
            "service_requested": None,
            "service_not_offered_reason": None,
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
            "confidence_score": 0.3,
            "follow_up_required": False,
            "follow_up_reason": None
        }


# Singleton instance
_summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """Get singleton summary service instance."""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummaryService()
    return _summary_service

