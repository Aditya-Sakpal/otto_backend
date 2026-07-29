"""Rep phone domain model."""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class RepPhone(BaseModel):
    """Domain model for a sales rep's verified phone number."""

    id: Optional[UUID] = None
    user_id: UUID
    phone_number: str
    is_verified: bool = False
    is_primary: bool = True
    verification_code: Optional[str] = None
    verification_expires_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    expo_push_token: Optional[str] = None
    extra_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
