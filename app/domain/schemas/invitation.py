"""
Invitation Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import InvitationStatus


class InvitationCreate(BaseModel):
    """Schema for creating a new invitation."""
    email: EmailStr = Field(..., description="Email address to send invitation to")
    company_id: UUID = Field(..., description="Company ID to invite user to")


class InvitationResponse(BaseModel):
    """Schema for invitation API responses."""
    id: UUID = Field(..., description="Invitation UUID")
    email: str = Field(..., description="Email address of the invitee")
    company_id: UUID = Field(..., description="Company ID")
    inviter_id: UUID = Field(..., description="User ID who sent the invitation")
    status: InvitationStatus = Field(..., description="Invitation status")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    accepted_at: Optional[datetime] = Field(None, description="Acceptance timestamp")

    class Config:
        from_attributes = True


class InvitationAcceptResponse(BaseModel):
    """Schema for invitation acceptance response."""
    message: str = Field(..., description="Success message")
    invitation: InvitationResponse = Field(..., description="Accepted invitation details")
