"""
Call service.

Orchestrates call-related business logic:
- Call ingestion from webhooks
- Call analysis pipeline
- Transcript processing
"""
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.analysis import CallAnalysis
from app.domain.models.pending_action import PendingAction
from app.domain.enums import AnalysisStatus, ObjectionType, SOPStage, PendingActionStatus
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.tasks.analysis import analyze_call_task
from app.core.s3 import get_s3_service
from app.domain.users.repository import UserRepository

logger = get_logger(__name__)


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
            # Create call record
            call = Call(
                company_id=company_id,
                phone_number=phone_number,
                audio_url=audio_url,
                call_type=call_type,
                missed_call=missed_call,
            )

            call = await self.call_repo.create(call)
            logger.info("Call ingested", call_id=str(call.id), company_id=str(company_id))

            # Trigger analysis if audio URL is available
            if audio_url and not missed_call:
                # TODO: Use Celery or BackgroundTasks for async execution
                # For now, call directly (will be async in production)
                await analyze_call_task(str(call.id))

            return call
        except Exception as e:
            logger.error(f"Error ingesting call: {e}")
            raise e

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
                    result = await self.shoonya.process_call(
                        call_id=str(call.id),
                        company_id=str(call.company_id),
                        audio_url=call.audio_url,
                        phone_number=call.phone_number,
                        duration=call.duration_seconds or 0,
                        call_date=call.created_at.isoformat() if call.created_at else datetime.utcnow().isoformat(),
                        webhook_url=f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete",
                        metadata={
                            "call_type": call.call_type.value if call.call_type else "csr_call",
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
        Process call analysis data from Shoonya webhook.

        Args:
            call_id: Call ID
            analysis_data: Analysis data from Shoonya
            transcript: Optional transcript text

        Returns:
            Created or updated CallAnalysis
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

            # Parse analysis data from Shoonya
            # Expected format from Shoonya (adjust based on actual format):
            # {
            #   "qualification_status": "...",
            #   "booking_status": "...",
            #   "objections": [...],
            #   "objection_texts": [...],
            #   "sop_stages_completed": [...],
            #   "sop_stages_missed": [...],
            #   "sop_compliance_score": 0.85,
            #   "sentiment_score": 0.5,
            #   "summary": "...",
            #   "key_points": [...],
            #   ...
            # }

            # Extract and normalize data
            qualification_status = analysis_data.get("qualification_status")
            booking_status = analysis_data.get("booking_status")

            # Parse objections (convert strings to enum if needed)
            objections_raw = analysis_data.get("objections", [])
            objections = []
            for obj in objections_raw:
                if isinstance(obj, str):
                    try:
                        objections.append(ObjectionType(obj.lower()))
                    except ValueError:
                        logger.warning(f"Unknown objection type: {obj}")
                else:
                    objections.append(obj)

            objection_texts = analysis_data.get("objection_texts", [])

            # Parse SOP stages
            sop_completed_raw = analysis_data.get("sop_stages_completed", [])
            sop_completed = []
            for stage in sop_completed_raw:
                if isinstance(stage, str):
                    try:
                        sop_completed.append(SOPStage(stage.lower()))
                    except ValueError:
                        logger.warning(f"Unknown SOP stage: {stage}")
                else:
                    sop_completed.append(stage)

            sop_missed_raw = analysis_data.get("sop_stages_missed", [])
            sop_missed = []
            for stage in sop_missed_raw:
                if isinstance(stage, str):
                    try:
                        sop_missed.append(SOPStage(stage.lower()))
                    except ValueError:
                        logger.warning(f"Unknown SOP stage: {stage}")
                else:
                    sop_missed.append(stage)

            sop_compliance_score = analysis_data.get("sop_compliance_score")
            if sop_compliance_score is not None:
                sop_compliance_score = float(sop_compliance_score)

            sentiment_score = analysis_data.get("sentiment_score")
            if sentiment_score is not None:
                sentiment_score = float(sentiment_score)

            summary = analysis_data.get("summary")
            key_points = analysis_data.get("key_points", [])

            # Create CallAnalysis domain model
            call_analysis = CallAnalysis(
                call_id=call_id,
                company_id=call.company_id,
                status=AnalysisStatus.COMPLETED,
                qualification_status=qualification_status,
                booking_status=booking_status,
                objections=objections,
                objection_texts=objection_texts,
                sop_stages_completed=sop_completed,
                sop_stages_missed=sop_missed,
                sop_compliance_score=sop_compliance_score,
                sentiment_score=sentiment_score,
                summary=summary,
                key_points=key_points,
                raw_analysis=analysis_data,  # Store raw data for reference
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

    async def _update_dependent_entities(
        self,
        call: Call,
        analysis: CallAnalysis,
    ) -> None:
        """
        Update dependent entities based on call analysis.

        Updates:
        - Lead status based on qualification_status
        - Appointment status based on booking_status
        - Contact card metadata
        """
        try:
            # Update lead if exists
            if call.lead_id:
                # TODO: Implement LeadRepository and update lead status
                # based on qualification_status and booking_status
                # Example logic:
                # if analysis.qualification_status == "qualified" and analysis.booking_status == "booked":
                #     lead.status = LeadStatus.QUALIFIED_BOOKED
                # elif analysis.qualification_status == "qualified":
                #     lead.status = LeadStatus.QUALIFIED_UNBOOKED
                logger.info(
                    "Lead update needed",
                    lead_id=str(call.lead_id),
                    qualification_status=analysis.qualification_status,
                    booking_status=analysis.booking_status,
                )

            # Update appointment if exists and booking_status indicates one
            if analysis.booking_status and analysis.booking_status.lower() in ["booked", "confirmed"]:
                # TODO: Implement AppointmentRepository and create/update appointment
                # based on booking_status and analysis data
                logger.info(
                    "Appointment update needed",
                    call_id=str(call.id),
                    booking_status=analysis.booking_status,
                )

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
            analysis_data: Raw analysis data from Shoonya
            analysis: The created/updated analysis
        """
        try:
            # Extract pending_actions from analysis_data
            # Expected format: list of dicts with action_type, raw_text, due_at, priority, etc.
            pending_actions_data = analysis_data.get("pending_actions", [])

            if not pending_actions_data:
                return

            for action_data in pending_actions_data:
                try:
                    # Handle both dict and string formats
                    if isinstance(action_data, str):
                        # Legacy format: simple string
                        action_type = action_data
                        raw_text = action_data
                        due_at = None
                        priority = None
                    else:
                        # New format: dict with fields
                        action_type = action_data.get("action_type") or action_data.get("action") or action_data.get("type") or ""
                        raw_text = action_data.get("raw_text") or action_data.get("action") or action_type
                        due_at_str = action_data.get("due_at")
                        priority = action_data.get("priority")

                        # Parse due_at if provided (should be UTC)
                        due_at = None
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
                        owner_id=call.handled_by_user_id,  # Use call owner or determine from action type
                        source="shunya",
                        extra_metadata={
                            "from_analysis": str(analysis.id),
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
                count=len(pending_actions_data),
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
        quick_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
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
            if status_filter and status_filter.lower() != "all":
                if status_filter.lower() == "qualified":
                    query = query.where(CallAnalysisORM.qualification_status == "qualified")
                elif status_filter.lower() == "unqualified":
                    query = query.where(
                        or_(
                            CallAnalysisORM.qualification_status != "qualified",
                            CallAnalysisORM.qualification_status.is_(None)
                        )
                    )

            # Booking filter
            if booking_filter and booking_filter.lower() != "all":
                if booking_filter.lower() == "booked":
                    query = query.where(CallAnalysisORM.booking_status == "booked")
                elif booking_filter.lower() == "unbooked":
                    query = query.where(
                        or_(
                            CallAnalysisORM.booking_status != "booked",
                            CallAnalysisORM.booking_status.is_(None)
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
                            CallAnalysisORM.qualification_status == "qualified",
                            or_(
                                CallAnalysisORM.booking_status != "booked",
                                CallAnalysisORM.booking_status.is_(None)
                            )
                        )
                    )
                elif quick_filter_lower == "qualified_booked":
                    query = query.where(
                        and_(
                            CallAnalysisORM.qualification_status == "qualified",
                            CallAnalysisORM.booking_status == "booked"
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

            # Calculate summary statistics (from all calls, not just filtered)
            summary_query = select(
                func.count(CallORM.id).label('total_calls'),
                func.sum(
                    case(
                        (CallAnalysisORM.qualification_status == "qualified", 1),
                        else_=0
                    )
                ).label('qualified'),
                func.sum(
                    case(
                        (CallAnalysisORM.booking_status == "booked", 1),
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
                CallORM.company_id == company_id
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
                is_qualified = analysis and analysis.qualification_status == "qualified" if analysis else False
                is_booked = analysis and analysis.booking_status == "booked" if analysis else False

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

                calls.append({
                    "call_id": str(call.id),
                    "call_received": call_received,
                    "duration": duration_str,
                    "csr_name": csr_name,
                    "customer_name": customer_name,
                    "phone_number": formatted_phone,
                    "is_qualified": is_qualified,
                    "is_booked": is_booked,
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
