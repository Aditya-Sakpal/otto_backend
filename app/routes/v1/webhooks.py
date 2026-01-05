"""
Webhook routes.

Handles incoming webhooks from:
- Telephony providers (CallRail, Twilio)
- Shoonya (job completions)

Note: These endpoints are public (no JWT required) as they are called by external services.
For production, implement webhook signature verification to ensure requests are authentic.
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.services.call_service import CallService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/telephony/call-complete")
async def call_complete_webhook(
    request: Request,
    db: DbSession,
):
    """
    Handle call completion webhook from telephony provider.
    
    Expected payload:
    {
        "phone_number": "+1234567890",
        "audio_url": "https://...",
        "call_type": "csr_call",
        "missed_call": false,
        "duration_seconds": 120,
        ...
    }
    """
    try:
        payload = await request.json()
        logger.info("Call complete webhook received", payload=payload)
        
        # Extract company_id from payload or headers
        company_id = payload.get("company_id") or request.headers.get("X-Company-Id")
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_id required",
            )
        
        # Ingest call
        service = CallService(db)
        call = await service.ingest_call(
            company_id=UUID(company_id),
            phone_number=payload.get("phone_number"),
            audio_url=payload.get("audio_url"),
            call_type=payload.get("call_type"),
            missed_call=payload.get("missed_call", False),
        )
        
        return {"status": "success", "call_id": str(call.id)}
    
    except Exception as e:
        logger.error(f"Error processing call webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/shoonya/job-complete")
async def shoonya_job_complete_webhook(
    request: Request,
    db: DbSession,
):
    """
    Handle job completion webhook from Shoonya.
    
    Expected payload from Shoonya:
    {
        "shunya_job_id": "job_123",
        "status": "completed",
        "call_id": "uuid-string" or int,
        "company_id": "uuid-string",
        "result": {
            "transcript": "...",
            "analysis": {
                "qualification_status": "...",
                "booking_status": "...",
                "objections": [...],
                "objection_texts": [...],
                "sop_stages_completed": [...],
                "sop_stages_missed": [...],
                "sop_compliance_score": 0.85,
                "sentiment_score": 0.5,
                "summary": "...",
                "key_points": [...],
                ...
            }
        }
    }
    """
    try:
        payload = await request.json()
        logger.info("Shoonya job complete webhook received", payload=payload)
        
        # Extract required fields
        job_status = payload.get("status")
        if job_status != "completed":
            logger.warning(
                "Job not completed, ignoring",
                status=job_status,
                job_id=payload.get("shunya_job_id"),
            )
            return {"status": "ignored", "reason": f"Job status is {job_status}"}
        
        # Extract call_id (can be UUID string or int)
        call_id_raw = payload.get("call_id")
        if not call_id_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="call_id required in payload",
            )
        
        # Convert to UUID
        try:
            if isinstance(call_id_raw, int):
                # If Shoonya sends int, we need to look it up or handle differently
                # For now, assume it's a UUID string
                raise ValueError("call_id must be UUID string, not int")
            call_id = UUID(call_id_raw)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid call_id format: {call_id_raw}",
            )
        
        # Extract company_id
        company_id = payload.get("company_id") or request.headers.get("X-Company-Id")
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_id required",
            )
        
        # Extract result data
        result = payload.get("result", {})
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="result required in payload",
            )
        
        # Extract transcript and analysis
        transcript = result.get("transcript")
        analysis_data = result.get("analysis", {})
        
        if not analysis_data:
            logger.warning(
                "No analysis data in result",
                call_id=str(call_id),
                job_id=payload.get("shunya_job_id"),
            )
            # Still process if we have transcript
            if transcript:
                service = CallService(db)
                call = await service.call_repo.get_by_id(call_id)
                if call:
                    call.transcript = transcript
                    await service.call_repo.update(call_id, call)
                    logger.info("Transcript updated", call_id=str(call_id))
                return {"status": "success", "message": "Transcript updated, no analysis data"}
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either transcript or analysis required in result",
                )
        
        # Process analysis
        service = CallService(db)
        analysis = await service.process_analysis(
            call_id=call_id,
            analysis_data=analysis_data,
            transcript=transcript,
        )
        
        logger.info(
            "Shoonya webhook processed successfully",
            call_id=str(call_id),
            analysis_id=str(analysis.id),
            job_id=payload.get("shunya_job_id"),
        )
        
        return {
            "status": "success",
            "call_id": str(call_id),
            "analysis_id": str(analysis.id),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Shoonya webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

