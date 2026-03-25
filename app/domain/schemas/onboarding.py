from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.domain.enums import UserRole

class ValidateGHLRequest(BaseModel):
    """Request schema for GoHighLevel (GHL) credential validation."""
    location_id: str = Field(..., description="GHL location ID")
    api_key: str = Field(..., description="GHL API key")

    model_config = {"json_schema_extra": {"example": {"location_id": "loc_abc123", "api_key": "ghl-api-key-xxxxx"}}}


class ValidateGHLResponse(BaseModel):
    """Response schema for GHL validation."""
    company_id: str = Field(..., description="GHL company ID")
    company_name: str = Field(..., description="GHL company name")


class ValidateCTMRequest(BaseModel):
    """Request schema for CallTrackingMetrics (CTM) credential validation."""
    access_key: str = Field(..., description="CTM access key")
    secret_key: str = Field(..., description="CTM secret key")

    model_config = {"json_schema_extra": {"example": {"access_key": "ctm-access-xxxxx", "secret_key": "ctm-secret-xxxxx"}}}


class ValidateCTMResponse(BaseModel):
    """Response schema for CTM validation."""
    secret_key: str = Field(..., description="CTM secret key (returned for confirmation)")
    company_name: str = Field(..., description="CTM company/account name")
    company_id: int = Field(..., description="CTM company/account ID")


class ValidateServiceTitanRequest(BaseModel):
    """Request schema for ServiceTitan credential validation."""
    tenant_id: str = Field(..., description="ServiceTitan tenant ID")
    client_id: str = Field(..., description="ServiceTitan client ID (OAuth2)")
    client_secret: str = Field(..., description="ServiceTitan client secret (OAuth2)")

    model_config = {"json_schema_extra": {"example": {"tenant_id": "12345", "client_id": "st-client-id", "client_secret": "st-client-secret"}}}


class ValidateServiceTitanResponse(BaseModel):
    """Response schema for ServiceTitan validation."""
    tenant_id: str = Field(..., description="ServiceTitan tenant ID")
    status: str = Field(..., description="Validation status")


class OnboardingCompleteResponse(BaseModel):
    """Response schema for onboarding completion. Matches LoginResponse format."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


# Avoid circular import — resolve forward ref
from app.domain.users.schemas import UserResponse  # noqa: E402

OnboardingCompleteResponse.model_rebuild()
