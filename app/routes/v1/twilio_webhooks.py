"""
Twilio webhook routes for masked communications.

Handles incoming webhooks from Twilio:
- Inbound voice calls to proxy numbers
- Inbound SMS to proxy numbers
- Call status updates
- Recording ready notifications
- Bridge call TwiML (second leg of outbound calls)

These endpoints are public (called by Twilio) but verified via X-Twilio-Signature.
All responses are TwiML XML.
"""
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Form, Header, Depends
from fastapi.responses import Response

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.infrastructure.integrations.twilio_client import get_twilio_client
from app.services.masked_comms_service import MaskedCommsService
from app.services.proxy_session_service import SessionNotFoundError

logger = get_logger(__name__)

router = APIRouter()

TWIML_CONTENT_TYPE = "application/xml"
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
ERROR_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response><Say>An error occurred. Please try again later.</Say></Response>'


# ── Twilio Signature Validation ───────────────────────────────────────────


async def _validate_twilio_signature(request: Request) -> None:
    """
    Validate Twilio webhook signature.

    Extracts X-Twilio-Signature header, reconstructs the full URL,
    and validates using the Twilio auth token.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    twilio = get_twilio_client()
    if not twilio.is_available():
        logger.warning("Twilio not configured — skipping signature validation")
        return

    form_data = await request.form()
    url = str(request.url)

    if not twilio.validate_request(url, dict(form_data), signature):
        logger.warning("Invalid Twilio signature", url=url)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


# ── Webhook Endpoints ─────────────────────────────────────────────────────


@router.post("/twilio/inbound-call")
async def inbound_call(
    request: Request,
    db: DbSession,
    From: str = Form(...),
    To: str = Form(...),
    CallSid: str = Form(...),
):
    """
    Inbound voice call to a proxy number.

    Twilio POSTs when someone calls a proxy number.
    Returns TwiML to bridge the call to the other party.
    """
    await _validate_twilio_signature(request)

    try:
        service = MaskedCommsService(db)
        twiml = await service.handle_inbound_call(
            proxy_number=To,
            caller=From,
            twilio_call_sid=CallSid,
        )
        await db.commit()
        return Response(content=twiml, media_type=TWIML_CONTENT_TYPE)
    except SessionNotFoundError as e:
        logger.warning(f"No session for inbound call: {e}")
        return Response(content=ERROR_TWIML, media_type=TWIML_CONTENT_TYPE)
    except Exception as e:
        logger.error(f"Error handling inbound call: {e}")
        await db.rollback()
        return Response(content=ERROR_TWIML, media_type=TWIML_CONTENT_TYPE)


@router.post("/twilio/inbound-sms")
async def inbound_sms(
    request: Request,
    db: DbSession,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(""),
    MessageSid: str = Form(...),
):
    """
    Inbound SMS to a proxy number.

    Twilio POSTs when someone texts a proxy number.
    Forwards the SMS to the other party.
    """
    await _validate_twilio_signature(request)

    try:
        service = MaskedCommsService(db)
        twiml = await service.handle_inbound_sms(
            proxy_number=To,
            sender=From,
            body=Body,
            twilio_message_sid=MessageSid,
        )
        await db.commit()
        return Response(content=twiml, media_type=TWIML_CONTENT_TYPE)
    except SessionNotFoundError as e:
        logger.warning(f"No session for inbound SMS: {e}")
        return Response(content=EMPTY_TWIML, media_type=TWIML_CONTENT_TYPE)
    except Exception as e:
        logger.error(f"Error handling inbound SMS: {e}")
        await db.rollback()
        return Response(content=EMPTY_TWIML, media_type=TWIML_CONTENT_TYPE)


@router.post("/twilio/call-status")
async def call_status(
    request: Request,
    db: DbSession,
    CallSid: str = Form(...),
    CallStatus: str = Form(""),
    CallDuration: int = Form(0),
):
    """
    Call status callback from Twilio.

    Fired when a call ends. Updates the masked_communications record.
    """
    await _validate_twilio_signature(request)

    try:
        service = MaskedCommsService(db)
        await service.handle_call_status(CallSid, CallStatus, CallDuration)
        await db.commit()
    except Exception as e:
        logger.error(f"Error handling call status: {e}")
        await db.rollback()

    return Response(content=EMPTY_TWIML, media_type=TWIML_CONTENT_TYPE)


@router.post("/twilio/recording-status")
async def recording_status(
    request: Request,
    db: DbSession,
    CallSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingSid: str = Form(...),
):
    """
    Recording ready callback from Twilio.

    Fired when a call recording is available. Downloads the recording,
    uploads to S3, creates a Call record, and submits to Shunya.
    """
    await _validate_twilio_signature(request)

    try:
        service = MaskedCommsService(db)
        await service.handle_recording_ready(CallSid, RecordingUrl, RecordingSid)
        await db.commit()
    except Exception as e:
        logger.error(f"Error handling recording status: {e}")
        await db.rollback()

    return Response(content=EMPTY_TWIML, media_type=TWIML_CONTENT_TYPE)


@router.post("/twilio/bridge-call/{session_id}")
async def bridge_call(
    request: Request,
    session_id: UUID,
    db: DbSession,
):
    """
    Bridge call TwiML endpoint.

    Called by Twilio when the rep answers the first leg of an outbound call.
    Returns TwiML that dials the homeowner (second leg).
    """
    await _validate_twilio_signature(request)

    try:
        service = MaskedCommsService(db)
        twiml = await service.get_bridge_twiml(session_id)
        return Response(content=twiml, media_type=TWIML_CONTENT_TYPE)
    except Exception as e:
        logger.error(f"Error generating bridge TwiML: {e}")
        return Response(content=ERROR_TWIML, media_type=TWIML_CONTENT_TYPE)
