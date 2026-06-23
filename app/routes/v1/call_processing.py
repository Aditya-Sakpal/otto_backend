"""
Call Processing API routes.

Handles Shunya call processing: transcription, analysis, summarization.
"""
import traceback
from typing import Optional
from uuid import UUID
from datetime import datetime
from dateutil import parser as date_parser

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.core.logging import get_logger
from app.infrastructure.database.models.call_processing_job import CallProcessingJobORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/call-processing", tags=["call-processing"])
logger = get_logger(__name__)

RESPONSES = {
    403: {"description": "Forbidden"},
    404: {"description": "Resource or job not found"},
    500: {"description": "Internal server error"},
    503: {"description": "Shunya service not available"},
}


# Request/Response Models
class ProcessCallRequest(BaseModel):
    """Request to process a call via AI analysis (transcription, summarization, objection detection, SOP compliance)."""
    call_id: str = Field(..., description="Call UUID")
    company_id: str = Field(..., description="Company UUID")
    audio_url: str = Field(..., description="Public URL to audio file (mp3, wav, etc.)")
    phone_number: str = Field(..., description="Phone number of the caller")
    duration: int = Field(..., description="Call duration in seconds")
    call_date: str = Field(..., description="ISO 8601 datetime string (e.g. '2026-03-20T10:30:00Z')")
    metadata: dict = Field(default_factory=dict, description="Additional metadata (e.g. call_type, lead_id)")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for completion notification (defaults to internal webhook)")
    options: dict = Field(
        default_factory=dict,
        description="Processing options: skip_rag_indexing (bool), skip_summary_generation (bool), priority ('normal'|'high')"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "call_id": "ede64a3e-cb73-44c4-94cc-35af4a95b0ac",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "audio_url": "https://example.com",
                "phone_number": "+15551234567",
                "duration": 180,
                "call_date": "2026-03-20T10:30:00Z",
                "metadata": {"call_type": "csr_call", "lead_id": "b1c2d3e4-f5a6-7890-abcd-ef1234567890"},
                "options": {"skip_rag_indexing": False, "priority": "normal"},
            }
        }
    }


class ProcessCallResponse(BaseModel):
    """Response from call processing submission."""
    job_id: str
    call_id: str
    status: str
    message: str
    estimated_completion_time: Optional[datetime] = None
    status_url: str
    created_at: datetime


@router.post(
    "/process",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProcessCallResponse,
    responses=RESPONSES,
)
async def process_call(
    body: ProcessCallRequest,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
) -> ProcessCallResponse:
    """Submit a call for AI processing."""
    try:
        logger.info(f"Processing call: {body}")
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        from app.core.config import settings
        webhook_url = f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete"
        
        result = await shoonya.process_call(
            call_id=body.call_id,
            company_id=body.company_id,
            audio_url=body.audio_url,
            phone_number=body.phone_number,
            duration=body.duration,
            call_date=body.call_date,
            metadata=body.metadata,
            webhook_url=webhook_url,
            options=body.options,
        )
        
        try:
            job = CallProcessingJobORM(
                company_id=UUID(body.company_id),
                call_id=UUID(body.call_id),
                shunya_job_id=result["job_id"],
                status=result.get("status", "queued"),
                skip_rag_indexing=body.options.get("skip_rag_indexing", False),
                skip_summary_generation=body.options.get("skip_summary_generation", False),
                priority=body.options.get("priority", "normal"),
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
        except Exception as db_error:
            logger.warning(f"Could not store job locally: {db_error}")
            await db.rollback()
        
        return ProcessCallResponse(
            job_id=result["job_id"],
            call_id=body.call_id,
            status=result.get("status", "queued"),
            message=result.get("message", "Call processing queued"),
            estimated_completion_time=date_parser.parse(result["estimated_completion_time"]) if isinstance(result.get("estimated_completion_time"), str) else result.get("estimated_completion_time"),
            status_url=f"/api/v1/call-processing/status/{result['job_id']}",
            created_at=date_parser.parse(result["created_at"]) if isinstance(result.get("created_at"), str) else (result.get("created_at") or datetime.utcnow()),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing call: {e}")
        traceback.print_exc()
        if "RetryError" in str(type(e).__name__) or "RetryError" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service temporarily unavailable",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process call: {str(e)}",
        )


@router.get("/status/{job_id}", responses=RESPONSES)
async def get_call_processing_status(
    job_id: str,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """Get call processing job status."""
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        # --- BUG #29 FIX: Intercept missing/unknown job status triggers ---
        try:
            result = await shoonya.get_call_processing_status(job_id)
            if not result or "error" in str(result).lower() or result.get("status") is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job sequence reference '{job_id}' not found in the service system context"
                )
        except HTTPException:
            raise
        except Exception as shunya_err:
            logger.warning(f"Service lookup failed for ID {job_id}: {shunya_err}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job sequence reference '{job_id}' not found in the system context"
            )
        # ---------------------------------------------------------------------------------
        
        job_query = select(CallProcessingJobORM).where(
            CallProcessingJobORM.shunya_job_id == job_id
        )
        job_result = await db.execute(job_query)
        job = job_result.scalar_one_or_none()
        
        if job:
            job.status = result.get("status", job.status) if result else job.status
            progress = result.get("progress") if result else None
            if progress:
                job.progress_percent = progress.get("percent")
                job.current_step = progress.get("current_step")
                job.steps_completed = progress.get("steps_completed", [])
                job.steps_remaining = progress.get("steps_remaining", [])
                job.steps_failed = progress.get("steps_failed", [])
            
            started_at_str = result.get("started_at") if result else None
            job.started_at = date_parser.parse(started_at_str) if started_at_str and isinstance(started_at_str, str) else (started_at_str if started_at_str else None)
            
            completed_at_str = result.get("completed_at") if result else None
            job.completed_at = date_parser.parse(completed_at_str) if completed_at_str and isinstance(completed_at_str, str) else (completed_at_str if completed_at_str else None)
            
            failed_at_str = result.get("failed_at") if result else None
            job.failed_at = date_parser.parse(failed_at_str) if failed_at_str and isinstance(failed_at_str, str) else (failed_at_str if failed_at_str else None)
            
            job.duration_seconds = result.get("duration_seconds") if result else None
            
            estimated_completion_str = result.get("estimated_completion") if result else None
            job.estimated_completion = date_parser.parse(estimated_completion_str) if estimated_completion_str and isinstance(estimated_completion_str, str) else (estimated_completion_str if estimated_completion_str else None)
            results = result.get("results") if result else None
            if results:
                job.summary_url = results.get("summary_url")
                job.chunks_url = results.get("chunks_url")
                job.transcript_url = results.get("transcript_url")
            job.job_metadata = result.get("metadata") if result else None
            job.error = result.get("error") if result else None
            job.retry_available = result.get("retry_available", False) if result else False
            
            await db.commit()
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call processing status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )
    finally:
        logger.info(f"Finished status lookup sequence for job: {job_id}")