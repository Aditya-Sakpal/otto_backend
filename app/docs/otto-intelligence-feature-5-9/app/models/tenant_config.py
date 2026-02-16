"""
Tenant Configuration Model

Defines the data model for tenant-specific configuration including:
- Qualification rules and thresholds
- Service prioritization
- Custom keywords
- Business hours

Each tenant (company) can have custom settings that affect how calls are processed.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .enums import ServicePriority


class QualificationThresholds(BaseModel):
    """Thresholds for lead qualification status"""
    hot_min_score: float = Field(0.75, ge=0.0, le=1.0, description="Minimum score for 'hot' status")
    warm_min_score: float = Field(0.5, ge=0.0, le=1.0, description="Minimum score for 'warm' status")
    cold_min_score: float = Field(0.25, ge=0.0, le=1.0, description="Minimum score for 'cold' status")
    
    # BANT weights (should sum to 1.0)
    need_weight: float = Field(0.3, ge=0.0, le=1.0)
    budget_weight: float = Field(0.2, ge=0.0, le=1.0)
    authority_weight: float = Field(0.2, ge=0.0, le=1.0)
    timeline_weight: float = Field(0.3, ge=0.0, le=1.0)


class QualificationRule(BaseModel):
    """Custom qualification rule"""
    rule_id: str
    name: str
    description: str
    condition: str = Field(..., description="Python-evaluable condition using BANT scores and signals")
    action: str = Field(..., description="Action: boost_score, reduce_score, set_status, set_priority")
    action_value: Any = Field(None, description="Value for the action")
    priority: int = Field(0, description="Rule priority (higher = evaluated first)")
    enabled: bool = True
    
    class Config:
        json_schema_extra = {
            "example": {
                "rule_id": "emergency_boost",
                "name": "Emergency Leak Boost",
                "description": "Boost score for emergency leak situations",
                "condition": "'leak' in urgency_signals.lower() and 'emergency' in urgency_signals.lower()",
                "action": "set_status",
                "action_value": "hot",
                "priority": 100,
                "enabled": True
            }
        }


class ServiceConfig(BaseModel):
    """Configuration for a specific service type"""
    service_type: str = Field(..., description="Service type identifier")
    display_name: str
    priority: ServicePriority = ServicePriority.NORMAL
    current_wait_time_weeks: Optional[int] = None
    is_active: bool = True
    qualification_boost: float = Field(0.0, ge=-1.0, le=1.0, description="Score adjustment for this service")
    notes: Optional[str] = None


class ServicePrioritization(BaseModel):
    """Service prioritization rules"""
    services: List[ServiceConfig] = Field(default_factory=list)
    defer_low_ticket_during_high_demand: bool = False
    high_demand_threshold: Optional[int] = Field(None, description="Queue length triggering high demand mode")
    default_priority: ServicePriority = ServicePriority.NORMAL


class KeywordCategory(BaseModel):
    """Category of custom keywords"""
    category: str = Field(..., description="Category name: urgency, budget, objection, etc.")
    keywords: List[str] = Field(default_factory=list)
    phrases: List[str] = Field(default_factory=list, description="Multi-word phrases")
    effect: str = Field(..., description="What this keyword indicates: high_urgency, budget_available, etc.")
    score_impact: float = Field(0.0, ge=-1.0, le=1.0, description="Impact on relevant score")


class CustomKeywords(BaseModel):
    """Custom keywords and phrases for the tenant"""
    urgency_keywords: List[KeywordCategory] = Field(default_factory=list)
    budget_keywords: List[KeywordCategory] = Field(default_factory=list)
    objection_keywords: List[KeywordCategory] = Field(default_factory=list)
    service_keywords: Dict[str, List[str]] = Field(default_factory=dict, description="Keywords per service type")


class BusinessHours(BaseModel):
    """Business hours configuration"""
    timezone: str = "America/Phoenix"
    weekday_start: str = "08:00"
    weekday_end: str = "18:00"
    saturday_start: Optional[str] = "09:00"
    saturday_end: Optional[str] = "14:00"
    sunday_closed: bool = True
    holidays: List[str] = Field(default_factory=list, description="ISO date strings of holidays")


class PropertyDetailsConfig(BaseModel):
    """Configuration for property details extraction"""
    extract_roof_type: bool = True
    extract_roof_age: bool = True
    extract_hoa_status: bool = True
    extract_gated_status: bool = True
    extract_pets: bool = True
    extract_solar: bool = True
    custom_property_fields: List[str] = Field(default_factory=list)


class TenantConfiguration(BaseModel):
    """Complete tenant configuration"""
    config_id: str = Field(..., description="Unique configuration ID")
    company_id: str = Field(..., description="Company/tenant identifier")
    company_name: str
    
    # Qualification Configuration
    qualification_thresholds: QualificationThresholds = Field(default_factory=QualificationThresholds)
    qualification_rules: List[QualificationRule] = Field(default_factory=list)
    
    # Service Configuration
    service_prioritization: ServicePrioritization = Field(default_factory=ServicePrioritization)
    
    # Keywords Configuration
    custom_keywords: CustomKeywords = Field(default_factory=CustomKeywords)
    
    # Business Configuration
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    service_area: List[str] = Field(default_factory=list, description="List of serviced zip codes or cities")
    
    # Property Details Configuration
    property_details_config: PropertyDetailsConfig = Field(default_factory=PropertyDetailsConfig)
    
    # Industry Context
    industry: str = Field("home_services", description="Industry type")
    primary_services: List[str] = Field(default_factory=list, description="Main services offered")
    
    # Metadata
    version: int = Field(1, description="Configuration version for rollback")
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    class Config:
        use_enum_values = True


def get_default_tenant_config(company_id: str, company_name: str = "Unknown Company") -> TenantConfiguration:
    """
    Get default tenant configuration.
    
    Used when no specific tenant config exists.
    """
    return TenantConfiguration(
        config_id=f"default_{company_id}",
        company_id=company_id,
        company_name=company_name,
        qualification_thresholds=QualificationThresholds(),
        qualification_rules=[],
        service_prioritization=ServicePrioritization(
            services=[
                ServiceConfig(
                    service_type="general",
                    display_name="General Service",
                    priority=ServicePriority.NORMAL
                )
            ]
        ),
        custom_keywords=CustomKeywords(),
        business_hours=BusinessHours(),
        property_details_config=PropertyDetailsConfig(),
        industry="home_services",
        primary_services=["general"]
    )

