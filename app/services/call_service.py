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
from app.core.datetime_utils import isoformat_utc
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
from app.domain.enums import LeadStatus, DealStatus, AppointmentOutcome, PipelineStage
from app.services.ghost_mode_service import GhostModeService
from app.domain.schemas.calls import (
    RecordingAnalysisResponse,
    RecordingSummary,
    RecordingObjections,
    RecordingCompliance,
    RecordingQualification,
    RecordingLeadScore,
    PendingActionDetail,
    ObjectionDetail,
    ComplianceStageDetail,
)

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

            # Find or create lead for this contact card
            if contact_card:
                try:
                    from app.domain.models.lead import Lead
                    from app.domain.enums import LeadStatus

                    existing_leads = await self.lead_repo.get_all(
                        filters={"contact_card_id": contact_card.id, "company_id": company_id}
                    )
                    lead = existing_leads[0] if existing_leads else None

                    if not lead:
                        lead = Lead(
                            company_id=company_id,
                            contact_card_id=contact_card.id,
                            status=LeadStatus.NEW,
                        )
                        lead = await self.lead_repo.create(lead)
                        logger.info(f"Lead created for call {call.id}", lead_id=str(lead.id))

                    if lead and not call.lead_id:
                        call.lead_id = lead.id
                        call = await self.call_repo.update(call.id, call)
                except Exception as e:
                    logger.error(f"Failed to find or create lead for call {call.id}: {e}")

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

    async def trigger_analysis_direct(
        self,
        company_id: UUID,
        audio_url: str,
        phone_number: str,
        contact_card_id: Optional[UUID] = None,
        lead_id: Optional[UUID] = None,
        handled_by_user_id: Optional[UUID] = None,
        call_type: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        call_date: Optional[str] = None,
        extra_metadata: Optional[dict] = None,
    ) -> dict:
        """
        Trigger AI analysis directly without creating a call record first.

        This is the new flow: CRM ╬ô├Ñ├å Shunya ╬ô├Ñ├å call_analyses ╬ô├Ñ├å appointment

        Args:
            company_id: Company UUID
            audio_url: URL to call recording
            phone_number: Phone number of the call
            contact_card_id: Optional contact card ID
            lead_id: Optional lead ID
            handled_by_user_id: Optional user who handled the call
            call_type: Type of call (csr_call, sales_call, etc.)
            duration_seconds: Call duration in seconds
            call_date: ISO format date string
            extra_metadata: Additional metadata to pass to Shunya

        Returns:
            dict with job_id and status from Shunya
        """
        try:
            if not audio_url:
                raise ValueError("audio_url is required")

            if not self.shoonya.is_available():
                raise ValueError("Shunya service is not available")

            from datetime import datetime
            from app.core.config import settings
            import uuid

            # Generate a temporary call_id for tracking (will be used as reference)
            temp_call_id = str(uuid.uuid4())

            # Construct webhook URL
            webhook_url = f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete"

            # Prepare metadata with all call context
            metadata = {
                "call_type": call_type or "csr_call",
                "contact_card_id": str(contact_card_id) if contact_card_id else None,
                "lead_id": str(lead_id) if lead_id else None,
                "handled_by_user_id": str(handled_by_user_id) if handled_by_user_id else None,
                "direct_analysis": True,  # Flag to indicate this was sent directly
                **(extra_metadata or {}),
            }

            # Submit to Shunya
            result = await self.shoonya.process_call(
                call_id=temp_call_id,
                company_id=str(company_id),
                audio_url=audio_url,
                phone_number=phone_number,
                duration=duration_seconds or 0,
                call_date=call_date or datetime.utcnow().isoformat(),
                webhook_url=webhook_url,
                metadata=metadata,
            )

            logger.info(
                "Call processing job submitted directly to Shunya",
                temp_call_id=temp_call_id,
                job_id=result.get("job_id"),
                company_id=str(company_id),
            )

            return {
                "job_id": result.get("job_id"),
                "temp_call_id": temp_call_id,
                "status": "submitted",
            }

        except Exception as e:
            logger.error(f"Error triggering direct analysis: {e}")
            traceback.print_exc()
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
            # Get the call (or create if NEW FLOW)
            call = await self.call_repo.get_by_id(call_id)

            if not call:
                # NEW FLOW: Call doesn't exist yet, create it from Shunya metadata
                logger.info(f"Call {call_id} not found, creating from Shunya results (NEW FLOW)")

                # Extract metadata from analysis_data
                metadata = analysis_data.get("metadata", {})
                qualification = analysis_data.get("qualification", {})

                # Get call details from metadata or qualification
                phone_number = metadata.get("phone_number", "unknown")
                company_id_str = metadata.get("company_id") or analysis_data.get("company_id")
                if not company_id_str:
                    raise ValueError("company_id required in metadata to create call record")

                # Extract other fields from metadata
                contact_card_id_str = metadata.get("contact_card_id")
                lead_id_str = metadata.get("lead_id")
                handled_by_user_id_str = metadata.get("handled_by_user_id")
                call_type_str = metadata.get("call_type", "csr_call")
                audio_url = metadata.get("audio_url")
                duration_seconds = metadata.get("duration", 0)

                # Create call record
                from app.domain.models.call import Call
                from app.domain.enums import CallType

                new_call = Call(
                    id=call_id,  # Use the temp_call_id from Shunya
                    company_id=UUID(company_id_str),
                    contact_card_id=UUID(contact_card_id_str) if contact_card_id_str else None,
                    lead_id=UUID(lead_id_str) if lead_id_str else None,
                    handled_by_user_id=UUID(handled_by_user_id_str) if handled_by_user_id_str else None,
                    phone_number=phone_number,
                    call_type=call_type_str,
                    audio_url=audio_url,
                    duration_seconds=duration_seconds,
                    transcript=transcript,
                    missed_call=False,
                    interaction_type="call",
                    lead_source=metadata.get("ghl_lead_source") or metadata.get("lead_source"),
                    extra_metadata=metadata,
                )

                call = await self.call_repo.create(new_call)
                logger.info(
                    "Created call record from Shunya results",
                    call_id=str(call_id),
                    company_id=company_id_str,
                    lead_id=lead_id_str,
                )
            else:
                # OLD FLOW: Call exists, update transcript if provided
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

                # Scope classification: IN_SCOPE -> "in", OUT_OF_SCOPE -> "out"
                scope_classification = qualification_section.get("scope_classification", "")
                scope = "out" if scope_classification == "OUT_OF_SCOPE" else "in"
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
                scope = None

            # Convert float values
            def safe_float(value):
                return float(value) if value is not None else None

            # Override is_existing_customer from contact card if available
            # (e.g. Service Titan tenants store authoritative customer data on the contact card)
            if call.contact_card_id:
                try:
                    contact_card = await self.contact_repo.get_by_id(call.contact_card_id)
                    if contact_card and contact_card.extra_metadata:
                        cc_is_customer = contact_card.extra_metadata.get("is_customer")
                        if cc_is_customer is not None:
                            logger.info(
                                f"Overriding is_existing_customer from contact card: "
                                f"Shunya={is_existing_customer}, ContactCard={cc_is_customer}",
                                call_id=str(call_id),
                            )
                            is_existing_customer = cc_is_customer
                except Exception as e:
                    logger.debug(f"Could not check contact card for is_customer override: {e}")

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
                # Scope
                scope=scope,
                # Raw data
                raw_analysis=analysis_data,  # Store complete raw data for reference (includes full objection objects)
            )

            # Upsert analysis
            analysis = await self.analysis_repo.upsert_by_call_id(call_id, call_analysis)
            logger.info("Call analysis processed", call_id=str(call_id), analysis_id=str(analysis.id))

            # Update call scope to match analysis scope
            if scope:
                call.scope = scope
                await self.call_repo.update(call_id, call)

            # Process pending actions from analysis
            await self._process_pending_actions(call, analysis_data, analysis)

            # Update dependent entities based on analysis
            await self._update_dependent_entities(call, analysis)

            # Extract coaching data into dedicated tables
            await self._extract_coaching_data(call, analysis, analysis_data)

            return analysis

        except Exception as e:
            logger.error(f"Error processing analysis: {e}", call_id=str(call_id))
            raise e

    async def _extract_coaching_data(
        self,
        call,
        analysis,
        analysis_data: dict,
    ) -> None:
        """Extract coaching issues, strengths, and objection details into dedicated tables."""
        try:
            from app.infrastructure.database.models.coaching import (
                CoachingIssueORM,
                CoachingStrengthORM,
                CallObjectionDetailORM,
            )

            company_id = call.company_id
            user_id = call.handled_by_user_id
            call_id = call.id
            analysis_id = analysis.id

            # Extract coaching issues from compliance.sop_compliance.coaching_issues
            compliance = analysis_data.get("compliance", {})
            sop_compliance = compliance.get("sop_compliance", {})

            coaching_issues = sop_compliance.get("coaching_issues", [])
            for issue_data in coaching_issues:
                if not isinstance(issue_data, dict):
                    continue
                issue_obj = CoachingIssueORM(
                    call_analysis_id=analysis_id,
                    call_id=call_id,
                    company_id=company_id,
                    user_id=user_id,
                    issue=issue_data.get("issue", ""),
                    severity=issue_data.get("severity", "medium"),
                    why_it_matters=issue_data.get("why_it_matters"),
                    how_to_fix=issue_data.get("how_to_fix"),
                    example_language=issue_data.get("example_language"),
                    transcript_evidence=issue_data.get("transcript_evidence"),
                    related_sop_metric=issue_data.get("related_sop_metric"),
                )
                self.session.add(issue_obj)

            # Extract coaching strengths from compliance.sop_compliance.coaching_strengths
            coaching_strengths = sop_compliance.get("coaching_strengths", [])
            for strength_data in coaching_strengths:
                if not isinstance(strength_data, dict):
                    continue
                strength_obj = CoachingStrengthORM(
                    call_analysis_id=analysis_id,
                    call_id=call_id,
                    company_id=company_id,
                    user_id=user_id,
                    behavior=strength_data.get("behavior", ""),
                    why_effective=strength_data.get("why_effective"),
                    transcript_evidence=strength_data.get("transcript_evidence"),
                    related_sop_metric=strength_data.get("related_sop_metric"),
                )
                self.session.add(strength_obj)

            # Extract objection details from objections.objections
            objections_section = analysis_data.get("objections", {})
            objections_list = []
            if isinstance(objections_section, dict):
                objections_list = objections_section.get("objections", [])
            elif isinstance(objections_section, list):
                objections_list = objections_section

            for obj_data in objections_list:
                if not isinstance(obj_data, dict):
                    continue
                obj_detail = CallObjectionDetailORM(
                    call_analysis_id=analysis_id,
                    call_id=call_id,
                    company_id=company_id,
                    user_id=user_id,
                    category_id=obj_data.get("category_id"),
                    category_text=obj_data.get("category_text", "Other"),
                    objection_text=obj_data.get("objection_text"),
                    overcome=obj_data.get("overcome", False),
                    severity=obj_data.get("severity"),
                    confidence_score=obj_data.get("confidence_score"),
                )
                self.session.add(obj_detail)

            await self.session.flush()
            logger.info(
                "Extracted coaching data",
                call_id=str(call_id),
                issues=len(coaching_issues),
                strengths=len(coaching_strengths),
                objections=len(objections_list),
            )
        except Exception as e:
            logger.warning(f"Failed to extract coaching data (non-fatal): {e}")

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

    def _map_to_pipeline_stage(
        self,
        lead_status: LeadStatus,
    ) -> Optional[PipelineStage]:
        """
        Map LeadStatus to PipelineStage.

        Args:
            lead_status: The lead status after call analysis

        Returns:
            Appropriate PipelineStage enum value or None
        """
        mapping = {
            LeadStatus.QUALIFIED_UNBOOKED: PipelineStage.QUALIFIED,
            LeadStatus.QUALIFIED_BOOKED: PipelineStage.BOOKED,
            LeadStatus.QUALIFIED_SERVICE_NOT_OFFERED: PipelineStage.SERVICE_NOT_OFFERED,
            LeadStatus.ABANDONED: PipelineStage.UNQUALIFIED,
            LeadStatus.CLOSED_WON: PipelineStage.WON,
            LeadStatus.CLOSED_LOST: PipelineStage.LOST,
        }
        return mapping.get(lead_status)

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

            # Fallback: build from contact card if analysis gave no address
            if not location_address and call.contact_card_id:
                try:
                    contact = await self.contact_repo.get_by_id(call.contact_card_id)
                    if contact:
                        parts = [contact.address, contact.city, contact.state, contact.postal_code]
                        location_address = ", ".join(p for p in parts if p) or None
                except Exception:
                    pass

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
                "assigned_rep_id": None,  # Sales rep assigned later via pipeline stage movement
                "interaction_id": call.id,
                "extra_metadata": {
                    "created_from_call": str(call.id),
                    "source": "call_analysis",
                },
            }

            existing = await self.appointment_repo.get_by_interaction_id(call.id)
            if existing:
                for key, value in appointment_data.items():
                    if key == "assigned_rep_id" and existing.assigned_rep_id is not None:
                        continue  # Don't overwrite an already-assigned sales rep
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

        Updates lead status, deal_status, and pipeline_stage based on
        qualification_status and booking_status from the analysis.
        Also creates/updates appointments when booking_status is 'booked'.
        """
        try:
            if not call.lead_id and not call.contact_card_id:
                logger.debug("No lead_id or contact_card_id on call, skipping dependent entity updates")
                return

            # Find the lead
            lead = None
            if call.lead_id:
                lead = await self.lead_repo.get_by_id(call.lead_id)
            if not lead and call.contact_card_id and call.company_id:
                lead = await self._find_existing_lead(call.contact_card_id, call.company_id)

            if not lead:
                logger.debug("No lead found for call, skipping dependent entity updates", call_id=str(call.id))
                return

            # Map to lead status and pipeline stage
            qualification_status = getattr(analysis, "qualification_status", None)
            booking_status = getattr(analysis, "booking_status", None)

            new_lead_status = self._map_to_lead_status(qualification_status, booking_status)
            new_deal_status = self._map_to_deal_status(booking_status)
            new_pipeline_stage = self._map_to_pipeline_stage(new_lead_status)

            # Update lead fields
            from sqlalchemy import select
            from app.infrastructure.database.models.lead import LeadORM

            result = await self.session.execute(
                select(LeadORM).where(LeadORM.id == lead.id)
            )
            lead_orm = result.scalar_one_or_none()
            if not lead_orm:
                return

            lead_orm.status = new_lead_status.value
            if new_deal_status:
                lead_orm.deal_status = new_deal_status.value
            if new_pipeline_stage:
                lead_orm.pipeline_stage = new_pipeline_stage.value

            await self.session.flush()

            logger.info(
                "Updated lead from call analysis",
                lead_id=str(lead.id),
                call_id=str(call.id),
                status=new_lead_status.value,
                pipeline_stage=new_pipeline_stage.value if new_pipeline_stage else None,
            )

            # Create/update appointment if booked
            if booking_status and booking_status.lower() == "booked":
                await self._upsert_appointment_from_call(call, analysis)

        except Exception as e:
            logger.error(f"Error updating dependent entities: {e}", call_id=str(call.id))
            traceback.print_exc()
            # Non-critical: do not re-raise

    async def _process_pending_actions(
        self,
        call: Any,
        analysis_data: Dict[str, Any],
        analysis: Any,
    ) -> None:
        """
        Create ActionItem rows from AI-generated action_items and
        PendingActionORM rows from AI-generated pending_actions
        extracted from the Shunya analysis payload.

        Reads from:
          analysis_data["summary"]["action_items"]    – explicit action items → ActionItemORM
          analysis_data["summary"]["pending_actions"] – pending tasks → PendingActionORM
        """
        try:
            from app.infrastructure.database.models.action_item import ActionItemORM
            from app.infrastructure.database.models.pending_action import PendingActionORM

            summary_section = analysis_data.get("summary", {})
            if not isinstance(summary_section, dict):
                return

            lead_id = getattr(call, "lead_id", None)
            company_id = getattr(call, "company_id", None)

            # 1) Store action_items as ActionItemORM rows
            action_texts: List[str] = []
            items = summary_section.get("action_items") or []
            if isinstance(items, list):
                action_texts.extend(str(i).strip() for i in items if i and str(i).strip())

            for text in action_texts:
                action_item = ActionItemORM(
                    company_id=company_id,
                    lead_id=lead_id,
                    call_id=call.id,
                    action_type="follow_up",
                    raw_text=text,
                    status="pending",
                    source="ai_analysis",
                )
                self.session.add(action_item)

            if action_texts:
                logger.info(
                    f"Created {len(action_texts)} action items from analysis",
                    call_id=str(call.id),
                )

            # 2) Store pending_actions as PendingActionORM rows
            pending_actions_list = summary_section.get("pending_actions") or []
            if isinstance(pending_actions_list, list):
                pa_count = 0
                for pa in pending_actions_list:
                    if not isinstance(pa, dict):
                        continue

                    # Parse due_at from ISO string if present
                    due_at_val = None
                    if pa.get("due_at"):
                        try:
                            from datetime import datetime as dt_cls
                            due_at_str = pa["due_at"]
                            # Handle both timezone-aware and naive ISO strings
                            due_at_val = dt_cls.fromisoformat(due_at_str.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse due_at: {pa.get('due_at')}")

                    # Use action_item text if available, fall back to raw_text
                    raw_text = pa.get("action_item") or pa.get("raw_text") or ""

                    pending_action = PendingActionORM(
                        company_id=company_id,
                        lead_id=lead_id,
                        call_id=call.id,
                        action_type=pa.get("type") or "follow_up",
                        raw_text=raw_text,
                        status="pending",
                        due_at=due_at_val,
                        priority=None,
                        owner_id=None,
                        source="ai_analysis",
                        extra_metadata={
                            k: v for k, v in {
                                "confidence": pa.get("confidence"),
                                "contact_method": pa.get("contact_method"),
                                "category": pa.get("category"),
                                "owner_role": pa.get("owner"),
                                "original_raw_text": pa.get("raw_text"),
                            }.items() if v is not None
                        } or None,
                    )
                    self.session.add(pending_action)
                    pa_count += 1

                if pa_count:
                    logger.info(
                        f"Created {pa_count} pending actions from analysis",
                        call_id=str(call.id),
                    )

            await self.session.flush()

        except Exception as e:
            logger.error(f"Error processing pending actions: {e}", call_id=str(call.id))
            traceback.print_exc()
            # Non-critical: do not re-raise

    async def get_call_logs(
        self,
        company_id: UUID,
        search: Optional[str] = None,
        csr_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        booking_filter: Optional[str] = None,
        existing_customer: Optional[bool] = None,
        quick_filter: Optional[str] = None,
        scope_filter: Optional[str] = None,
        objection_filter: Optional[str] = None,
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

            # Apply scope filter: in_scope (default), out_scope, or all
            if scope_filter and scope_filter.lower() == "out_scope":
                query = query.where(CallORM.scope == "out")
            elif scope_filter and scope_filter.lower() == "all":
                pass  # No scope filter — return all calls
            else:
                # Default: in_scope (includes None for legacy calls)
                query = query.where(
                    or_(CallORM.scope == "in", CallORM.scope.is_(None))
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
                    query = query.where(func.lower(CallAnalysisORM.qualification_status) == "hot")
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
                elif quick_filter_lower == "service_not_offered":
                    query = query.where(
                        func.lower(CallAnalysisORM.booking_status) == "service_not_offered"
                    )

            # Objection filter: check if the given value exists in the objections array
            # Supports both snake_case enum values (e.g. "service_fee_concerns") and
            # legacy human-readable strings (e.g. "Service Fee Concerns") via case-insensitive match
            if objection_filter:
                from sqlalchemy import exists as sa_exists, literal, column as sa_column
                query = query.where(
                    sa_exists(
                        select(literal(1))
                        .select_from(func.unnest(CallAnalysisORM.objections).alias("obj"))
                        .where(func.lower(sa_column("obj")) == objection_filter.strip().lower())
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

            # Calculate summary statistics from all calls for this company
            # Qualified statuses: hot, cold, warm, qualified
            summary_base = CallORM.company_id == company_id
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

            # Apply same scope filter to summary
            if scope_filter and scope_filter.lower() == "out_scope":
                summary_query = summary_query.where(CallORM.scope == "out")
            elif scope_filter and scope_filter.lower() == "all":
                pass  # No scope filter
            else:
                summary_query = summary_query.where(
                    or_(CallORM.scope == "in", CallORM.scope.is_(None))
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
                # Both sop_compliance_score and sentiment_score are stored as 0-1 decimals from Shunya
                score = None
                if analysis:
                    if analysis.sop_compliance_score is not None:
                        raw = analysis.sop_compliance_score
                        score = round(raw * 100, 1) if raw <= 1.0 else round(raw, 1)
                    elif analysis.sentiment_score is not None:
                        raw = analysis.sentiment_score
                        score = round(raw * 100, 1) if raw <= 1.0 else round(raw, 1)

                # Get objections
                objections = None
                if analysis and analysis.objections:
                    # Classify objections before displaying
                    from app.domain.objection_classifier import ObjectionClassifier
                    classified = ObjectionClassifier.classify_and_deduplicate(analysis.objections)

                    # Join objections with comma
                    objections = ", ".join(classified[:3])  # Limit to first 3
                    if len(classified) > 3:
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

                # Format call received date as UTC ISO 8601 timestamp
                call_received = None
                if call.created_at:
                    dt = call.created_at
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    call_received = dt.isoformat()

                # Get dropdown fields
                audio_url = call.audio_url
                transcript = call.transcript
                call_summary = analysis.summary if analysis else None
                key_items = list(analysis.key_points) if (analysis and analysis.key_points) else None
                action_items = list(analysis.action_items) if (analysis and analysis.action_items) else None

                booking_status_raw = (analysis.booking_status or "").strip() if analysis else None
                if not booking_status_raw:
                    booking_status_raw = None
                # Determine if service was offered: false when booking_status explicitly indicates service not offered
                is_service_offered = True
                if booking_status_raw:
                    bs_norm = booking_status_raw.lower().replace("_", " ").replace("-", " ").strip()
                    if bs_norm == "service not offered":
                        is_service_offered = False

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
                    "is_service_offered": is_service_offered,
                    "is_existing_customer": bool(analysis.is_existing_customer) if analysis else None,
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

    async def get_recording_analysis(self, call_id: UUID) -> Optional[RecordingAnalysisResponse]:
        """Get comprehensive recording analysis for post-meeting insights."""
        try:
            from sqlalchemy import select as sa_select
            from app.infrastructure.database.models.analysis import CallAnalysisORM as AnalysisORM

            # Use direct ORM query (same pattern as get_call_logs) to avoid domain conversion issues
            result = await self.session.execute(
                sa_select(AnalysisORM).where(AnalysisORM.call_id == call_id)
            )
            a = result.scalar_one_or_none()
            if not a:
                return None

            # 1. Summary section — use pending_actions JSON first, fall back to action_items array
            pending_actions_structured = []
            if a.pending_actions:
                actions_list = a.pending_actions if isinstance(a.pending_actions, list) else []
                for action in actions_list:
                    if isinstance(action, dict):
                        pending_actions_structured.append(PendingActionDetail(
                            type=action.get("type", "unknown"),
                            owner=action.get("owner", "unknown"),
                            raw_text=action.get("raw_text", ""),
                            due_at=action.get("due_at"),
                            confidence=action.get("confidence"),
                            contact_method=action.get("contact_method"),
                        ))
            if not pending_actions_structured and a.action_items:
                for item_text in (a.action_items or []):
                    pending_actions_structured.append(PendingActionDetail(
                        type="follow_up",
                        owner="customer_rep",
                        raw_text=str(item_text),
                    ))

            summary = RecordingSummary(
                summary=a.summary or "",
                key_points=list(a.key_points) if a.key_points else [],
                pending_actions=pending_actions_structured,
                sentiment_score=a.sentiment_score,
            )

            # 2. Objections section
            objection_details = []
            if a.objections and a.objection_texts:
                for idx, objection in enumerate(a.objections):
                    obj_text = a.objection_texts[idx] if idx < len(a.objection_texts) else ""
                    obj_str = str(objection)
                    objection_details.append(ObjectionDetail(
                        category_id=idx + 1,
                        category_text=obj_str,
                        objection_text=obj_text or obj_str,
                        overcome=True,
                        severity="medium",
                        confidence_score=0.85,
                        response_suggestions=[],
                    ))

            objections = RecordingObjections(
                objections=objection_details,
                total_count=a.objections_total_count or len(objection_details),
            )

            # 3. Compliance section
            stages_detail = {}
            for stage in (a.sop_stages_completed or []):
                stages_detail[stage.lower().replace(" ", "_")] = ComplianceStageDetail(score=0.95, issues=[])
            for stage in (a.sop_stages_missed or []):
                stages_detail[stage.lower().replace(" ", "_")] = ComplianceStageDetail(
                    score=0.0, issues=[f"Missed: {stage}"]
                )

            compliance = RecordingCompliance(
                score=a.sop_compliance_score or 0.0,
                stages=stages_detail,
                positive_behaviors=list(a.sop_compliance_positive_behaviors) if a.sop_compliance_positive_behaviors else [],
                issues=list(a.sop_compliance_issues) if a.sop_compliance_issues else [],
            )

            # 4. Qualification section
            qualification = RecordingQualification(
                overall_score=a.qualification_overall_score or 0.0,
                bant_scores={
                    "need": a.bant_need_score or 0.0,
                    "budget": a.bant_budget_score or 0.0,
                    "authority": a.bant_authority_score or 0.0,
                    "timeline": a.bant_timeline_score or 0.0,
                },
                qualification_status=a.qualification_status or "unqualified",
            )

            # 5. Lead score
            total_score = int((a.qualification_overall_score or 0.0) * 100)
            lead_band = "hot" if total_score >= 80 else "warm" if total_score >= 60 else "cold" if total_score >= 40 else "unqualified"

            return RecordingAnalysisResponse(
                call_id=str(call_id),
                status=str(a.status) if a.status else "completed",
                summary=summary,
                objections=objections,
                compliance=compliance,
                qualification=qualification,
                lead_score=RecordingLeadScore(total_score=total_score, lead_band=lead_band),
            )

        except Exception as e:
            logger.error(f"Error getting recording analysis: {e}")
            traceback.print_exc()
            return None

