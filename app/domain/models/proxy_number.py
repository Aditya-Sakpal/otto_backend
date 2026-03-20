"""Proxy number domain model."""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ProxyNumber(BaseModel):
    """Domain model for a proxy phone number in the pool."""

    id: Optional[UUID] = None
    company_id: UUID
    phone_number: str
    twilio_sid: str
    friendly_name: Optional[str] = None
    is_active: bool = True
    is_assigned: bool = False
    capabilities_sms: bool = True
    capabilities_voice: bool = True
    region: Optional[str] = None
    last_released_at: Optional[datetime] = None
    extra_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
