from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.domain.enums import UserRole
from app.domain.schemas.tenant_config import (
    QualificationThresholds,
    ServicePrioritization,
    CustomKeywords,
    QualificationRule,
    BusinessHours,
)

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


class OnboardingTenantConfigPayload(BaseModel):
    """Optional tenant-config sections accepted during onboarding."""

    qualification_thresholds: Optional[QualificationThresholds] = None
    service_prioritization: Optional[ServicePrioritization] = None
    custom_keywords: Optional[CustomKeywords] = None
    qualification_rules: Optional[List[QualificationRule]] = None
    business_hours: Optional[BusinessHours] = None
    service_area: Optional[List[str]] = None
    industry: Optional[str] = "home_services"
    primary_services: Optional[List[str]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "qualification_thresholds": {
                    "hot_threshold": 0.8,
                    "warm_threshold": 0.55,
                    "cold_threshold": 0.3,
                    "scoring_weights": {
                        "need": 0.3,
                        "budget": 0.2,
                        "authority": 0.2,
                        "timeline": 0.3,
                    },
                },
                "service_prioritization": {
                    "services": [
                        {
                            "service_type": "roof_replacement",
                            "display_name": "Roof Replacement",
                            "priority": "high",
                        },
                        {
                            "service_type": "roof_repair",
                            "display_name": "Roof Repair",
                            "priority": "deferred",
                        },
                    ],
                    "default_priority": "normal",
                },
                "custom_keywords": {
                    "urgency_keywords": [
                        "monsoon",
                        "rainy season",
                        "before summer",
                        "emergency",
                        "leak",
                    ],
                    "budget_keywords": ["insurance", "claim", "adjuster"],
                    "objection_keywords": ["too expensive", "call me later"],
                    "service_keywords": [
                        "new roof",
                        "full replacement",
                        "tear off",
                        "patch",
                        "fix",
                        "repair",
                        "small job",
                    ],
                },
                "qualification_rules": [
                    {
                        "rule_id": "emergency_leak_boost",
                        "name": "Emergency Leak Priority",
                        "description": "Boost score for emergency leak situations",
                        "condition": "'leak' in urgency_signals and 'emergency' in urgency_signals",
                        "action": "set_status:hot",
                    }
                ],
                "business_hours": {
                    "timezone": "America/Phoenix",
                    "monday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "tuesday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "wednesday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "thursday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "friday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "saturday": {"open": "09:00", "close": "14:00", "is_closed": False},
                    "sunday": {"open": "00:00", "close": "00:00", "is_closed": True},
                },
                "service_area": ["85001", "85002", "Phoenix", "Scottsdale", "Tempe"],
                "industry": "home_services",
                "primary_services": [
                    "roofing_repair",
                    "roofing_replacement",
                    "roofing_inspection",
                ],
            }
        }
    }


class OnboardingCompleteResponse(BaseModel):
    """Response schema for onboarding completion. Matches LoginResponse format."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


# Avoid circular import — resolve forward ref
from app.domain.users.schemas import UserResponse  # noqa: E402

OnboardingCompleteResponse.model_rebuild()
