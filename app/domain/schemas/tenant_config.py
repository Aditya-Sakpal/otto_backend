"""
Tenant Configuration request/response schemas.

Typed sub-models give Swagger full visibility into the shape of each
configuration section, including defaults from Default_Tenant_Config.
"""
from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Qualification Thresholds
# ---------------------------------------------------------------------------


class QualificationThresholds(BaseModel):
    """Score thresholds that determine lead temperature (hot/warm/cold)."""

    hot_threshold: float = Field(
        0.75,
        description="Minimum overall score to classify a lead as HOT",
    )
    warm_threshold: float = Field(
        0.5,
        description="Minimum overall score to classify a lead as WARM (below hot)",
    )
    cold_threshold: float = Field(
        0.25,
        description="Minimum overall score to classify a lead as COLD (below warm)",
    )
    scoring_weights: Optional[Dict[str, float]] = Field(
        None,
        description="Weights for BANT dimensions, e.g. {\"need\": 0.3, \"budget\": 0.25, \"authority\": 0.2, \"timeline\": 0.25}",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "hot_threshold": 0.75,
                    "warm_threshold": 0.5,
                    "cold_threshold": 0.25,
                    "scoring_weights": {
                        "need": 0.3,
                        "budget": 0.25,
                        "authority": 0.2,
                        "timeline": 0.25,
                    },
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Qualification Rules
# ---------------------------------------------------------------------------


class QualificationRule(BaseModel):
    """A single qualification rule evaluated during call analysis."""

    rule_id: str = Field(..., description="Unique rule identifier, e.g. 'rule_001'")
    name: str = Field(..., description="Human-readable rule name")
    description: Optional[str] = Field(None, description="What this rule checks")
    condition: str = Field(
        ...,
        description="Condition expression evaluated against call data, e.g. 'bant.need >= 0.7 AND bant.timeline >= 0.5'",
    )
    action: str = Field(
        ...,
        description="Action to take when condition is met, e.g. 'set_status:hot', 'add_tag:urgent'",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rule_id": "rule_001",
                    "name": "High-intent lead",
                    "description": "Flag leads with strong need and short timeline",
                    "condition": "bant.need >= 0.7 AND bant.timeline >= 0.5",
                    "action": "set_status:hot",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Service Prioritization
# ---------------------------------------------------------------------------


class ServicePriority(BaseModel):
    """Priority configuration for a specific service the company offers."""

    service_name: str = Field("", description="Service name, e.g. 'Roof Replacement'")
    priority: str = Field(
        "NORMAL",
        description="Priority level: HIGH, NORMAL, or LOW",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_service_name(cls, data):
        """Accept 'service_type' as an alias for 'service_name' from legacy DB data."""
        if isinstance(data, dict) and "service_name" not in data and "service_type" in data:
            data["service_name"] = data.pop("service_type")
        return data

    model_config = {
        "json_schema_extra": {
            "examples": [{"service_name": "Roof Replacement", "priority": "HIGH"}]
        }
    }


class ServicePrioritization(BaseModel):
    """Controls how services are ranked and prioritised in analysis."""

    services: List[ServicePriority] = Field(
        default_factory=list,
        description="List of services with their priority levels",
    )
    default_priority: str = Field(
        "NORMAL",
        description="Default priority for services not explicitly listed",
    )


# ---------------------------------------------------------------------------
# Custom Keywords
# ---------------------------------------------------------------------------


class CustomKeywords(BaseModel):
    """Keyword lists that Shunya uses to detect signals during call analysis."""

    urgency_keywords: List[str] = Field(
        default_factory=list,
        description="Words indicating urgency, e.g. ['emergency', 'asap', 'leaking', 'urgent']",
    )
    budget_keywords: List[str] = Field(
        default_factory=list,
        description="Words indicating budget discussion, e.g. ['financing', 'insurance', 'cost', 'payment plan']",
    )
    objection_keywords: List[str] = Field(
        default_factory=list,
        description="Words indicating customer objections, e.g. ['too expensive', 'not interested', 'think about it']",
    )
    service_keywords: List[str] = Field(
        default_factory=list,
        description="Words for service detection, e.g. ['roof', 'gutter', 'leak', 'shingle']",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_keywords(cls, data):
        """Convert dict values to list for keyword fields (legacy DB data stores {} instead of [])."""
        if isinstance(data, dict):
            for field in ("urgency_keywords", "budget_keywords", "objection_keywords", "service_keywords"):
                val = data.get(field)
                if isinstance(val, dict):
                    data[field] = list(val.values()) if val else []
        return data

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "urgency_keywords": ["emergency", "asap", "leaking"],
                    "budget_keywords": ["financing", "insurance", "cost"],
                    "objection_keywords": ["too expensive", "not interested"],
                    "service_keywords": ["roof", "gutter", "leak"],
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Business Hours
# ---------------------------------------------------------------------------


class DaySchedule(BaseModel):
    """Operating hours for a single day of the week."""

    open: str = Field(..., description="Opening time in HH:MM format, e.g. '08:00'")
    close: str = Field(..., description="Closing time in HH:MM format, e.g. '18:00'")
    is_closed: bool = Field(False, description="If true, the business is closed this day")

    model_config = {
        "json_schema_extra": {
            "examples": [{"open": "08:00", "close": "18:00", "is_closed": False}]
        }
    }


class BusinessHours(BaseModel):
    """Company operating hours used for scheduling and call routing."""

    timezone: str = Field(
        "America/Phoenix",
        description="IANA timezone identifier, e.g. 'America/Phoenix', 'America/New_York'",
    )
    monday: Optional[DaySchedule] = Field(None, description="Monday hours")
    tuesday: Optional[DaySchedule] = Field(None, description="Tuesday hours")
    wednesday: Optional[DaySchedule] = Field(None, description="Wednesday hours")
    thursday: Optional[DaySchedule] = Field(None, description="Thursday hours")
    friday: Optional[DaySchedule] = Field(None, description="Friday hours")
    saturday: Optional[DaySchedule] = Field(None, description="Saturday hours")
    sunday: Optional[DaySchedule] = Field(None, description="Sunday hours")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timezone": "America/Phoenix",
                    "monday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "tuesday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "wednesday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "thursday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "friday": {"open": "08:00", "close": "18:00", "is_closed": False},
                    "saturday": {"open": "09:00", "close": "14:00", "is_closed": False},
                    "sunday": {"open": "00:00", "close": "00:00", "is_closed": True},
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------


class TenantConfigCreateRequest(BaseModel):
    """Request to create a tenant configuration.

    All configuration sections are optional — Shunya applies sensible defaults
    for any section not provided (see Default_Tenant_Config for full defaults).
    """

    company_id: UUID = Field(..., description="Company UUID (must exist in companies table)")
    company_name: str = Field(..., description="Display name of the company")
    qualification_thresholds: Optional[QualificationThresholds] = Field(
        None,
        description="Score thresholds for hot/warm/cold classification. Defaults: hot=0.75, warm=0.5, cold=0.25",
    )
    service_prioritization: Optional[ServicePrioritization] = Field(
        None,
        description="Service ranking and priority. Default: empty list, NORMAL priority",
    )
    custom_keywords: Optional[CustomKeywords] = Field(
        None,
        description="Keyword lists for urgency/budget/objection/service detection. Default: empty lists",
    )
    qualification_rules: Optional[List[QualificationRule]] = Field(
        None,
        description="Custom rules evaluated during call analysis. Default: empty list",
    )
    business_hours: Optional[BusinessHours] = Field(
        None,
        description="Operating hours and timezone. Default: Phoenix timezone, Mon-Fri 8-6, Sat 9-2, Sun closed",
    )
    service_area: Optional[List[str]] = Field(
        None,
        description="Geographic areas served, e.g. ['Phoenix', 'Scottsdale', 'Mesa']. Default: empty list",
    )
    industry: Optional[str] = Field(
        "home_services",
        description="Industry vertical. Currently supported: 'home_services'",
    )
    primary_services: Optional[List[str]] = Field(
        None,
        description="Primary services offered, e.g. ['Roof Replacement', 'Roof Repair', 'Gutter Installation']. Default: empty list",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "company_name": "Arizona Roofers Inc.",
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


class TenantConfigUpdateRequest(BaseModel):
    """Request to update a tenant configuration. Only non-null fields are applied."""

    company_name: Optional[str] = Field(None, description="Updated company display name")
    qualification_thresholds: Optional[QualificationThresholds] = Field(
        None, description="Updated score thresholds"
    )
    service_prioritization: Optional[ServicePrioritization] = Field(
        None, description="Updated service priorities"
    )
    custom_keywords: Optional[CustomKeywords] = Field(
        None, description="Updated keyword lists"
    )
    qualification_rules: Optional[List[QualificationRule]] = Field(
        None, description="Updated qualification rules"
    )
    business_hours: Optional[BusinessHours] = Field(
        None, description="Updated operating hours"
    )
    service_area: Optional[List[str]] = Field(
        None, description="Updated service areas"
    )
    industry: Optional[str] = Field(None, description="Updated industry vertical")
    primary_services: Optional[List[str]] = Field(
        None, description="Updated primary services"
    )


class TenantConfigResponse(BaseModel):
    """Tenant configuration response with all sections."""

    id: UUID = Field(..., description="Config record UUID")
    company_id: UUID = Field(..., description="Company UUID")
    company_name: str = Field(..., description="Company display name")
    shunya_config_id: Optional[str] = Field(
        None, description="Config ID on Shunya's side (internal reference)"
    )
    qualification_thresholds: Optional[QualificationThresholds] = Field(
        None, description="Score thresholds for lead temperature classification"
    )
    service_prioritization: Optional[ServicePrioritization] = Field(
        None, description="Service ranking and priority configuration"
    )
    custom_keywords: Optional[CustomKeywords] = Field(
        None, description="Keyword lists for signal detection"
    )
    qualification_rules: Optional[List[QualificationRule]] = Field(
        None, description="Custom rules evaluated during analysis"
    )
    business_hours: Optional[BusinessHours] = Field(
        None, description="Operating hours and timezone"
    )
    service_area: Optional[List[str]] = Field(
        None, description="Geographic areas served"
    )
    industry: Optional[str] = Field(None, description="Industry vertical")
    primary_services: Optional[List[str]] = Field(
        None, description="Primary services offered"
    )
    version: int = Field(..., description="Config version (increments on each update)")
    is_active: bool = Field(..., description="Whether this config is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}
