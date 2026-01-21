"""
Webhook routes.

Handles incoming webhooks from:
- Telephony providers (CallRail, Twilio)
- Shoonya (job completions)
- GoHighLevel (CRM webhooks)

Note: These endpoints are public (no JWT required) as they are called by external services.
For production, implement webhook signature verification to ensure requests are authentic.
"""
import json
import traceback
from typing import Any, Dict, Optional, Set
from uuid import UUID
from fastapi import APIRouter, Header, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.encryption import decrypt_api_key
from app.infrastructure.integrations.crm_mapping import LEAD_UPDATE_EVENT_TYPES
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.services.call_service import CallService
from app.services.ghl_service import GHLService
from app.services.ctm_service import CTMService

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
        traceback.print_exc()
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
        logger.error(f"Error processing Shoonya webhook: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

@router.post("/ghl/messages")
async def ghl_message(
    request: Request,
    db: DbSession,
    x_wh_signature: Optional[str] = Header(default=None),
):
    """
    Handle GHL message webhooks (including call recordings).

    Processes call events, fetches recordings, and uploads them to S3.
    """
    raw = await request.body()

    # Optional but recommended: verify authenticity (reject spoofed webhooks).
    # GHL uses x-wh-signature for verification.
    if x_wh_signature:
        if not GHLService.verify_ghl_signature(raw, x_wh_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = GHLService.extract_event_payload(body)

    # Identify call events: In GHL InboundMessage schema, call events have messageType "CALL".
    message_type = (event.get("messageType") or "").upper()
    if message_type == "CALL":
        # Get company_id from location_id using repository
        from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
        from uuid import UUID

        location_id: Optional[str] = event.get("locationId")
        integration_repo = CompanyIntegrationRepository(db)
        company_id = None
        if location_id:
            try:
                company_id = await integration_repo.get_company_id_by_location_id(location_id)
                if not company_id:
                    logger.warning(f"No company found for location_id {location_id}")
                    return {
                        "ok": False,
                        "isCall": True,
                        "error": f"No company found for location_id {location_id}",
                    }
            except Exception as e:
                logger.error(f"Error getting company_id for location_id {location_id}: {e}")
                return {
                    "ok": False,
                    "isCall": True,
                    "error": f"Error getting company_id: {e}",
                }

        # Initialize GHL service and process call webhook
        ghl_service = GHLService()
        try:
            result = await ghl_service.process_call_webhook(
                event=event,
                db_session=db,
                company_id=company_id,
            )
            return result
        except Exception as e:
            logger.exception(f"Error processing call webhook: {e}")
            return {
                "ok": False,
                "isCall": True,
                "error": str(e),
            }

    # Not a call: acknowledge non CALL quickly with 200 so GHL doesn't retry unnecessarily
    return {"ok": True, "isCall": False, "messageType": event.get("messageType")}


@router.post("/ghl/lead-updates")
async def ghl_lead_updates(
    request: Request,
    db: DbSession,
    x_wh_signature: Optional[str] = Header(default=None),
):
    raw = await request.body()

    # Verify webhook signature
    if x_wh_signature:
        if not GHLService.verify_ghl_signature(raw, x_wh_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # For these event types, the envelope is usually:
    # { "type": "...", "locationId": "...", "timestamp": "...", "webhookId": "...", "data": {...} }
    event_type = body.get("type") or body.get("eventType") or body.get("name")
    location_id = body.get("locationId") or (body.get("data") or {}).get("locationId")
    webhook_id = body.get("webhookId")
    timestamp = body.get("timestamp")

    accepted = event_type in LEAD_UPDATE_EVENT_TYPES

    logger.info(
        "Lead update webhook received type=%s accepted=%s locationId=%s webhookId=%s",
        event_type, accepted, location_id, webhook_id
    )

    if not accepted or not location_id:
        return {
            "ok": True,
            "accepted": accepted,
            "type": event_type,
            "locationId": location_id,
            "webhookId": webhook_id,
            "timestamp": timestamp,
            "message": "Event type not accepted or missing locationId",
        }

    # Get company_id from location_id
    from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
    from uuid import UUID

    integration_repo = CompanyIntegrationRepository(db)
    company_id = await integration_repo.get_company_id_by_location_id(location_id)

    if not company_id:
        logger.warning(f"No company found for location_id {location_id}")
        return {
            "ok": False,
            "error": "No company integration found for location_id",
            "locationId": location_id,
        }

    # Extract event payload (handle both envelope and direct formats)
    event = GHLService.extract_event_payload(body)
    if not event:
        event = body

    # Initialize GHL service
    ghl_service = GHLService()

    try:
        # Route to appropriate handler based on event type
        if event_type == "ContactCreate":
            await ghl_service.insert_contact_event(event, db, UUID(company_id))
        elif event_type == "ContactUpdate" or event_type == "ContactTagUpdate":
            await ghl_service.update_contact_event(event, db, UUID(company_id))
        elif event_type == "ContactDelete":
            await ghl_service.delete_contact_event(event, db, UUID(company_id))
        elif event_type == "AppointmentCreate":
            await ghl_service.insert_appointment_event(event, db, UUID(company_id))
        elif event_type == "AppointmentUpdate":
            await ghl_service.update_appointment_event(event, db, UUID(company_id))
        elif event_type == "AppointmentDelete":
            await ghl_service.delete_appointment_event(event, db, UUID(company_id))
        elif event_type == "OpportunityCreate":
            await ghl_service.insert_lead_event(event, db, UUID(company_id))
        elif event_type in [
            "OpportunityUpdate",
            "OpportunityStatusUpdate",
            "OpportunityStageUpdate",
            "OpportunityMonetaryValueUpdate",
            "OpportunityAssignedToUpdate",
        ]:
            await ghl_service.update_lead_event(event, db, UUID(company_id))
        elif event_type == "OpportunityDelete":
            await ghl_service.delete_lead_event(event, db, UUID(company_id))
        else:
            logger.warning(f"Unhandled event type: {event_type}")

        await db.commit()

        return {
            "ok": True,
            "accepted": accepted,
            "type": event_type,
            "locationId": location_id,
            "webhookId": webhook_id,
            "timestamp": timestamp,
            "processed": True,
        }

    except Exception as e:
        logger.error(f"Error processing GHL webhook: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing webhook: {str(e)}",
        )


@router.post("/ctm/calls")
async def ctm_call_webhook(
    request: Request,
    db: DbSession,
    x_wh_signature: Optional[str] = Header(default=None),
    x_ctm_time: Optional[str] = Header(default=None),
):
    """
    Handle Call Tracking Metrics (CTM) call webhook.

    Processes completed calls (both inbound and outbound):
    - Filters for status: "completed" or "answered"
    - For inbound calls: updates contactCard and call tables, stores audio in S3
    - For outbound calls: updates call tables, stores audio in S3

    Expected payload format (inbound):
    {
        "id": 123456789,
        "direction": "inbound",
        "status": "answered",
        "caller_number": "+15550123456",
        "audio": "https://...",
        ...
    }

    Expected payload format (outbound):
    {
        "id": 987654321,
        "direction": "outbound",
        "status": "completed",
        "dialed_number": "+15559998888",
        "agent_email": "sarah.miller@company.com",
        "audio": "https://...",
        ...
    }
    """
    raw_body = await request.body()

    # Parse JSON to get company_id for fetching auth token
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract company_id from payload or headers
    voip_company_id = str(payload.get("account_id") or request.headers.get("X-Company-Id"))
    integration_repo = CompanyIntegrationRepository(db)

    # Verify webhook signature if provided
    if x_wh_signature:
        if not voip_company_id:
            # Can't verify without company_id, but we'll still continue
            logger.warning("Cannot verify CTM signature without company_id")
        else:
            # Get company integration to retrieve voip_api_encrypted_key
            try:
                voip_api_encrypted_key = await integration_repo.get_voip_api_encrypted_key_by_voip_company_id(
                    voip_company_id
                )

                if not voip_api_encrypted_key:
                    logger.warning(
                        f"No company integration or voip_api_key found for company_id {voip_company_id}"
                    )
                else:
                    # Decrypt the voip_api_encrypted_key
                    auth_token = decrypt_api_key(voip_api_encrypted_key)

                    # Verify signature
                    if not CTMService.verify_ctm_signature(
                        raw_body=raw_body,
                        signature_header=x_wh_signature,
                        time_header=x_ctm_time,
                        auth_token=auth_token,
                    ):
                        raise HTTPException(status_code=401, detail="Invalid webhook signature")
            except ValueError as e:
                # Handle decryption errors
                logger.error(f"Error decrypting voip_api_key for company_id {voip_company_id}: {e}")
                raise HTTPException(status_code=500, detail="Error verifying webhook signature")
            except Exception as e:
                logger.error(f"Error verifying CTM signature: {e}")
                raise HTTPException(status_code=500, detail="Error verifying webhook signature")

    try:
        logger.info("CTM call webhook received", payload=payload)
        if not voip_company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_id required in payload or X-Company-Id header",
            )

        company_id = await integration_repo.get_company_id_by_voip_company_id(voip_company_id)

        # Process CTM webhook
        service = CTMService(db)
        call = await service.process_webhook(
            payload=payload,
            company_id=company_id,
        )

        return {
            "status": "success",
            "call_id": str(call.id),
            "ctm_call_id": payload.get("id"),
        }

    except ValueError as e:
        # Handle cases where call is not completed (expected)
        if "not completed" in str(e) or "not answered" in str(e):
            logger.info(f"Ignoring CTM webhook: {e}")
            return {"status": "ignored", "reason": str(e)}
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error processing CTM call webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
