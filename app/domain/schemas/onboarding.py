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


class ValidateCTMRequest(BaseModel):
    """Request schema for CTM validation."""
    access_key: str = Field(..., description="CTM access key")
    secret_key: str = Field(..., description="CTM secret key")


class ValidateCTMResponse(BaseModel):
    """Response schema for CTM validation."""
    secret_key: str = Field(..., description="CTM secret key (returned for confirmation)")
    company_name: str = Field(..., description="CTM company/account name")
    company_id: int = Field(..., description="CTM company/account ID")


class ValidateServiceTitanRequest(BaseModel):
    """Request schema for ServiceTitan validation."""
    tenant_id: str = Field(..., description="ServiceTitan tenant ID")
    client_id: str = Field(..., description="ServiceTitan client ID")
    client_secret: str = Field(..., description="ServiceTitan client secret")


class ValidateServiceTitanResponse(BaseModel):
    """Response schema for ServiceTitan validation."""
    tenant_id: str = Field(..., description="ServiceTitan tenant ID")
    status: str = Field(..., description="Validation status")


class OnboardingCompleteResponse(BaseModel):
    """Response schema for onboarding completion."""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    company_id: Optional[UUID]
    created_at: str
