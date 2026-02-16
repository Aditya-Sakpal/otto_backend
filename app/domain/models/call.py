"""
Call domain model.

Represents a phone call record.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import CallType


class Call(BaseModel):
    """
    Call model.

    Represents a phone call from telephony providers (CallRail, Twilio).
    """
    company_id: UUID = Field(..., description="Company/tenant ID")
    contact_card_id: Optional[UUID] = Field(None, description="Associated contact")
    lead_id: Optional[UUID] = Field(None, description="Associated lead")
    phone_number: str = Field(..., description="Caller phone number")
    call_type: Optional[CallType] = Field(None, description="Type of call")
    missed_call: bool = Field(default=False, description="Whether call was missed")
    transcript: Optional[str] = Field(None, description="Call transcript")
    audio_url: Optional[str] = Field(None, description="Audio recording URL")
    duration_seconds: Optional[int] = Field(None, description="Call duration in seconds")
    handled_by_user_id: Optional[UUID] = Field(None, description="CSR who handled the call")
    interaction_type: Optional[str] = Field(default="call", description="Type of interaction")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

