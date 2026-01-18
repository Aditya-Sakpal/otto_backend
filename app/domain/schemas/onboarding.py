from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.domain.enums import UserRole

class ValidateGHLRequest(BaseModel):
    """Request schema for GHL validation."""
    location_id: str = Field(..., description="GHL location ID")
    api_key: str = Field(..., description="GHL API key")


class ValidateGHLResponse(BaseModel):
    """Response schema for GHL validation."""
    company_id: str = Field(..., description="GHL company ID")
    company_name: str = Field(..., description="GHL company name")


class OnboardingCompleteResponse(BaseModel):
    """Response schema for onboarding completion."""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    company_id: Optional[UUID]
    created_at: str
