"""
Call service.

Orchestrates call-related business logic:
- Call ingestion from webhooks
- Call analysis pipeline
- Transcript processing
"""
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
from dateutil import parser as date_parser

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.analysis import CallAnalysis
from app.domain.models.pending_action import PendingAction
from app.domain.enums import AnalysisStatus, PendingActionStatus
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.tasks.analysis import analyze_call_task
from app.core.s3 import get_s3_service
from app.domain.users.repository import UserRepository
from app.domain.users.models import User
from app.domain.models.lead import Lead
from app.domain.models.appointment import Appointment
from app.domain.enums import LeadStatus, DealStatus, AppointmentOutcome
from app.services.ghost_mode_service import GhostModeService

logger = get_logger(__name__)

# Qualified statuses: hot, cold, warm, and qualified are all considered qualified
QUALIFIED_STATUSES = ['hot', 'cold', 'warm', 'qualified']


def is_qualified_status(qualification_status: Optional[str]) -> bool:
    """
    Check if a qualification_status is considered qualified.
    
    Qualified statuses: 'hot', 'cold', 'warm', 'qualified'
    """
    if not qualification_status:
        return False
    return qualification_status.lower() in [s.lower() for s in QUALIFIED_STATUSES]


def transform_summary_to_analysis_data(summary_json: dict) -> dict:
    """
    Transform summary API JSON (context.spec shape) into the flat analysis_data
    format expected by process_analysis.

    Summary API returns: { summary, compliance, objections, qualification }.
    process_analysis expects: qualification_status, booking_status, objections,
    objection_texts, sop_stages_*, sop_compliance_score, sentiment_score,
    summary, key_points, pending_actions.
    """
    try:
        summary_block = summary_json.get("summary") or {}
        compliance_block = summary_json.get("compliance") or {}
        sop = compliance_block.get("sop_compliance") or {}
        stages = sop.get("stages") or {}
        objections_block = summary_json.get("objections") or {}
        qualification_block = summary_json.get("qualification") or {}

        objections_list = objections_block.get("objections") or []
        objection_texts = []
        if objections_list:
            for o in objections_list:
                if isinstance(o, str):
                    objection_texts.append(o)
                elif isinstance(o, dict) and o.get("text"):
                    objection_texts.append(o["text"])

        return {
            "qualification_status": qualification_block.get("qualification_status"),
            "booking_status": qualification_block.get("booking_status"),
            "objections": objections_list,
            "objection_texts": objection_texts,
            "sop_stages_completed": stages.get("followed") or [],
            "sop_stages_missed": stages.get("missed") or [],
            "sop_compliance_score": sop.get("score") or sop.get("compliance_rate"),
            "sentiment_score": summary_block.get("sentiment_score"),
            "summary": summary_block.get("summary"),
            "key_points": summary_block.get("key_points") or [],
            "pending_actions": summary_block.get("pending_actions") or [],
        }
    except Exception as e:
        logger.error(f"Error transforming summary to analysis data: {e}")
        raise e


class CallService:
    """Service for call-related operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
        self.analysis_repo = CallAnalysisRepository(session)
        self.pending_action_repo = PendingActionRepository(session)
        self.contact_repo = ContactRepository(session)
        self.lead_repo = LeadRepository(session)
        self.appointment_repo = AppointmentRepository(session)
        self.user_repo = UserRepository(session)
        self.shoonya = get_shoonya_client()

    async def ingest_call(
        self,
        company_id: UUID,
        phone_number: str,
        audio_url: Optional[str] = None,
        call_type: Optional[str] = None,
        missed_call: bool = False,
    ) -> Call:
        """
        Ingest a new call from webhook.

        Args:
            company_id: Company/tenant ID
            phone_number: Caller phone number
            audio_url: Optional audio recording URL
            call_type: Type of call
            missed_call: Whether call was missed

        Returns:
            Created call
        """
        try:
            # Find or create contact card for this phone number
            contact_card = None
            try:
                contact_card = await self.contact_repo.find_or_create_by_phone(
                    company_id=company_id,
                    phone=phone_number,
                )
                logger.debug(
                    "Found or created contact card",
                    contact_card_id=str(contact_card.id),
                    phone_number=phone_number,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to find or create contact card for phone {phone_number}: {e}",
                    company_id=str(company_id),
                )
                # Continue without contact_card_id - call will still be created

            # Create call record
            call = Call(
                company_id=company_id,
                contact_card_id=contact_card.id if contact_card else None,
                phone_number=phone_number,
                audio_url=audio_url,
                call_type=call_type,
                missed_call=missed_call,
            )

            call = await self.call_repo.create(call)
            logger.info(
                "Call ingested",
                call_id=str(call.id),
                company_id=str(company_id),
                contact_card_id=str(call.contact_card_id) if call.contact_card_id else None,
            )

            # Trigger analysis if audio URL is available
            if audio_url and not missed_call:
                # TODO: Use Celery or BackgroundTasks for async execution
                # For now, call directly (will be async in production)
                await analyze_call_task(str(call.id))

            return call
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error ingesting call: {e}")
            traceback.print_exc()
            raise

    async def trigger_analysis(self, call_id: UUID) -> None:
        """
        Trigger AI analysis for a call.

        Args:
            call_id: Call ID
        """
        try:
            call = await self.call_repo.get_by_id(call_id)
            if not call:
                raise ValueError(f"Call {call_id} not found")

            if not call.audio_url:
                logger.warning("No audio URL for call", call_id=str(call_id))
                return

            # Submit call processing job to Shunya (replaces old transcription flow)
            if self.shoonya.is_available():
                try:
                    from datetime import datetime
                    from app.core.config import settings

                    # Construct webhook URL for Shunya to notify us when processing completes
                    webhook_url = f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete"

                    # Handle call_type: it may be an enum instance or a string
                    call_type_str = "csr_call"
                    if call.call_type:
                        if hasattr(call.call_type, 'value'):
                            # It's an enum instance
                            call_type_str = call.call_type.value
                        else:
                            # It's already a string
                            call_type_str = call.call_type
                    
                    result = await self.shoonya.process_call(
                        call_id=str(call.id),
                        company_id=str(call.company_id),
                        audio_url=call.audio_url,
                        phone_number=call.phone_number,
                        duration=call.duration_seconds or 0,
                        call_date=call.created_at.isoformat() if call.created_at else datetime.utcnow().isoformat(),
                        webhook_url=webhook_url,
                        metadata={
                            "call_type": call_type_str,
                            **(call.extra_metadata or {}),
                        },
                    )
                    logger.info(
                        "Call processing job submitted",
                        call_id=str(call_id),
                        job_id=result.get("job_id"),
                    )
                except Exception as e:
                    logger.error("Failed to submit call processing", call_id=str(call_id), error=str(e))
                    traceback.print_exc()
                    raise
        except Exception as e:
            logger.error(f"Error triggering analysis: {e}")
            raise e

    async def process_analysis(
        self,
        call_id: UUID,
        analysis_data: dict,
        transcript: Optional[str] = None,
    ) -> CallAnalysis:
        """
        Process call analysis data from Shunya Summary API or webhook.

        Args:
            call_id: Call ID
            analysis_data: Complete analysis data from Shunya (Summary API structure)
            transcript: Optional transcript text

        Returns:
            Created or updated CallAnalysis

        Expected structure from Shunya Summary API:
        {
            "summary": {
                "summary": "...",
                "key_points": [...],
                "action_items": [...],
                "next_steps": [...],
                "pending_actions": [...],
                "sentiment_score": 0.82,
                "confidence_score": 0.86
            },
            "compliance": {
                "sop_compliance": {
                    "score": 0.72,
                    "compliance_rate": 0.72,
                    "stages": {
                        "total": 7,
                        "followed": [...],
                        "missed": [...]
                    },
                    "issues": [...],
                    "positive_behaviors": [...],
                    "confidence": 0.84
                }
            },
            "objections": {
                "objections": [...],
                "total_count": 0
            },
            "qualification": {
                "bant_scores": {
                    "need": 0.8,
                    "budget": 0.0,
                    "timeline": 0.0,
                    "authority": 1.0
                },
                "overall_score": 0.45,
                "qualification_status": "cold",
                "booking_status": "not_booked",
                "call_outcome_category": "qualified_but_unbooked",
                "appointment_*": {...},
                "service_*": {...},
                "customer_*": {...},
                "follow_up_*": {...}
            }
        }
        """
        try:
            # Get the call
            call = await self.call_repo.get_by_id(call_id)
            if not call:
                raise ValueError(f"Call {call_id} not found")

            # Update transcript if provided
            if transcript:
                call.transcript = transcript
                await self.call_repo.update(call_id, call)
                logger.info("Call transcript updated", call_id=str(call_id))

            # Parse complete summary structure from Shunya Summary API
            # Handle both old webhook format and new Summary API format

            # Extract summary section
            summary_section = analysis_data.get("summary", {})
            if isinstance(summary_section, dict):
                summary = summary_section.get("summary") or analysis_data.get("summary")  # Fallback to direct field
                key_points = summary_section.get("key_points", [])
                action_items = summary_section.get("action_items", [])
                next_steps = summary_section.get("next_steps", [])
                pending_actions = summary_section.get("pending_actions", [])
                sentiment_score = summary_section.get("sentiment_score") or analysis_data.get("sentiment_score")
                summary_confidence_score = summary_section.get("confidence_score")
            else:
                # Old format: summary is a string
                summary = summary_section if isinstance(summary_section, str) else analysis_data.get("summary")
                key_points = analysis_data.get("key_points", [])
                action_items = []
                next_steps = []
                pending_actions = None
                sentiment_score = analysis_data.get("sentiment_score")
                summary_confidence_score = None

            # Extract compliance section
            compliance_section = analysis_data.get("compliance", {})
            sop_compliance = compliance_section.get("sop_compliance", {}) if isinstance(compliance_section, dict) else {}

            # Extract target_role from compliance section
            compliance_target_role = compliance_section.get("target_role") if isinstance(compliance_section, dict) else None

            if sop_compliance:
                sop_compliance_score = sop_compliance.get("score")
                sop_compliance_rate = sop_compliance.get("compliance_rate")
                sop_compliance_confidence = sop_compliance.get("confidence")
                sop_stages = sop_compliance.get("stages", {})
                sop_stages_total = sop_stages.get("total")
                sop_stages_followed = sop_stages.get("followed", [])
                sop_stages_missed_list = sop_stages.get("missed", [])
                sop_compliance_issues = sop_compliance.get("issues", [])
                sop_compliance_positive_behaviors = sop_compliance.get("positive_behaviors", [])
            else:
                # Fallback to old format
                sop_compliance_score = analysis_data.get("sop_compliance_score")
                sop_compliance_rate = None
                sop_compliance_confidence = None
                sop_stages_total = None
                sop_stages_followed = analysis_data.get("sop_stages_completed", [])
                sop_stages_missed_list = analysis_data.get("sop_stages_missed", [])
                sop_compliance_issues = []
                sop_compliance_positive_behaviors = []

            # Parse SOP stages (store as strings - Shunya sends descriptive names that don't match our enums)
            sop_completed = []
            for stage in sop_stages_followed:
                if isinstance(stage, str):
                    sop_completed.append(stage)  # Store as string directly
                else:
                    sop_completed.append(str(stage))

            sop_missed = []
            for stage in sop_stages_missed_list:
                if isinstance(stage, str):
                    sop_missed.append(stage)  # Store as string directly
                else:
                    sop_missed.append(str(stage))

            # Extract objections section
            objections_section = analysis_data.get("objections", {})
            if isinstance(objections_section, dict):
                objections_raw = objections_section.get("objections", [])
                # Shunya Summary API uses "total_objections", but also check "total_count" for backward compatibility
                objections_total_count = objections_section.get("total_objections") or objections_section.get("total_count") or len(objections_raw)
            else:
                # Old format: objections is a list
                objections_raw = objections_section if isinstance(objections_section, list) else analysis_data.get("objections", [])
                objections_total_count = len(objections_raw)

            # Parse objections (store as strings - Shunya sends rich objection objects)
            # Extract category_text for the objections array, but keep full objects in raw_analysis
            objections = []
            objection_texts = []
            for obj in objections_raw:
                if isinstance(obj, str):
                    objections.append(obj)  # Store as string directly
                    objection_texts.append(obj)  # Use as text too
                elif isinstance(obj, dict):
                    # Handle rich objection objects with category_id, category_text, objection_text, etc.
                    # Extract category_text for the objections array
                    obj_type = obj.get("category_text") or obj.get("type") or obj.get("category")
                    if obj_type:
                        objections.append(str(obj_type))  # Store category_text as string
                    else:
                        # If no type found, try to extract from object
                        objections.append(str(obj))

                    # Extract objection_text for objection_texts array
                    obj_text = obj.get("objection_text") or obj.get("text") or ""
                    if obj_text:
                        objection_texts.append(str(obj_text))
                else:
                    objections.append(str(obj))
                    objection_texts.append(str(obj))

            # Extract qualification section
            qualification_section = analysis_data.get("qualification", {})
            if isinstance(qualification_section, dict):
                bant_scores = qualification_section.get("bant_scores", {})
                bant_need_score = bant_scores.get("need")
                bant_budget_score = bant_scores.get("budget")
                bant_timeline_score = bant_scores.get("timeline")
                bant_authority_score = bant_scores.get("authority")
                qualification_overall_score = qualification_section.get("overall_score")
                qualification_status = qualification_section.get("qualification_status")
                booking_status = qualification_section.get("booking_status")
                call_outcome_category = qualification_section.get("call_outcome_category")
                qualification_confidence_score = qualification_section.get("confidence_score")

                # Appointment fields
                appointment_confirmed = qualification_section.get("appointment_confirmed", False)
                appointment_date_str = qualification_section.get("appointment_date")
                appointment_date = None
                if appointment_date_str:
                    try:
                        appointment_date = date_parser.parse(appointment_date_str) if isinstance(appointment_date_str, str) else appointment_date_str
                    except Exception as e:
                        logger.warning(f"Failed to parse appointment_date: {e}")

                appointment_type = qualification_section.get("appointment_type")
                appointment_timezone = qualification_section.get("appointment_timezone")
                appointment_time_confidence = qualification_section.get("appointment_time_confidence")
                preferred_time_window = qualification_section.get("preferred_time_window")
                appointment_intent = qualification_section.get("appointment_intent")

                original_appointment_datetime_str = qualification_section.get("original_appointment_datetime")
                original_appointment_datetime = None
                if original_appointment_datetime_str:
                    try:
                        original_appointment_datetime = date_parser.parse(original_appointment_datetime_str) if isinstance(original_appointment_datetime_str, str) else original_appointment_datetime_str
                    except Exception as e:
                        logger.warning(f"Failed to parse original_appointment_datetime: {e}")

                new_requested_time_str = qualification_section.get("new_requested_time")
                new_requested_time = None
                if new_requested_time_str:
                    try:
                        new_requested_time = date_parser.parse(new_requested_time_str) if isinstance(new_requested_time_str, str) else new_requested_time_str
                    except Exception as e:
                        logger.warning(f"Failed to parse new_requested_time: {e}")

                # Service fields
                service_requested = qualification_section.get("service_requested")
                service_not_offered_reason = qualification_section.get("service_not_offered_reason")
                service_address_raw = qualification_section.get("service_address_raw")
                service_address_structured = qualification_section.get("service_address_structured")
                address_confidence = qualification_section.get("address_confidence")

                # Customer fields
                customer_name = qualification_section.get("customer_name")
                customer_name_confidence = qualification_section.get("customer_name_confidence")
                decision_makers = qualification_section.get("decision_makers", [])
                urgency_signals = qualification_section.get("urgency_signals", [])
                budget_indicators = qualification_section.get("budget_indicators", [])

                # Follow-up fields
                follow_up_required = qualification_section.get("follow_up_required", False)
                follow_up_reason = qualification_section.get("follow_up_reason")

                # Additional qualification fields (new in Shunya Summary API)
                detected_call_type = qualification_section.get("detected_call_type")
                is_existing_customer = qualification_section.get("is_existing_customer")
                is_deprioritized = qualification_section.get("is_deprioritized", False)
                service_wait_time_weeks = qualification_section.get("service_wait_time_weeks")
                applied_rules = qualification_section.get("applied_rules", [])
                property_details = qualification_section.get("property_details")
                customer_details = qualification_section.get("customer_details")
            else:
                # Old format: direct fields
                bant_need_score = None
                bant_budget_score = None
                bant_timeline_score = None
                bant_authority_score = None
                qualification_overall_score = None
                qualification_status = analysis_data.get("qualification_status")
                booking_status = analysis_data.get("booking_status")
                call_outcome_category = None
                qualification_confidence_score = None
                appointment_confirmed = False
                appointment_date = None
                appointment_type = None
                appointment_timezone = None
                appointment_time_confidence = None
                preferred_time_window = None
                appointment_intent = None
                original_appointment_datetime = None
                new_requested_time = None
                service_requested = None
                service_not_offered_reason = None
                service_address_raw = None
                service_address_structured = None
                address_confidence = None
                customer_name = None
                customer_name_confidence = None
                decision_makers = []
                urgency_signals = []
                budget_indicators = []
                follow_up_required = False
                follow_up_reason = None
                # New fields default to None/empty
                detected_call_type = None
                is_existing_customer = None
                is_deprioritized = None
                service_wait_time_weeks = None
                applied_rules = []
                property_details = None
                customer_details = None

            # Convert float values
            def safe_float(value):
                return float(value) if value is not None else None

            # Create CallAnalysis domain model with all fields
            call_analysis = CallAnalysis(
                call_id=call_id,
                company_id=call.company_id,
                status=AnalysisStatus.COMPLETED,
                # Qualification
                qualification_status=qualification_status,
                booking_status=booking_status,
                # Objections
                objections=objections,
                objection_texts=objection_texts,
                objections_total_count=objections_total_count,
                # SOP Compliance
                sop_stages_completed=sop_completed,
                sop_stages_missed=sop_missed,
                sop_stages_total=sop_stages_total,
                sop_compliance_score=safe_float(sop_compliance_score),
                sop_compliance_rate=safe_float(sop_compliance_rate),
                sop_compliance_confidence=safe_float(sop_compliance_confidence),
                sop_compliance_issues=sop_compliance_issues,
                sop_compliance_positive_behaviors=sop_compliance_positive_behaviors,
                compliance_target_role=compliance_target_role,
                # Sentiment
                sentiment_score=safe_float(sentiment_score),
                # Summary
                summary=summary,
                key_points=key_points,
                action_items=action_items,
                next_steps=next_steps,
                pending_actions=pending_actions,
                summary_confidence_score=safe_float(summary_confidence_score),
                # BANT Scores
                bant_need_score=safe_float(bant_need_score),
                bant_budget_score=safe_float(bant_budget_score),
                bant_timeline_score=safe_float(bant_timeline_score),
                bant_authority_score=safe_float(bant_authority_score),
                qualification_overall_score=safe_float(qualification_overall_score),
                qualification_confidence_score=safe_float(qualification_confidence_score),
                call_outcome_category=call_outcome_category,
                # Appointment
                appointment_confirmed=appointment_confirmed,
                appointment_date=appointment_date,
                appointment_type=appointment_type,
                appointment_timezone=appointment_timezone,
                appointment_time_confidence=safe_float(appointment_time_confidence),
                preferred_time_window=preferred_time_window,
                appointment_intent=appointment_intent,
                original_appointment_datetime=original_appointment_datetime,
                new_requested_time=new_requested_time,
                # Service
                service_requested=service_requested,
                service_not_offered_reason=service_not_offered_reason,
                service_address_raw=service_address_raw,
                service_address_structured=service_address_structured,
                address_confidence=safe_float(address_confidence),
                # Customer
                customer_name=customer_name,
                customer_name_confidence=safe_float(customer_name_confidence),
                decision_makers=decision_makers,
                urgency_signals=urgency_signals,
                budget_indicators=budget_indicators,
                # Follow-up
                follow_up_required=follow_up_required,
                follow_up_reason=follow_up_reason,
                # Additional qualification fields
                detected_call_type=detected_call_type,
                is_existing_customer=is_existing_customer,
                is_deprioritized=is_deprioritized,
                service_wait_time_weeks=service_wait_time_weeks,
                applied_rules=applied_rules,
                property_details=property_details,
                customer_details=customer_details,
                # Raw data
                raw_analysis=analysis_data,  # Store complete raw data for reference (includes full objection objects)
            )

            # Upsert analysis
            analysis = await self.analysis_repo.upsert_by_call_id(call_id, call_analysis)
            logger.info("Call analysis processed", call_id=str(call_id), analysis_id=str(analysis.id))

            # Process pending actions from analysis
            await self._process_pending_actions(call, analysis_data, analysis)

            # Update dependent entities based on analysis
            await self._update_dependent_entities(call, analysis)

            return analysis

        except Exception as e:
            logger.error(f"Error processing analysis: {e}", call_id=str(call_id))
            raise e

    def _map_to_lead_status(
        self,
        qualification_status: Optional[str],
        booking_status: Optional[str],
    ) -> LeadStatus:
        """
        Map qualification_status and booking_status to LeadStatus.
        
        Args:
            qualification_status: 'hot', 'warm', 'cold', 'unqualified', or None
            booking_status: 'booked', 'not_booked', 'service_not_offered', or None
            
        Returns:
            Appropriate LeadStatus enum value
        """
        if not qualification_status:
            return LeadStatus.NEW
        
        qual_lower = qualification_status.lower()
        booking_lower = booking_status.lower() if booking_status else None
        
        # If qualified and booked
        if qual_lower in ['hot', 'warm', 'cold'] and booking_lower == 'booked':
            return LeadStatus.QUALIFIED_BOOKED
        
        # If qualified but service not offered
        if qual_lower in ['hot', 'warm', 'cold'] and booking_lower == 'service_not_offered':
            return LeadStatus.QUALIFIED_SERVICE_NOT_OFFERED
        
        # If qualified but not booked
        if qual_lower in ['hot', 'warm', 'cold'] and booking_lower == 'not_booked':
            return LeadStatus.QUALIFIED_UNBOOKED
        
        # Map qualification status directly (when booking_status is None or doesn't match above)
        if qual_lower == 'hot':
            return LeadStatus.HOT
        elif qual_lower == 'warm':
            return LeadStatus.WARM
        elif qual_lower == 'cold':
            return LeadStatus.WARM  # Cold leads are still warm leads
        elif qual_lower == 'unqualified':
            return LeadStatus.ABANDONED
        
        # Default to NEW if status is unknown
        return LeadStatus.NEW
    
    def _map_to_deal_status(
        self,
        booking_status: Optional[str],
    ) -> Optional[DealStatus]:
        """
        Map booking_status to DealStatus.
        
        Args:
            booking_status: 'booked', 'not_booked', 'service_not_offered', or None
            
        Returns:
            Appropriate DealStatus enum value or None
        """
        if not booking_status:
            return None
        
        booking_lower = booking_status.lower()
        
        if booking_lower == 'booked':
            return DealStatus.BOOKED
        elif booking_lower == 'not_booked':
            return DealStatus.NURTURING
        elif booking_lower == 'service_not_offered':
            return DealStatus.NEW
        
        return None
    
    async def _find_existing_lead(
        self,
        contact_card_id: UUID,
        company_id: UUID,
    ) -> Optional[Lead]:
        """
        Find existing lead by contact_card_id and company_id.
        
        Args:
            contact_card_id: Contact card ID
            company_id: Company ID
            
        Returns:
            Lead if found, None otherwise
        """
        try:
            from sqlalchemy import select
            from app.infrastructure.database.models.lead import LeadORM
            
            result = await self.session.execute(
                select(LeadORM).where(
                    LeadORM.contact_card_id == contact_card_id,
                    LeadORM.company_id == company_id,
                )
            )
            lead_orm = result.scalar_one_or_none()
            
            if lead_orm:
                return self.lead_repo._to_domain(lead_orm)
            return None
        except Exception as e:
            logger.error(f"Error finding existing lead: {e}")
            return None

    async def _upsert_appointment_from_call(
        self,
        call: Call,
        analysis: CallAnalysis,
    ) -> None:
        """
        Create or update an appointment from a call with booking_status=booked.
        Populates the appointments table for companies without GoHighLevel integration.
        """
        try:
            if not call.lead_id or not call.contact_card_id:
                logger.debug(
                    "Skipping appointment create/update - call has no lead_id or contact_card_id",
                    call_id=str(call.id),
                )
                return

            # Resolve scheduled_start from analysis or call
            scheduled_start = (
                getattr(analysis, "appointment_date", None)
                or getattr(analysis, "original_appointment_datetime", None)
                or getattr(analysis, "new_requested_time", None)
            )
            if not scheduled_start:
                scheduled_start = getattr(call, "created_at", None) or datetime.now(timezone.utc)
            if hasattr(scheduled_start, "tzinfo") and scheduled_start.tzinfo is None:
                scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)

            # Optional: scheduled_end (leave None or set default duration)
            scheduled_end = None

            # Location from analysis
            location_address = getattr(analysis, "service_address_raw", None)
            if not location_address and getattr(analysis, "service_address_structured", None):
                addr = analysis.service_address_structured
                if isinstance(addr, dict):
                    parts = [
                        addr.get("line1") or addr.get("address"),
                        addr.get("city"),
                        addr.get("state"),
                        addr.get("postal_code"),
                        addr.get("country"),
                    ]
                    location_address = ", ".join(p for p in parts if p) or None

            # Outcome: pending for call-created appointments
            outcome = AppointmentOutcome.PENDING

            appointment_data = {
                "company_id": call.company_id,
                "lead_id": call.lead_id,
                "contact_card_id": call.contact_card_id,
                "scheduled_start": scheduled_start,
                "scheduled_end": scheduled_end,
                "location_address": location_address,
                "outcome": outcome,
                "assigned_rep_id": call.handled_by_user_id,
                "interaction_id": call.id,
                "extra_metadata": {
                    "created_from_call": str(call.id),
                    "source": "call_analysis",
                },
            }

            existing = await self.appointment_repo.get_by_interaction_id(call.id)
            if existing:
                for key, value in appointment_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                await self.appointment_repo.update(existing.id, existing)
                logger.info(
                    "Updated appointment from call",
                    call_id=str(call.id),
                    appointment_id=str(existing.id),
                )
                appt_id = existing.id
            else:
                appointment = Appointment(**appointment_data)
                created = await self.appointment_repo.create(appointment)
                logger.info(
                    "Created appointment from call (no GHL)",
                    call_id=str(call.id),
                    appointment_id=str(created.id),
                )
                appt_id = created.id

            # Trigger background geocoding if location_address is set
            if location_address:
                import asyncio
                from app.infrastructure.integrations.google_geocoding import geocode_appointment_background
                asyncio.create_task(geocode_appointment_background(
                    appointment_id=appt_id,
                    location_address=location_address,
                ))
        except Exception as e:
            logger.error(
                f"Error upserting appointment from call: {e}",
                call_id=str(call.id),
            )
            traceback.print_exc()
            # Non-critical: do not re-raise

    async def _update_dependent_entities(
        self,
        call: Call,
        analysis: CallAnalysis,
    ) -> None:
        """
        Update dependent entities based on call analysis.

        Updates:
        - Lead status based on qualification_status and booking_status
        - Creates lead if it doesn't exist and call has contact_card_id
        - Updates call.lead_id after creating/updating lead
        - Appointment status based on booking_status
        - Contact card metadata
        """
        try:
            # Skip if no contact_card_id (can't create/update lead without contact)
            if not call.contact_card_id:
                logger.debug(
                    "Skipping lead creation/update - no contact_card_id",
                    call_id=str(call.id),
                )
                return
            
            # Skip if qualification_status is missing (analysis not complete)
            if not analysis.qualification_status:
                logger.debug(
                    "Skipping lead creation/update - no qualification_status",
                    call_id=str(call.id),
                )
                return
            
            # Map to lead status and deal status
            new_lead_status = self._map_to_lead_status(
                analysis.qualification_status,
                analysis.booking_status,
            )
            new_deal_status = self._map_to_deal_status(analysis.booking_status)
            
            # Find existing lead or create new one
            existing_lead = None
            if call.lead_id:
                # Try to get existing lead by lead_id first
                existing_lead = await self.lead_repo.get_by_id(call.lead_id)
            
            # If not found by lead_id, try to find by contact_card_id and company_id
            if not existing_lead:
                existing_lead = await self._find_existing_lead(
                    call.contact_card_id,
                    call.company_id,
                )
            
            if existing_lead:
                # Update existing lead - always update with latest status (even if worse)
                logger.info(
                    "Updating existing lead",
                    lead_id=str(existing_lead.id),
                    old_status=existing_lead.status,
                    new_status=new_lead_status,
                    old_deal_status=existing_lead.deal_status,
                    new_deal_status=new_deal_status,
                )
                
                # Update lead fields
                existing_lead.status = new_lead_status
                existing_lead.deal_status = new_deal_status
                
                # Update extra_metadata with call analysis info
                if existing_lead.extra_metadata is None:
                    existing_lead.extra_metadata = {}
                
                # Store latest call analysis info
                existing_lead.extra_metadata['last_call_analysis'] = {
                    'call_id': str(call.id),
                    'qualification_status': analysis.qualification_status,
                    'booking_status': analysis.booking_status,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                }
                
                # Update lead
                updated_lead = await self.lead_repo.update(existing_lead.id, existing_lead)
                
                # Update call.lead_id if it wasn't set
                if not call.lead_id:
                    call.lead_id = updated_lead.id
                    await self.call_repo.update(call.id, call)
                    logger.info(
                        "Linked call to existing lead",
                        call_id=str(call.id),
                        lead_id=str(updated_lead.id),
                    )
            else:
                # Create new lead
                logger.info(
                    "Creating new lead from call analysis",
                    call_id=str(call.id),
                    contact_card_id=str(call.contact_card_id),
                    qualification_status=analysis.qualification_status,
                    booking_status=analysis.booking_status,
                )
                
                new_lead = Lead(
                    company_id=call.company_id,
                    
                    contact_card_id=call.contact_card_id,
                    status=new_lead_status,
                    deal_status=new_deal_status,
                    extra_metadata={
                        'created_from_call': str(call.id),
                        'last_call_analysis': {
                            'call_id': str(call.id),
                            'qualification_status': analysis.qualification_status,
                            'booking_status': analysis.booking_status,
                            'created_at': datetime.now(timezone.utc).isoformat(),
                        },
                    },
                )
                
                created_lead = await self.lead_repo.create(new_lead)
                
                # Update call.lead_id
                call.lead_id = created_lead.id
                await self.call_repo.update(call.id, call)
                
                logger.info(
                    "Created new lead and linked to call",
                    call_id=str(call.id),
                    lead_id=str(created_lead.id),
                )

            # Create or update appointment when booking_status is booked (for companies without GHL)
            if analysis.booking_status and str(analysis.booking_status).lower() in ["booked", "confirmed"]:
                await self._upsert_appointment_from_call(call, analysis)

            # Update contact card metadata with analysis insights
            if call.contact_card_id:
                # TODO: Implement ContactCardRepository and update metadata
                # Store key insights, sentiment, objections in extra_metadata
                logger.info(
                    "Contact card update needed",
                    contact_card_id=str(call.contact_card_id),
                )

            logger.info("Dependent entities update completed", call_id=str(call.id))

        except Exception as e:
            logger.error(
                f"Error updating dependent entities: {e}",
                call_id=str(call.id),
            )
            traceback.print_exc()
            # Don't raise - this is non-critical

    async def _process_pending_actions(
        self,
        call: Call,
        analysis_data: Dict[str, Any],
        analysis: CallAnalysis,
    ) -> None:
        """
        Process pending actions from analysis data and insert into pending_actions table.

        Args:
            call: The call record
            analysis_data: Raw analysis data from Shunya (can be top-level or nested in summary/compliance/qualification)
            analysis: The created/updated analysis
        """
        try:
            # Extract pending_actions from analysis_data
            # Shunya Summary API structure: {summary: {pending_actions: [...]}, ...}
            # Also check top-level for backward compatibility
            pending_actions_data = None

            # Check in summary section first (Shunya Summary API format)
            summary_section = analysis_data.get("summary", {})
            if isinstance(summary_section, dict):
                pending_actions_data = summary_section.get("pending_actions", [])
                if pending_actions_data:
                    logger.debug(f"Found {len(pending_actions_data)} pending actions in summary section", call_id=str(call.id))

            # Fallback to top-level (legacy format)
            if not pending_actions_data:
                pending_actions_data = analysis_data.get("pending_actions", [])
                if pending_actions_data:
                    logger.debug(f"Found {len(pending_actions_data)} pending actions at top level", call_id=str(call.id))

            # If still not found, check if analysis_data itself is the summary section
            if not pending_actions_data and isinstance(analysis_data, dict) and "pending_actions" in analysis_data:
                pending_actions_data = analysis_data.get("pending_actions", [])
                if pending_actions_data:
                    logger.debug(f"Found {len(pending_actions_data)} pending actions in analysis_data", call_id=str(call.id))

            if not pending_actions_data:
                logger.debug("No pending actions found in analysis data", call_id=str(call.id))
                return

            for action_data in pending_actions_data:
                try:
                    # Initialize variables
                    owner = None
                    confidence = None
                    contact_method = None
                    due_at = None
                    priority = None

                    # Handle both dict and string formats
                    if isinstance(action_data, str):
                        # Legacy format: simple string
                        action_type = action_data
                        raw_text = action_data
                    else:
                        # New format: dict with fields (Shunya format)
                        action_type = action_data.get("action_type") or action_data.get("action") or action_data.get("type") or "unknown"
                        raw_text = action_data.get("raw_text") or action_data.get("action") or action_type
                        due_at_str = action_data.get("due_at")
                        priority = action_data.get("priority")

                        # Extract additional fields from Shunya payload
                        owner = action_data.get("owner")  # "company" or user ID
                        confidence = action_data.get("confidence")
                        contact_method = action_data.get("contact_method")

                        # Parse due_at if provided (should be UTC)
                        if due_at_str:
                            if isinstance(due_at_str, datetime):
                                due_at = due_at_str
                            elif isinstance(due_at_str, str):
                                try:
                                    # Try ISO format first
                                    due_at = datetime.fromisoformat(due_at_str.replace('Z', '+00:00'))
                                except ValueError:
                                    try:
                                        # Try other common formats
                                        due_at = datetime.strptime(due_at_str, "%Y-%m-%d %H:%M:%S%z")
                                    except ValueError:
                                        logger.warning(f"Could not parse due_at: {due_at_str}")
                                        due_at = None

                        # Convert priority string to int if needed
                        if isinstance(priority, str):
                            priority_map = {"high": 3, "medium": 2, "low": 1}
                            priority = priority_map.get(priority.lower(), 2)
                        elif priority is None:
                            priority = 2  # Default to medium

                    # Determine owner_id
                    # Shunya sends "owner": "company" or a user ID
                    # If owner is "company", use call.handled_by_user_id or leave as None
                    owner_id = None
                    if owner and owner != "company":
                        try:
                            owner_id = UUID(owner) if isinstance(owner, str) else owner
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid owner ID format: {owner}, using call owner")
                            owner_id = call.handled_by_user_id
                    else:
                        # Use call owner if available, otherwise leave as None (will be assigned based on action type)
                        owner_id = call.handled_by_user_id

                    # Create PendingAction domain model
                    pending_action = PendingAction(
                        company_id=call.company_id,
                        lead_id=call.lead_id,
                        call_id=call.id,
                        appointment_id=None,  # Only for appointment recordings
                        action_type=action_type,
                        raw_text=raw_text,
                        status=PendingActionStatus.PENDING,
                        due_at=due_at,
                        priority=priority,
                        owner_id=owner_id,  # May be None if call wasn't handled by a user
                        source="shunya",
                        extra_metadata={
                            "from_analysis": str(analysis.id),
                            "shunya_owner": owner,  # Store original owner value from Shunya
                            "confidence": confidence,
                            "contact_method": contact_method,
                            "analysis_data": action_data if isinstance(action_data, dict) else None,
                        },
                    )

                    # Insert into database
                    await self.pending_action_repo.create(pending_action)
                    logger.debug(
                        "Pending action created",
                        call_id=str(call.id),
                        action_type=action_type,
                        due_at=due_at.isoformat() if due_at else None,
                    )

                except Exception as e:
                    logger.error(
                        f"Error processing pending action: {e}",
                        call_id=str(call.id),
                        action_data=action_data,
                    )
                    traceback.print_exc()
                    # Continue processing other actions
                    continue

            logger.info(
                "Pending actions processed",
                call_id=str(call.id),
                count=len(pending_actions_data) if pending_actions_data else 0,
            )

        except Exception as e:
            logger.error(
                f"Error processing pending actions: {e}",
                call_id=str(call.id),
            )
            traceback.print_exc()
            # Don't raise - pending actions are non-critical

    async def get_call_logs(
        self,
        company_id: UUID,
        search: Optional[str] = None,
        csr_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        booking_filter: Optional[str] = None,
        existing_customer: Optional[bool] = None,
        quick_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        current_user: Optional["User"] = None,
    ) -> Dict[str, Any]:
        """
        Get call logs with summary statistics and filtered call list.

        Returns:
            Dictionary with:
            - summary: Statistics (total_calls, qualified, booked, abandoned)
            - calls: List of call log entries with all details
            - total: Total count of calls matching filters
        """
        try:
            from sqlalchemy import select, func, or_, and_, case
            from sqlalchemy.orm import selectinload
            from app.infrastructure.database.models.call import CallORM
            from app.infrastructure.database.models.analysis import CallAnalysisORM
            from app.infrastructure.database.models.contact import ContactCardORM
            from app.infrastructure.database.models.user import UserORM
            from app.infrastructure.database.models.lead import LeadORM

            # Build base query with joins
            query = select(
                CallORM,
                CallAnalysisORM,
                ContactCardORM,
                UserORM,
                LeadORM
            ).outerjoin(
                CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).outerjoin(
                UserORM, CallORM.handled_by_user_id == UserORM.id
            ).outerjoin(
                LeadORM, CallORM.lead_id == LeadORM.id
            ).where(
                CallORM.company_id == company_id
            )

            # Apply filters
            if csr_id:
                query = query.where(CallORM.handled_by_user_id == csr_id)

            # Status filter (qualification status)
            # Qualified statuses: hot, cold, warm, qualified
            if status_filter and status_filter.lower() != "all":
                if status_filter.lower() == "qualified":
                    # Consider hot, cold, warm, qualified as qualified
                    query = query.where(
                        func.lower(CallAnalysisORM.qualification_status).in_(
                            [s.lower() for s in QUALIFIED_STATUSES]
                        )
                    )
                elif status_filter.lower() == "unqualified":
                    # Unqualified: not in qualified statuses and not null
                    query = query.where(
                        or_(
                            ~func.lower(CallAnalysisORM.qualification_status).in_(
                                [s.lower() for s in QUALIFIED_STATUSES]
                            ),
                            CallAnalysisORM.qualification_status.is_(None)
                        )
                    )

            # Booking filter (case-insensitive: DB may store "Booked", "booked", etc.)
            if booking_filter and booking_filter.lower() != "all":
                if booking_filter.lower() == "booked":
                    query = query.where(func.lower(CallAnalysisORM.booking_status) == "booked")
                elif booking_filter.lower() == "unbooked":
                    query = query.where(
                        or_(
                            CallAnalysisORM.booking_status.is_(None),
                            func.lower(CallAnalysisORM.booking_status) != "booked"
                        )
                    )

            # Existing customer filter (from call analysis)
            if existing_customer is not None:
                if existing_customer:
                    query = query.where(CallAnalysisORM.is_existing_customer == True)
                else:
                    query = query.where(
                        or_(
                            CallAnalysisORM.is_existing_customer == False,
                            CallAnalysisORM.is_existing_customer.is_(None)
                        )
                    )

            # Quick filters
            if quick_filter:
                quick_filter_lower = quick_filter.lower()
                if quick_filter_lower == "hot_lead":
                    query = query.where(LeadORM.status == "hot")
                elif quick_filter_lower == "qualified_unbooked":
                    query = query.where(
                        and_(
                            func.lower(CallAnalysisORM.qualification_status).in_(
                                [s.lower() for s in QUALIFIED_STATUSES]
                            ),
                            or_(
                                CallAnalysisORM.booking_status.is_(None),
                                func.lower(CallAnalysisORM.booking_status) != "booked"
                            )
                        )
                    )
                elif quick_filter_lower == "qualified_booked":
                    query = query.where(
                        and_(
                            func.lower(CallAnalysisORM.qualification_status).in_(
                                [s.lower() for s in QUALIFIED_STATUSES]
                            ),
                            func.lower(CallAnalysisORM.booking_status) == "booked"
                        )
                    )
                elif quick_filter_lower == "abandoned":
                    query = query.where(LeadORM.status == "abandoned")
                elif quick_filter_lower == "residential":
                    # Check in contact card property_snapshot or extra_metadata
                    query = query.where(
                        or_(
                            ContactCardORM.property_snapshot['property_type'].astext == "residential",
                            ContactCardORM.extra_metadata['property_type'].astext == "residential"
                        )
                    )
                elif quick_filter_lower == "commercial":
                    query = query.where(
                        or_(
                            ContactCardORM.property_snapshot['property_type'].astext == "commercial",
                            ContactCardORM.extra_metadata['property_type'].astext == "commercial"
                        )
                    )

            # Search filter (customer name, CSR name, or phone number)
            if search:
                search_term = f"%{search.lower()}%"
                query = query.where(
                    or_(
                        func.lower(ContactCardORM.first_name).like(search_term),
                        func.lower(ContactCardORM.last_name).like(search_term),
                        func.lower(ContactCardORM.primary_phone).like(search_term),
                        func.lower(UserORM.first_name).like(search_term),
                        func.lower(UserORM.last_name).like(search_term),
                    )
                )

            # Get total count before pagination
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.session.execute(count_query)
            total = total_result.scalar() or 0

            # Apply ordering and pagination
            query = query.order_by(CallORM.created_at.desc())
            query = query.offset(skip).limit(limit)

            # Execute query
            results = await self.session.execute(query)
            rows = results.all()

            # Calculate summary statistics (from all calls, excluding existing customers and service_not_offered)
            # Qualified statuses: hot, cold, warm, qualified
            summary_base = and_(
                CallORM.company_id == company_id,
                or_(
                    CallAnalysisORM.is_existing_customer == False,
                    CallAnalysisORM.is_existing_customer.is_(None)
                ),
                or_(
                    CallAnalysisORM.booking_status.is_(None),
                    func.lower(CallAnalysisORM.booking_status) != "service_not_offered"
                ),
                or_(
                    CallAnalysisORM.service_not_offered_reason.is_(None),
                    CallAnalysisORM.service_not_offered_reason == ""
                ),
            )
            summary_query = select(
                func.count(CallORM.id).label('total_calls'),
                func.sum(
                    case(
                        (func.lower(CallAnalysisORM.qualification_status).in_(
                            [s.lower() for s in QUALIFIED_STATUSES]
                        ), 1),
                        else_=0
                    )
                ).label('qualified'),
                func.sum(
                    case(
                        (func.lower(CallAnalysisORM.booking_status) == "booked", 1),
                        else_=0
                    )
                ).label('booked'),
                func.sum(
                    case(
                        (LeadORM.status == "abandoned", 1),
                        else_=0
                    )
                ).label('abandoned'),
            ).outerjoin(
                CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id
            ).outerjoin(
                LeadORM, CallORM.lead_id == LeadORM.id
            ).where(
                summary_base
            )

            summary_result = await self.session.execute(summary_query)
            summary_row = summary_result.first()

            summary = {
                "total_calls": summary_row.total_calls or 0,
                "qualified": int(summary_row.qualified or 0),
                "booked": int(summary_row.booked or 0),
                "abandoned": int(summary_row.abandoned or 0),
            }

            # Build call log entries
            calls = []
            for call, analysis, contact, user, lead in rows:
                # Get CSR name
                csr_name = None
                if user:
                    if user.first_name and user.last_name:
                        csr_name = f"{user.first_name} {user.last_name}"
                    elif user.first_name:
                        csr_name = user.first_name
                    elif user.last_name:
                        csr_name = user.last_name

                # Get customer name
                customer_name = None
                phone_number = call.phone_number
                if contact:
                    if contact.first_name and contact.last_name:
                        customer_name = f"{contact.first_name} {contact.last_name}".upper()
                    elif contact.first_name:
                        customer_name = contact.first_name.upper()
                    elif contact.last_name:
                        customer_name = contact.last_name.upper()
                    if contact.primary_phone:
                        phone_number = contact.primary_phone

                # Format phone number
                formatted_phone = phone_number
                if phone_number and len(phone_number) == 10:
                    formatted_phone = f"({phone_number[:3]}) {phone_number[3:6]}-{phone_number[6:]}"
                elif phone_number and len(phone_number) > 10:
                    # Try to format if it has country code
                    if phone_number.startswith("+1"):
                        clean_phone = phone_number[2:].replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                        if len(clean_phone) == 10:
                            formatted_phone = f"({clean_phone[:3]}) {clean_phone[3:6]}-{clean_phone[6:]}"

                # Get qualification and booking status
                # Qualified statuses: hot, cold, warm, qualified
                is_qualified = analysis and is_qualified_status(analysis.qualification_status) if analysis else False
                is_booked = analysis and analysis.booking_status and str(analysis.booking_status).lower() == "booked" if analysis else False

                # Get score (use SOP compliance score or sentiment score)
                score = None
                if analysis:
                    if analysis.sop_compliance_score is not None:
                        score = int(analysis.sop_compliance_score)
                    elif analysis.sentiment_score is not None:
                        score = int(analysis.sentiment_score * 100)  # Convert to 0-100 scale

                # Get objections
                objections = None
                if analysis and analysis.objections:
                    # Join objections with comma
                    objections = ", ".join(analysis.objections[:3])  # Limit to first 3
                    if len(analysis.objections) > 3:
                        objections += "..."

                # Get tags (from lead status or extra_metadata)
                tags = []
                if lead:
                    # Map lead status to tags
                    status_to_tag = {
                        "hot": "Hot lead",
                        "warm": "Warm lead",
                        "new": "New",
                        "qualified_booked": "Qualified, booked",
                        "qualified_unbooked": "Qualified, unbooked",
                        "abandoned": "Abandoned",
                        "nurturing": "Follow-up",
                    }
                    if lead.status in status_to_tag:
                        tags.append(status_to_tag[lead.status])

                    # Check for additional tags in extra_metadata
                    if lead.extra_metadata:
                        if lead.extra_metadata.get("tags"):
                            if isinstance(lead.extra_metadata["tags"], list):
                                tags.extend(lead.extra_metadata["tags"])
                            elif isinstance(lead.extra_metadata["tags"], str):
                                tags.append(lead.extra_metadata["tags"])

                # Format duration
                duration_str = None
                if call.duration_seconds:
                    minutes = call.duration_seconds // 60
                    seconds = call.duration_seconds % 60
                    duration_str = f"{minutes}m {seconds}s"

                # Format call received date
                call_received = None
                if call.created_at:
                    call_received = call.created_at.strftime("%m/%d/%y, %I:%M %p")

                # Get dropdown fields
                audio_url = call.audio_url
                transcript = call.transcript
                call_summary = analysis.summary if analysis else None
                key_items = list(analysis.key_points) if (analysis and analysis.key_points) else None
                action_items = list(analysis.action_items) if (analysis and analysis.action_items) else None

                booking_status_raw = (analysis.booking_status or "").strip() if analysis else None
                if not booking_status_raw:
                    booking_status_raw = None

                # Ghost mode filtering - only for meetings
                if current_user and call.interaction_type == "meeting":
                    ghost_mode_service = GhostModeService(self.session)
                    should_hide = await ghost_mode_service.should_hide_meeting_data(
                        interaction_type=call.interaction_type,
                        owner_user_id=call.handled_by_user_id,
                        company_id=company_id,
                        current_user=current_user,
                    )
                    if should_hide:
                        audio_url = None
                        transcript = None

                calls.append({
                    "call_id": str(call.id),
                    "lead_id": str(call.lead_id) if call.lead_id else None,
                    "call_received": call_received,
                    "duration": duration_str,
                    "csr_name": csr_name,
                    "answered_by_display": getattr(call, "answered_by_display", None) or None,
                    "customer_name": customer_name,
                    "phone_number": formatted_phone,
                    "is_qualified": is_qualified,
                    "is_booked": is_booked,
                    "booking_status": booking_status_raw,
                    "is_existing_customer": bool(analysis.is_existing_customer) if analysis and analysis.is_existing_customer is not None else None,
                    "lead_source": getattr(call, "lead_source", None) or None,
                    "audio_url": audio_url,
                    "transcript": transcript,
                    "call_summary": call_summary,
                    "key_items": key_items,
                    "action_items": action_items,
                    "score": score,
                    "objections": objections,
                    "tags": ", ".join(tags) if tags else None,
                })

            return {
                "summary": summary,
                "calls": calls,
                "total": total,
                "skip": skip,
                "limit": limit,
            }

        except Exception as e:
            logger.error(f"Error getting call logs: {e}")
            traceback.print_exc()
            raise
