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

from app.core.config import settings
from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.encryption import decrypt_api_key
from app.infrastructure.integrations.crm_mapping import LEAD_UPDATE_EVENT_TYPES
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.services.call_service import CallService, transform_summary_to_analysis_data
from app.services.ghl_service import GHLService
from app.services.ctm_service import CTMService
from app.services.servicetitan_service import ServiceTitanService

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
    Handle job completion webhook from Shunya.

    Expected payload from Shunya (new format with URLs):
    {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "completed",
        "event_type": "call_processing",
        "timestamp": "2026-01-12T15:05:00Z",
        "call_id": "call_abc123",
        "summary_url": "/api/v1/call-processing/summary/call_abc123",
        "chunks_url": "/api/v1/call-processing/chunks/call_abc123"
    }

    OR (legacy format with results object):
    {
        "job_id": "job_a1b2c3d4e5f6",
        "call_id": "call_abc123",
        "status": "completed",
        "results": {
            "summary_url": "/api/v1/call-processing/summary/call_abc123",
            "chunks_url": "/api/v1/call-processing/chunks/call_abc123",
            "transcript_url": "/api/v1/call-processing/transcript/call_abc123"
        }
    }

    OR (legacy format with full data):
    {
        "shunya_job_id": "job_123",
        "status": "completed",
        "call_id": "uuid-string",
        "company_id": "uuid-string",
        "result": {
            "transcript": "...",
            "analysis": {...}
        }
    }

    This handler:
    1. Receives the webhook payload (lightweight notification with URLs)
    2. Extracts call_id from payload (handles both UUID and "call_abc123" formats)
    3. Calls Shunya's Summary API (GET /api/v1/call-processing/summary/{call_id}) to fetch complete analysis data
    4. Parses and stores all data in the database, including:
       - Rich objection objects (extracts category_text for objections array, stores full objects in raw_analysis)
       - All new fields: compliance_target_role, detected_call_type, is_existing_customer, etc.
       - Property details and customer details as JSONB
    """
    try:
        payload = await request.json()
        logger.info("Shunya job complete webhook received", payload=payload)

        job_status = payload.get("status")
        if job_status != "completed":
            logger.warning(
                "Job not completed, ignoring",
                status=job_status,
                job_id=payload.get("job_id") or payload.get("shunya_job_id"),
            )
            return {"status": "ignored", "reason": f"Job status is {job_status}"}

        # Extract call_id (can be UUID string or int)
        # Handle both "call_abc123" format and UUID format
        # New webhook format: call_id at top level
        # Legacy format: call_id might be in result or other nested locations
        call_id_raw = payload.get("call_id")
        if not call_id_raw:
            # Try legacy format
            result = payload.get("result", {})
            if result and isinstance(result, dict):
                call_id_raw = result.get("call_id")

        if not call_id_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="call_id required in payload",
            )

        # Convert to UUID
        # Shunya may send "call_abc123" format, but we need UUID
        # Try to extract UUID from the call_id or use it directly if it's already a UUID
        call_id = None
        try:
            # If it's already a UUID string, use it directly
            call_id = UUID(call_id_raw)
        except (ValueError, TypeError):
            # If it's in "call_abc123" format, we need to look it up
            # For now, try to parse it as UUID string
            # In production, you might need to maintain a mapping
            logger.warning(
                f"call_id is not a UUID format: {call_id_raw}. "
                f"Attempting to use as-is. If this fails, ensure call_id is a valid UUID.",
            )
            try:
                call_id = UUID(call_id_raw)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid call_id format: {call_id_raw}. Expected UUID.",
                )

        # Get company_id - try multiple sources
        company_id = payload.get("company_id") or request.headers.get("X-Company-Id")

        # Initialize service
        service = CallService(db)

        # Try to get existing call record (OLD FLOW)
        # In NEW FLOW, call may not exist yet
        call = await service.call_repo.get_by_id(call_id)

        # Get company_id from call if exists, otherwise from payload
        if call:
            # OLD FLOW: Call record exists
            if not company_id:
                company_id = str(call.company_id)
            logger.info(f"Found existing call record for {call_id}")
        else:
            # NEW FLOW: Call record doesn't exist yet (direct Shunya submission)
            if not company_id:
                logger.warning(f"Call {call_id} not found and no company_id in payload")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Call {call_id} not found and company_id not provided",
                )
            logger.info(f"No existing call record for {call_id}, will create from Shunya results (NEW FLOW)")

        # CRITICAL: Always fetch complete call summary from Shunya Summary API
        # The webhook payload only contains URLs (summary_url at top level or in results), not the actual data
        # We need to call the Summary API to get the complete structure with all fields
        complete_summary_data = None
        transcript = None
        shoonya = get_shoonya_client()

        if shoonya.is_available():
            try:
                logger.info(f"Fetching complete call summary from Shunya Summary API for call {call_id}")
                complete_summary_data = await shoonya.get_call_summary(
                    call_id=str(call_id),
                    company_id=company_id,
                    include_chunks=False,
                )
                logger.info(f"Successfully fetched complete summary for call {call_id}")

                # Extract transcript from summary if available
                transcript = complete_summary_data.get("transcript")

            except Exception as e:
                logger.error(
                    f"Failed to fetch complete summary from Shunya Summary API: {e}",
                    call_id=str(call_id),
                    exc_info=True
                )
                # Try to extract data from webhook payload as fallback
                result = payload.get("result", {})
                if result:
                    transcript = result.get("transcript")
                    analysis_data = result.get("analysis", {})
                    if analysis_data:
                        complete_summary_data = analysis_data

                if not complete_summary_data:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to fetch summary from Shunya API and no fallback data available: {str(e)}",
                    )
        else:
            # Shunya not configured - try to use webhook payload data
            logger.warning("Shunya client not available, attempting to use webhook payload data")
            result = payload.get("result", {})
            if result:
                transcript = result.get("transcript")
                analysis_data = result.get("analysis", {})
                if analysis_data:
                    complete_summary_data = analysis_data
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No analysis data in webhook payload and Shunya client not available",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No result data in webhook payload and Shunya client not available",
                )

        # Process analysis with complete data from Summary API
        logger.info(f"Processing analysis for call {call_id} with complete summary data")

        analysis = await service.process_analysis(
            call_id=call_id,
            analysis_data=complete_summary_data,
            transcript=transcript,
        )
        await db.commit()
        logger.info(
            "Shunya webhook processed successfully",
            call_id=str(call_id),
            analysis_id=str(analysis.id),
            job_id=payload.get("job_id") or payload.get("shunya_job_id"),
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

    Processes both inbound and outbound call events:
    - Standard GHL format: InboundMessage/OutboundMessage with messageType="CALL"
    - Custom outbound webhooks: POST from GHL workflows with callDirection, callFrom, callTo, callStatus fields

    For inbound calls: contact is the caller (from field)
    For outbound calls: contact is the recipient (to field)

    Fetches recordings (when available) and uploads them to S3.
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

    logger.info("GHL message webhook received", payload=body, extracted_event=event)

    # Normalize outbound webhook format to standard GHL format
    # Outbound webhooks from GHL workflows may use different field names:
    # callDirection -> direction, callFrom -> from, callTo -> to, callStatus -> status
    if "callDirection" in event and "direction" not in event:
        event["direction"] = event.pop("callDirection")
    if "callFrom" in event and "from" not in event:
        event["from"] = event.pop("callFrom")
    if "callTo" in event and "to" not in event:
        event["to"] = event.pop("callTo")
    if "callStatus" in event and "status" not in event:
        event["status"] = event.pop("callStatus")
    # callDuration might already be in the event, keep both if present

    # Identify call events:
    # 1. Standard GHL format: messageType "CALL" (InboundMessage/OutboundMessage)
    # 2. Custom outbound webhook: type "InboundMessage" or "OutboundMessage" with call data
    # 3. Direct call webhook: has call-related fields (direction, status, etc.)
    message_type = (event.get("messageType") or "").upper()
    webhook_type = (event.get("type") or "").upper()
    has_call_fields = any(key in event for key in ["direction", "callDirection", "status", "callStatus", "callDuration"])

    is_call_event = (
        message_type == "CALL" or
        webhook_type in ("INBOUNDMESSAGE", "OUTBOUNDMESSAGE") or
        (has_call_fields and event.get("status", "").lower() in (
            "completed", "answered", "no-answer", "no answer", "busy", "voicemail", "failed", "missed"
        ))
    )

    if is_call_event:
        # Get company_id from location_id using repository
        # For outbound webhooks, location_id might not be present
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
                    # For outbound webhooks, continue without company_id if location_id not found
                    # The process_call_webhook will handle gracefully
                else:
                    # Convert company_id to Python UUID if needed (handles asyncpg UUID objects)
                    if not isinstance(company_id, UUID):
                        company_id = UUID(str(company_id))
            except Exception as e:
                logger.error(f"Error getting company_id for location_id {location_id}: {e}")
                # Continue processing even if we can't get company_id
                # Some outbound webhooks might not have location_id

        # Initialize GHL service and process call webhook
        # Note: company_id can be None for outbound webhooks without location_id
        # Get decrypted CRM API key from database if company_id is available
        bearer_token = None
        if company_id:
            try:
                bearer_token = await integration_repo.get_decrypted_crm_key(company_id)
            except Exception as e:
                logger.warning(f"Failed to get CRM API key for company {company_id}: {e}")

        ghl_service = GHLService(bearer_token=bearer_token)
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

    logger.info("GHL lead-updates webhook received", payload=body)

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

    # Convert company_id to Python UUID if needed (handles asyncpg UUID objects)
    # asyncpg returns UUID objects that need to be converted to Python UUID
    if not isinstance(company_id, UUID):
        # If it's an asyncpg UUID or other UUID-like object, convert via string
        company_id = UUID(str(company_id))

    # Extract event payload (handle both envelope and direct formats)
    event = GHLService.extract_event_payload(body)
    if not event:
        event = body

    # Get decrypted CRM API key from database for this company
    bearer_token = None
    try:
        bearer_token = await integration_repo.get_decrypted_crm_key(company_id)
    except Exception as e:
        logger.warning(f"Failed to get CRM API key for company {company_id}: {e}")

    # Initialize GHL service with bearer token from database
    ghl_service = GHLService(bearer_token=bearer_token)

    try:
        # Route to appropriate handler based on event type
        if event_type == "ContactCreate":
            await ghl_service.insert_contact_event(event, db, company_id)
        elif event_type == "ContactUpdate" or event_type == "ContactTagUpdate":
            await ghl_service.update_contact_event(event, db, company_id)
        elif event_type == "ContactDelete":
            await ghl_service.delete_contact_event(event, db, company_id)
        elif event_type == "AppointmentCreate":
            await ghl_service.insert_appointment_event(event, db, company_id)
        elif event_type == "AppointmentUpdate":
            await ghl_service.update_appointment_event(event, db, company_id)
        elif event_type == "AppointmentDelete":
            await ghl_service.delete_appointment_event(event, db, company_id)
        elif event_type == "OpportunityCreate":
            await ghl_service.insert_lead_event(event, db, company_id)
        elif event_type in [
            "OpportunityUpdate",
            "OpportunityStatusUpdate",
            "OpportunityStageUpdate",
            "OpportunityMonetaryValueUpdate",
            "OpportunityAssignedToUpdate",
        ]:
            await ghl_service.update_lead_event(event, db, company_id)
        elif event_type == "OpportunityDelete":
            await ghl_service.delete_lead_event(event, db, company_id)
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


def _verify_worker_secret(x_worker_secret: str | None) -> None:
    """Validate the shared secret sent by the ST poller worker."""
    expected = settings.ST_WORKER_SECRET
    if expected and x_worker_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid worker secret")


@router.post("/servicetitan/calls")
async def servicetitan_calls_webhook(
    request: Request,
    db: DbSession,
    x_worker_secret: Optional[str] = Header(default=None),
):
    """
    Receive batched ServiceTitan call records from the ST poller worker.

    Payload: { "tenant_id": "...", "calls": [...], "poll_timestamp": "..." }
    """
    _verify_worker_secret(x_worker_secret)

    try:
        payload = await request.json()
        logger.info("ST calls payload received", payload=payload)
        logger.info("ST calls webhook received", tenant_id=payload.get("tenant_id"))

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id required")

        integration_repo = CompanyIntegrationRepository(db)
        company_id = await integration_repo.get_company_id_by_st_tenant_id(str(tenant_id))
        if not company_id:
            raise HTTPException(
                status_code=404,
                detail=f"No company found for ST tenant_id {tenant_id}",
            )

        if not isinstance(company_id, UUID):
            company_id = UUID(str(company_id))

        service = ServiceTitanService(db)
        result = await service.process_calls_webhook(payload, company_id)
        await db.commit()

        return {"status": "success", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing ST calls webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/servicetitan/crm")
async def servicetitan_crm_webhook(
    request: Request,
    db: DbSession,
    x_worker_secret: Optional[str] = Header(default=None),
):
    """
    Receive batched ServiceTitan CRM records from the ST poller worker.

    Payload: {
        "tenant_id": "...",
        "customers": [...],
        "customer_contacts": [...],
        "leads": [...],
        "bookings": [...]
    }
    """
    _verify_worker_secret(x_worker_secret)

    try:
        payload = await request.json()
        logger.info("ST CRM payload received", payload=payload)
        logger.info("ST CRM webhook received", tenant_id=payload.get("tenant_id"))

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id required")

        integration_repo = CompanyIntegrationRepository(db)
        company_id = await integration_repo.get_company_id_by_st_tenant_id(str(tenant_id))
        if not company_id:
            raise HTTPException(
                status_code=404,
                detail=f"No company found for ST tenant_id {tenant_id}",
            )

        if not isinstance(company_id, UUID):
            company_id = UUID(str(company_id))

        service = ServiceTitanService(db)
        result = await service.process_crm_webhook(payload, company_id)
        await db.commit()

        return {"status": "success", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing ST CRM webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
