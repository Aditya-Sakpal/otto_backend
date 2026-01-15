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

from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.analysis import CallAnalysis
from app.domain.models.pending_action import PendingAction
from app.domain.enums import AnalysisStatus, ObjectionType, SOPStage, PendingActionStatus
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.tasks.analysis import analyze_call_task

logger = get_logger(__name__)


class CallService:
    """Service for call-related operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
        self.analysis_repo = CallAnalysisRepository(session)
        self.pending_action_repo = PendingActionRepository(session)
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
            traceback.print_exc()
            raise
    
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
            traceback.print_exc()
            raise
    
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

