"""
Masked communications API routes.

JWT-authenticated endpoints for the mobile app:
- List active proxy sessions for the current rep
- View conversation threads (calls + SMS)
- Initiate outbound calls
- Send SMS
- Register/verify rep phone numbers
- Update push notification token
"""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.services.masked_comms_service import MaskedCommsService
from app.services.proxy_session_service import ProxySessionService, SessionNotFoundError
from app.services.rep_phone_service import RepPhoneService, RepPhoneNotRegisteredError
from app.services.proxy_pool_service import NoAvailableProxyNumberError

logger = get_logger(__name__)

router = APIRouter()

RESPONSES = {
    401: {"description": "Not authenticated"},
    403: {"description": "Not authorized"},
}


# ── Request/Response Schemas ──────────────────────────────────────────────


class SendSMSRequest(BaseModel):
    body: str = Field(..., max_length=1600, description="SMS message body")


class RegisterPhoneRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format")


class VerifyPhoneRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class PushTokenRequest(BaseModel):
    expo_push_token: str = Field(
        ..., description="Expo push token (ExponentPushToken[...])"
    )


class SessionResponse(BaseModel):
    id: str
    lead_id: str
    proxy_number_id: str
    homeowner_phone_masked: str
    status: str
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class CommunicationResponse(BaseModel):
    id: str
    comm_type: str
    direction: str
    message_body: Optional[str] = None
    call_status: Optional[str] = None
    duration_seconds: Optional[int] = None
    is_homeowner_reply: bool = False
    source_metadata: Optional[dict] = None
    audio_url: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class PhoneStatusResponse(BaseModel):
    has_phone: bool
    is_verified: bool
    phone_number: Optional[str] = None


# ── Session Endpoints ─────────────────────────────────────────────────────


@router.get("/sessions", responses=RESPONSES)
async def list_sessions(
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Get all active proxy sessions for the current rep."""
    service = ProxySessionService(db)
    sessions = await service.get_sessions_for_rep(user.id)
    return {
        "sessions": [
            {
                "id": str(s.id),
                "lead_id": str(s.lead_id),
                "proxy_number_id": str(s.proxy_number_id),
                "homeowner_phone_masked": _mask_phone(s.homeowner_phone),
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}/conversation", responses=RESPONSES)
async def get_conversation(
    session_id: UUID,
    db: DbSession,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Get conversation thread (calls + SMS) for a session."""
    service = MaskedCommsService(db)
    messages = await service.get_conversation(session_id, skip, limit)
    return {
        "session_id": str(session_id),
        "messages": [
            {
                "id": str(m.id),
                "comm_type": m.comm_type,
                "direction": m.direction,
                "message_body": m.message_body,
                "call_status": m.call_status,
                "duration_seconds": m.duration_seconds,
                "is_homeowner_reply": m.is_homeowner_reply,
                "source_metadata": m.source_metadata,
                "audio_url": m.audio_url,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


# ── Communication Action Endpoints ────────────────────────────────────────


@router.post("/sessions/{session_id}/call", responses=RESPONSES)
async def initiate_call(
    session_id: UUID,
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Rep initiates an outbound call to homeowner via proxy."""
    try:
        service = MaskedCommsService(db)
        result = await service.initiate_outbound_call(session_id)
        await db.commit()
        return {"call_sid": result["call_sid"], "status": result["status"]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Error initiating call: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate call")


@router.post("/sessions/{session_id}/sms", responses=RESPONSES)
async def send_sms(
    session_id: UUID,
    request: SendSMSRequest,
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Rep sends SMS to homeowner via proxy."""
    try:
        service = MaskedCommsService(db)
        result = await service.send_sms(session_id, request.body)
        await db.commit()
        return {"message_sid": result["message_sid"], "status": result["status"]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail="Failed to send SMS")


# ── Phone Registration Endpoints ──────────────────────────────────────────


@router.post("/phone/register", responses=RESPONSES)
async def register_phone(
    request: RegisterPhoneRequest,
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Start phone registration — sends OTP to the provided number."""
    service = RepPhoneService(db)
    result = await service.register_phone(user.id, request.phone_number)
    await db.commit()
    return result


@router.post("/phone/verify", responses=RESPONSES)
async def verify_phone(
    request: VerifyPhoneRequest,
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Verify OTP for phone registration."""
    try:
        service = RepPhoneService(db)
        rep_phone = await service.verify_phone(
            user.id, request.phone_number, request.code
        )
        await db.commit()
        return {
            "status": "verified",
            "phone_number": _mask_phone(rep_phone.phone_number),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/phone/status", responses=RESPONSES)
async def phone_status(
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Check if the current rep has a verified phone number."""
    service = RepPhoneService(db)
    return await service.get_phone_status(user.id)


# ── Push Token Endpoint ──────────────────────────────────────────────────


@router.post("/push-token", responses=RESPONSES)
async def update_push_token(
    request: PushTokenRequest,
    db: DbSession,
    user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """Register or update Expo push notification token."""
    service = RepPhoneService(db)
    await service.update_push_token(user.id, request.expo_push_token)
    await db.commit()
    return {"status": "updated"}


# ── Helpers ───────────────────────────────────────────────────────────────


def _mask_phone(phone: str) -> str:
    """Mask a phone number for display."""
    if len(phone) >= 4:
        return phone[:2] + "*" * (len(phone) - 6) + phone[-4:]
    return phone
