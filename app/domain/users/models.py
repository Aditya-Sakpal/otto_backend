"""
User domain model.

Represents a user in the system with JWT-based authentication.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import UserRole


class User(BaseModel):
    """
    User domain model.
    
    Represents a user with JWT-based authentication.
    """
    id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="User email (unique)")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(default=True, description="Whether user account is active")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    company_id: Optional[UUID] = Field(None, description="Associated company ID")
    created_at: datetime = Field(..., description="Account creation timestamp")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")
    
    # Password hash is NOT included in domain model (security)
    # It's only stored in the ORM layer
    
    def has_role(self, role: UserRole) -> bool:
        """Check if user has a specific role."""
        return self.role == role

