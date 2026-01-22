"""
Invitation domain model.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import InvitationStatus, UserRole


class Invitation(BaseModel):
    """
    Invitation domain model.

    Represents an invitation sent to a user to join a company.
    """
    email: str = Field(..., description="Email address of the invitee")
    company_id: UUID = Field(..., description="Company ID the invitation is for")
    inviter_id: UUID = Field(..., description="User ID who sent the invitation")
    token: str = Field(..., description="Unique token for accepting the invitation")
    role: UserRole = Field(..., description="Role assigned upon acceptance")
    status: InvitationStatus = Field(..., description="Invitation status")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    accepted_at: Optional[datetime] = Field(None, description="Acceptance timestamp (if accepted)")
