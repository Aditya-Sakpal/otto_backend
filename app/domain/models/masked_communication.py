"""Masked communication domain model."""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class MaskedCommunication(BaseModel):
    """Domain model for an individual call or SMS within a proxy session."""

    id: Optional[UUID] = None
    session_id: UUID
    company_id: UUID
    lead_id: UUID
    comm_type: str  # call | sms
    direction: str  # rep_to_homeowner | homeowner_to_rep
    from_number: str
    to_number: str
    proxy_number: str

    # Call-specific
    twilio_call_sid: Optional[str] = None
    duration_seconds: Optional[int] = None
    call_status: Optional[str] = None
    recording_url: Optional[str] = None
    recording_sid: Optional[str] = None
    audio_url: Optional[str] = None
    call_id: Optional[UUID] = None

    # SMS-specific
    twilio_message_sid: Optional[str] = None
    message_body: Optional[str] = None

    extra_metadata: Optional[dict] = None

    # Intelligence layer
    is_homeowner_reply: bool = False
    source_metadata: Optional[dict] = None
    intent_label: Optional[str] = None
    confidence_score: Optional[float] = None

    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
