"""
Invitation Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import InvitationStatus, UserRole
from app.domain.users.schemas import UserResponse


class InvitationCreate(BaseModel):
    """Schema for creating a new invitation."""
    email: EmailStr = Field(..., description="Email address to send invitation to")
    company_id: UUID = Field(..., description="Company ID to invite user to")
    role: UserRole = Field(default=UserRole.CSR, description="Role for the invited user. Allowed: csr, sales_rep, executive")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newuser@example.com",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "role": "csr",
            }
        }
    }


class InvitationResponse(BaseModel):
    """Schema for invitation API responses."""
    id: UUID = Field(..., description="Invitation UUID")
    email: str = Field(..., description="Email address of the invitee")
    company_id: UUID = Field(..., description="Company ID")
    inviter_id: UUID = Field(..., description="User ID who sent the invitation")
    token: str = Field(..., description="Invitation token — use this to call /invites/validate/{token} or accept the invite")
    role: UserRole = Field(..., description="Role assigned upon acceptance")
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


class InvitationValidateResponse(BaseModel):
    """Schema for invitation token validation response."""
    valid: bool = Field(..., description="Whether the invitation token is valid")
    invitation: InvitationResponse = Field(..., description="Invitation details")


class InvitationSignupRequest(BaseModel):
    """Schema for accepting an invitation by creating a user account."""
    token: str = Field(..., min_length=1, description="Invitation token")
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")


class InvitationSignupResponse(BaseModel):
    """Schema for invitation acceptance + signup response."""
    message: str = Field(..., description="Success message")
    invitation: InvitationResponse = Field(..., description="Accepted invitation details")
    user: UserResponse = Field(..., description="Created user details")
