"""
Call service.

Orchestrates call-related business logic:
- Call ingestion from webhooks
- Call analysis pipeline
- Transcript processing
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.analysis import CallAnalysis
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.tasks.analysis import analyze_call_task

logger = get_logger(__name__)


class CallService:
    """Service for call-related operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
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
            
            # Submit transcription job to Shoonya
            if self.shoonya.is_available():
                try:
                    result = await self.shoonya.transcribe_audio(
                        company_id=str(call.company_id),
                        audio_url=call.audio_url,
                        call_id=int(call.id),
                        call_type=call.call_type.value if call.call_type else "csr_call",
                    )
                    logger.info(
                        "Transcription job submitted",
                        call_id=str(call_id),
                        job_id=result.get("job_id"),
                    )
                except Exception as e:
                    logger.error("Failed to submit transcription", call_id=str(call_id), error=str(e))
                    raise
        except Exception as e:
            logger.error(f"Error triggering analysis: {e}")
            raise e

