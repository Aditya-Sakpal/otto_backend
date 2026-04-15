"""
Recordings API routes.

Handles recording initiation for mobile uploads.
Recordings are tied directly to appointments (not calls).
"""
import traceback
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from sqlalchemy import select as sa_select
from app.domain.enums import UserRole, PipelineStage
from app.infrastructure.database.models.lead import LeadORM
from app.domain.users.models import User
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.integrations.shoonya import get_shoonya_client

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    403: {"description": "Forbidden"},
    404: {"description": "Appointment not found"},
    500: {"description": "Internal server error"},
    503: {"description": "S3 service not available"},
}


class RecordingInitiateRequest(BaseModel):
    """Request to initiate a recording upload."""
    appointment_id: UUID = Field(..., description="Appointment ID to associate recording with")

    model_config = {"json_schema_extra": {"example": {"appointment_id": "c3d4e5f6-a7b8-9012-cdef-345678901234"}}}


class RecordingInitiateResponse(BaseModel):
    """Response with pre-signed S3 URL for uploading audio."""
    appointment_id: UUID = Field(..., description="Appointment ID")
    upload_url: str = Field(..., description="Pre-signed S3 URL for uploading audio (expires in 15 minutes)")
    s3_key: str = Field(..., description="S3 key where the file will be stored")


@router.post("/initiate", response_model=RecordingInitiateResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def initiate_recording(
    request: RecordingInitiateRequest,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> RecordingInitiateResponse:
    """
    Initiate a recording upload for an appointment.

    This endpoint:
    1. Validates the appointment exists
    2. Returns a pre-signed S3 URL for the mobile app to upload the audio file

    Access: Any authenticated user
    """
    try:
        appointment_repo = AppointmentRepository(db)

        # Get the appointment
        appointment = await appointment_repo.get_by_id(request.appointment_id)
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

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
            filename=f"appointment_{request.appointment_id}",
            extension="wav"
        )

        upload_url = s3_service.generate_presigned_url(
            s3_key=s3_key,
            content_type="audio/x-wav",
            bucket_type="audio",
        )

        logger.info(
            f"Generated pre-signed URL for appointment {request.appointment_id}"
        )

        return RecordingInitiateResponse(
            appointment_id=request.appointment_id,
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
    appointment_id: UUID = Field(..., description="Appointment ID")
    s3_key: str = Field(..., description="S3 key where the file was uploaded")


class RecordingCompleteResponse(BaseModel):
    """Response after recording upload completion."""
    appointment_id: UUID = Field(..., description="Appointment ID")
    status: str = Field(..., description="Processing status")
    processing_job_id: Optional[str] = Field(None, description="Shunya job ID if processing was triggered")


@router.post("/complete", response_model=RecordingCompleteResponse, responses=RESPONSES)
async def complete_recording(
    request: RecordingCompleteRequest,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> RecordingCompleteResponse:
    """
    Complete recording upload and trigger processing.

    This endpoint:
    1. Updates Appointment with audio_url (from S3 key)
    2. Triggers Shunya processing with appointment_id as tracker

    Access: Any authenticated user
    """
    try:
        appointment_repo = AppointmentRepository(db)

        # Get the appointment
        appointment = await appointment_repo.get_by_id(request.appointment_id)
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        # Generate S3 URL from key
        s3_service = get_s3_service()
        if not s3_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 service not available",
            )

        audio_url = s3_service.get_public_url(request.s3_key, bucket_type="audio")

        # Set audio_url directly on the appointment
        appointment.audio_url = audio_url
        appointment.recording_status = "uploaded"
        appointment.mark_updated()
        await appointment_repo.update(request.appointment_id, appointment)
        await db.commit()

        # Move lead to APPOINTMENT_RAN since recording proves the appointment happened
        # Also assign the sales rep to the lead if not already assigned
        if appointment.lead_id:
            result = await db.execute(
                sa_select(LeadORM).where(LeadORM.id == appointment.lead_id)
            )
            lead_orm = result.scalar_one_or_none()
            if lead_orm:
                updated = False
                if lead_orm.pipeline_stage in (
                    PipelineStage.BOOKED.value,
                    PipelineStage.APPOINTMENT.value,
                ):
                    lead_orm.pipeline_stage = PipelineStage.APPOINTMENT_RAN.value
                    updated = True
                if not lead_orm.assigned_rep_id and appointment.assigned_rep_id:
                    lead_orm.assigned_rep_id = appointment.assigned_rep_id
                    updated = True
                if updated:
                    await db.flush()
                    await db.commit()
                    logger.info(
                        f"Updated lead {appointment.lead_id}: "
                        f"pipeline_stage={lead_orm.pipeline_stage}, "
                        f"assigned_rep_id={lead_orm.assigned_rep_id}"
                    )

        logger.info(
            f"Recording upload completed for appointment {request.appointment_id}, triggering processing"
        )

        # Trigger Shunya processing with appointment_id as tracker
        processing_job_id = None
        shoonya = get_shoonya_client()
        shoonya_available = shoonya.is_available()
        submission_error: Optional[str] = None
        if shoonya_available:
            try:
                from datetime import datetime

                webhook_url = f"{settings.API_URL}/api/v1/webhooks/shoonya/job-complete"

                result = await shoonya.process_call(
                    call_id=str(appointment.id),  # appointment_id as tracker
                    company_id=str(appointment.company_id),
                    audio_url=audio_url,
                    phone_number="",
                    duration=0,
                    call_date=appointment.scheduled_start.isoformat() if appointment.scheduled_start else datetime.utcnow().isoformat(),
                    webhook_url=webhook_url,
                    metadata={
                        "is_appointment": True,
                        "appointment_id": str(appointment.id),
                        "interaction_type": "meeting",
                        "call_type": "sales_call",
                        "role": "sales_rep",
                        "lead_id": str(appointment.lead_id) if appointment.lead_id else None,
                        "contact_card_id": str(appointment.contact_card_id) if appointment.contact_card_id else None,
                    },
                )
                processing_job_id = result.get("job_id")

                # Store job ID on appointment
                appointment.shunya_job_id = processing_job_id
                appointment.analysis_status = "processing"
                appointment.mark_updated()
                await appointment_repo.update(request.appointment_id, appointment)
                await db.commit()

                logger.info(
                    f"Triggered Shunya processing for appointment {request.appointment_id}, job_id={processing_job_id}"
                )
            except Exception as e:
                submission_error = str(e)
                logger.error(f"Failed to trigger Shunya processing: {e}", exc_info=True)

        # CL-44 parity for sales audio: if we either couldn't reach Shunya or
        # the submission raised, record the failure explicitly so the
        # appointment doesn't sit in whatever state the recording-upload step
        # last left it. Frontend + operators key off analysis_status="failed"
        # to show "Analysis failed — retry?" instead of a permanent spinner.
        if not shoonya_available or submission_error is not None:
            try:
                appointment.analysis_status = "failed"
                existing_meta = dict(appointment.extra_metadata or {})
                existing_meta["analysis_failure"] = {
                    "source": "recordings_complete_submission",
                    "detail": (
                        submission_error
                        if submission_error
                        else "shoonya_client_unavailable"
                    )[:500],
                    "recorded_at": __import__("datetime").datetime.utcnow().isoformat(),
                }
                appointment.extra_metadata = existing_meta
                appointment.mark_updated()
                await appointment_repo.update(request.appointment_id, appointment)
                await db.commit()
            except Exception as mark_err:
                logger.warning(
                    f"Could not mark appointment {request.appointment_id} analysis_status=failed: {mark_err}"
                )
                try:
                    await db.rollback()
                except Exception:
                    pass

        return RecordingCompleteResponse(
            appointment_id=request.appointment_id,
            status=(
                "failed"
                if (not shoonya_available or submission_error is not None)
                else "processing"
            ),
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


class RecordingAnalysisResponse(BaseModel):
    """Response with appointment analysis data."""
    appointment_id: UUID
    analysis_status: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[list[str]] = None
    action_items: Optional[list[str]] = None
    next_steps: Optional[list[str]] = None
    objections: Optional[list[str]] = None
    objection_texts: Optional[list[str]] = None
    objections_total_count: Optional[int] = None
    qualification_status: Optional[str] = None
    booking_status: Optional[str] = None
    sentiment_score: Optional[float] = None
    sop_compliance_score: Optional[float] = None
    sop_compliance_rate: Optional[float] = None
    sop_stages_completed: Optional[list[str]] = None
    sop_stages_missed: Optional[list[str]] = None
    sop_compliance_issues: Optional[list[str]] = None
    sop_compliance_positive_behaviors: Optional[list[str]] = None
    compliance_target_role: Optional[str] = None
    transcript: Optional[str] = None
    duration_seconds: Optional[int] = None


@router.get("/{appointment_id}/analysis", response_model=RecordingAnalysisResponse, responses=RESPONSES)
async def get_recording_analysis(
    db: DbSession,
    appointment_id: UUID,
    user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE, UserRole.CSR])),
):
    """
    Get recording analysis for an appointment.

    Returns structured analysis with summary, objections, compliance, qualification.

    Access: Sales reps, executives, and CSRs
    """
    try:
        appointment_repo = AppointmentRepository(db)
        appointment = await appointment_repo.get_by_id(appointment_id)

        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment not found: {appointment_id}",
            )

        # Sales-audio failure visibility: "failed" is now a first-class
        # terminal state (set by /recordings/complete when Shunya submission
        # fails, or by the Shunya webhook when summary fetch / extraction
        # fails). Return 200 with the existing schema — all analytical
        # fields are already Optional on the response, so the payload is
        # structurally valid, and clients that look at analysis_status can
        # render a "retry?" affordance instead of spinning on 404.
        if not appointment.analysis_status or appointment.analysis_status not in (
            "completed",
            "failed",
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recording analysis not yet available for appointment {appointment_id}",
            )

        return RecordingAnalysisResponse(
            appointment_id=appointment.id,
            analysis_status=appointment.analysis_status,
            summary=appointment.summary,
            key_points=appointment.key_points,
            action_items=appointment.action_items,
            next_steps=appointment.next_steps,
            objections=appointment.objections,
            objection_texts=appointment.objection_texts,
            objections_total_count=appointment.objections_total_count,
            qualification_status=appointment.qualification_status,
            booking_status=appointment.booking_status,
            sentiment_score=appointment.sentiment_score,
            sop_compliance_score=appointment.sop_compliance_score,
            sop_compliance_rate=appointment.sop_compliance_rate,
            sop_stages_completed=appointment.sop_stages_completed,
            sop_stages_missed=appointment.sop_stages_missed,
            sop_compliance_issues=appointment.sop_compliance_issues,
            sop_compliance_positive_behaviors=appointment.sop_compliance_positive_behaviors,
            compliance_target_role=appointment.compliance_target_role,
            transcript=appointment.transcript,
            duration_seconds=appointment.duration_seconds,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recording analysis: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch recording analysis: {str(e)}",
        )
