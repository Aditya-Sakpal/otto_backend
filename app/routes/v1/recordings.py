"""
Recordings API routes.

Handles recording initiation for mobile uploads.
"""
import traceback
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from app.domain.enums import UserRole, CallStatus
from app.domain.users.models import User
from app.domain.models.call import Call
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.services.call_service import CallService

router = APIRouter()
logger = get_logger(__name__)


class RecordingInitiateRequest(BaseModel):
    """Request to initiate a recording upload."""
    appointment_id: UUID = Field(..., description="Appointment ID to associate recording with")


class RecordingInitiateResponse(BaseModel):
    """Response with pre-signed URL for upload."""
    call_id: UUID = Field(..., description="Created call ID")
    upload_url: str = Field(..., description="Pre-signed S3 URL for uploading audio")
    s3_key: str = Field(..., description="S3 key where the file should be uploaded")


@router.post("/initiate", response_model=RecordingInitiateResponse, status_code=status.HTTP_201_CREATED)
async def initiate_recording(
    request: RecordingInitiateRequest,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> RecordingInitiateResponse:
    """
    Initiate a recording upload for an appointment.

    This endpoint:
    1. Creates a Call record with status="pending" and interaction_type="meeting"
    2. Updates Appointment.interaction_id with the new Call ID
    3. Returns a pre-signed S3 URL for the mobile app to upload the audio file

    Access: Any authenticated user
    """
    try:
        appointment_repo = AppointmentRepository(db)
        call_repo = CallRepository(db)

        # Get the appointment
        appointment = await appointment_repo.get_by_id(request.appointment_id)
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        # Check if appointment already has an interaction_id
        if appointment.interaction_id:
            logger.warning(
                f"Appointment {request.appointment_id} already has interaction_id {appointment.interaction_id}"
            )
            # Return existing call info if it exists
            existing_call = await call_repo.get_by_id(appointment.interaction_id)
            if existing_call:
                # Generate a new pre-signed URL if needed
                s3_service = get_s3_service()
                if not s3_service:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="S3 service not available",
                    )

                # Generate S3 key for the recording
                s3_key = s3_service.generate_s3_key(
                    prefix="recordings",
                    filename=f"appointment_{request.appointment_id}",
                    extension="wav"
                )

                upload_url = s3_service.generate_presigned_url(
                    s3_key=s3_key,
                    content_type="audio/x-wav",
                    bucket_type="audio",
                )

                return RecordingInitiateResponse(
                    call_id=existing_call.id,
                    upload_url=upload_url,
                    s3_key=s3_key,
                )

        # Create a new Call record
        call = Call(
            company_id=appointment.company_id,
            contact_card_id=appointment.contact_card_id,
            lead_id=appointment.lead_id,
            phone_number="",  # Not applicable for meeting recordings
            interaction_type="meeting",
            status=CallStatus.PENDING.value,
            missed_call=False,
        )

        call = await call_repo.create(call)
        logger.info(f"Created call record {call.id} for appointment {request.appointment_id}")

        # Update appointment with interaction_id
        appointment.interaction_id = call.id
        appointment.mark_updated()
        await appointment_repo.update(request.appointment_id, appointment)
        await db.commit()

        # Get S3 service and generate pre-signed URL
        s3_service = get_s3_service()
        if not s3_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 service not available",
            )

        # Generate S3 key for the recording
        s3_key = s3_service.generate_s3_key(
            prefix="recordings",
            filename=f"appointment_{request.appointment_id}_call_{call.id}",
            extension="wav"
        )

        upload_url = s3_service.generate_presigned_url(
            s3_key=s3_key,
            content_type="audio/x-wav",
            bucket_type="audio",
        )

        logger.info(
            f"Generated pre-signed URL for appointment {request.appointment_id}, call {call.id}"
        )

        return RecordingInitiateResponse(
            call_id=call.id,
            upload_url=upload_url,
            s3_key=s3_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating recording: {e}")
        traceback.print_exc()
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
        
class RecordingCompleteRequest(BaseModel):
    """Request to complete recording upload."""
    call_id: UUID = Field(..., description="Call ID from initiate response")
    s3_key: str = Field(..., description="S3 key where the file was uploaded")


class RecordingCompleteResponse(BaseModel):
    """Response after recording upload completion."""
    call_id: UUID = Field(..., description="Call ID")
    status: str = Field(..., description="Call status")
    processing_job_id: Optional[str] = Field(None, description="Shunya job ID if processing was triggered")


@router.post("/complete", response_model=RecordingCompleteResponse)
async def complete_recording(
    request: RecordingCompleteRequest,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> RecordingCompleteResponse:
    """
    Complete recording upload and trigger processing.

    This endpoint:
    1. Updates Call with audio_url (from S3 key)
    2. Updates Call status to "processing"
    3. Triggers Shunya processing

    Access: Any authenticated user
    """
    try:
        call_repo = CallRepository(db)
        call_service = CallService(db)

        # Get the call
        call = await call_repo.get_by_id(request.call_id)
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        # Generate S3 URL from key
        s3_service = get_s3_service()
        if not s3_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 service not available",
            )

        audio_url = s3_service.get_public_url(request.s3_key, bucket_type="audio")

        # Update call with audio_url
        call.audio_url = audio_url
        await call_repo.update(request.call_id, call)
        await db.commit()

        logger.info(
            f"Recording upload completed for call {request.call_id}, triggering processing"
        )

        # Trigger Shunya processing
        processing_job_id = None
        shoonya = get_shoonya_client()
        if shoonya.is_available():
            try:
                from datetime import datetime
                from app.core.config import settings
                
                # Construct webhook URL for Shunya to notify us when processing completes
                webhook_url = f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete"
                
                result = await shoonya.process_call(
                    call_id=str(call.id),
                    company_id=str(call.company_id),
                    audio_url=audio_url,
                    phone_number=call.phone_number or "",
                    duration=call.duration_seconds or 0,
                    call_date=call.created_at.isoformat() if call.created_at else datetime.utcnow().isoformat(),
                    metadata={
                        "interaction_type": call.interaction_type or "meeting",
                        "appointment_id": str(call.lead_id) if call.lead_id else None,
                        **(call.extra_metadata or {}),
                    },
                    webhook_url=webhook_url,
                )
                processing_job_id = result.get("job_id")
                # Note: shunya_job_id is stored in call_processing_jobs table, not in calls table
                logger.info(
                    f"Triggered Shunya processing for call {request.call_id}, job_id={processing_job_id}"
                )
            except Exception as e:
                logger.error(f"Failed to trigger Shunya processing: {e}", exc_info=True)
                # Don't fail the request - call is updated with audio_url

        return RecordingCompleteResponse(
            call_id=request.call_id,
            status="processing",  # Default status since field doesn't exist in DB
            processing_job_id=processing_job_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing recording: {e}")
        traceback.print_exc()
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

