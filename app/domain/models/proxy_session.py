"""Proxy session domain model."""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class ProxySession(BaseModel):
    """Domain model for a masked communication session."""

    id: Optional[UUID] = None
    company_id: UUID
    lead_id: UUID
    rep_user_id: UUID
    proxy_number_id: UUID
    homeowner_phone: str
    rep_phone: str
    status: str = "active"
    closed_reason: Optional[str] = None
    extra_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
