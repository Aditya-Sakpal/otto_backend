"""
User domain model.

Represents a user in the system.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import UserRole


class User(BaseModel):
    """
    User model.
    
    Represents a user in the system with email/password authentication.
    """
    id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether user account is active")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    company_id: Optional[UUID] = Field(None, description="Associated company ID")
    created_at: datetime = Field(..., description="Account creation timestamp")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")
    
    def has_role(self, role: UserRole) -> bool:
        """Check if user has a specific role."""
        return self.role == role

