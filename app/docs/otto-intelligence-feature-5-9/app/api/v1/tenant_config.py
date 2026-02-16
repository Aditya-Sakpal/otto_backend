"""
Tenant Configuration API

Endpoints for managing tenant-specific configurations including:
- Qualification rules and thresholds
- Service prioritization
- Custom keywords
- Business hours
"""

from fastapi import APIRouter, HTTPException, Depends, Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from ...core.database import get_database
from ...services.tenant_config_service import TenantConfigService
from ...models.tenant_config import (
    TenantConfiguration,
    QualificationThresholds,
    QualificationRule,
    ServiceConfig,
    ServicePrioritization,
    CustomKeywords,
    BusinessHours,
    PropertyDetailsConfig
)
from ...utils.uuid_validator import validate_uuid

router = APIRouter(prefix="/api/v1/tenant-config", tags=["Tenant Configuration"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class TenantConfigCreateRequest(BaseModel):
    """Request to create tenant configuration"""
    company_id: str = Field(..., description="Company identifier (UUID format)")
    company_name: str
    qualification_thresholds: Optional[Dict[str, Any]] = None
    qualification_rules: Optional[List[Dict[str, Any]]] = None
    service_prioritization: Optional[Dict[str, Any]] = None
    custom_keywords: Optional[Dict[str, Any]] = None
    business_hours: Optional[Dict[str, Any]] = None
    property_details_config: Optional[Dict[str, Any]] = None
    service_area: Optional[List[str]] = None
    industry: str = "home_services"
    primary_services: Optional[List[str]] = None
    
    @field_validator('company_id')
    @classmethod
    def validate_company_id(cls, v):
        return validate_uuid(v, "company_id")


class TenantConfigUpdateRequest(BaseModel):
    """Request to update tenant configuration"""
    company_name: Optional[str] = None
    qualification_thresholds: Optional[Dict[str, Any]] = None
    qualification_rules: Optional[List[Dict[str, Any]]] = None
    service_prioritization: Optional[Dict[str, Any]] = None
    custom_keywords: Optional[Dict[str, Any]] = None
    business_hours: Optional[Dict[str, Any]] = None
    property_details_config: Optional[Dict[str, Any]] = None
    service_area: Optional[List[str]] = None


class QualificationRuleRequest(BaseModel):
    """Request to add/update a qualification rule"""
    rule_id: str
    name: str
    description: str
    condition: str = Field(..., description="Python-evaluable condition")
    action: str = Field(..., description="Action: boost_score, reduce_score, set_status, set_priority, flag")
    action_value: Any
    priority: int = 0
    enabled: bool = True


class ServiceConfigRequest(BaseModel):
    """Request to add/update a service configuration"""
    service_type: str
    display_name: str
    priority: str = "normal"
    current_wait_time_weeks: Optional[int] = None
    is_active: bool = True
    qualification_boost: float = 0.0
    notes: Optional[str] = None


class TenantConfigResponse(BaseModel):
    """Tenant configuration response"""
    config_id: str
    company_id: str
    company_name: str
    qualification_thresholds: Dict[str, Any]
    qualification_rules: List[Dict[str, Any]]
    service_prioritization: Dict[str, Any]
    custom_keywords: Dict[str, Any]
    business_hours: Dict[str, Any]
    property_details_config: Dict[str, Any]
    service_area: List[str]
    industry: str
    primary_services: List[str]
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConfigHistoryResponse(BaseModel):
    """Configuration history entry"""
    version: int
    updated_at: datetime
    updated_by: Optional[str]
    changes_summary: Optional[str]


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/", response_model=TenantConfigResponse, status_code=201)
async def create_tenant_config(
    request: TenantConfigCreateRequest,
    db=Depends(get_database)
):
    """
    Create a new tenant configuration.
    
    This creates a custom configuration for a company/tenant that controls
    how their calls are processed, including qualification rules, service
    priorities, and custom keywords.
    """
    service = TenantConfigService(db)
    
    try:
        # Build kwargs from request
        kwargs = {}
        if request.qualification_thresholds:
            kwargs["qualification_thresholds"] = QualificationThresholds(**request.qualification_thresholds)
        if request.qualification_rules:
            kwargs["qualification_rules"] = [QualificationRule(**r) for r in request.qualification_rules]
        if request.service_prioritization:
            sp_data = request.service_prioritization
            if "services" in sp_data:
                sp_data["services"] = [ServiceConfig(**s) for s in sp_data["services"]]
            kwargs["service_prioritization"] = ServicePrioritization(**sp_data)
        if request.custom_keywords:
            kwargs["custom_keywords"] = CustomKeywords(**request.custom_keywords)
        if request.business_hours:
            kwargs["business_hours"] = BusinessHours(**request.business_hours)
        if request.property_details_config:
            kwargs["property_details_config"] = PropertyDetailsConfig(**request.property_details_config)
        if request.service_area:
            kwargs["service_area"] = request.service_area
        if request.primary_services:
            kwargs["primary_services"] = request.primary_services
        kwargs["industry"] = request.industry
        
        config = await service.create_config(
            company_id=request.company_id,
            company_name=request.company_name,
            **kwargs
        )
        
        return TenantConfigResponse(
            config_id=config.config_id,
            company_id=config.company_id,
            company_name=config.company_name,
            qualification_thresholds=config.qualification_thresholds.model_dump(),
            qualification_rules=[r.model_dump() for r in config.qualification_rules],
            service_prioritization=config.service_prioritization.model_dump(),
            custom_keywords=config.custom_keywords.model_dump(),
            business_hours=config.business_hours.model_dump(),
            property_details_config=config.property_details_config.model_dump(),
            service_area=config.service_area,
            industry=config.industry,
            primary_services=config.primary_services,
            version=config.version,
            is_active=config.is_active,
            created_at=config.created_at,
            updated_at=config.updated_at
        )
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create configuration: {str(e)}")


@router.get("/{company_id}", response_model=TenantConfigResponse)
async def get_tenant_config(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    db=Depends(get_database)
):
    """
    Get tenant configuration.
    
    Returns the configuration for the specified company, or a default
    configuration if none exists.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    service = TenantConfigService(db)
    config = await service.get_config(company_id)
    
    return TenantConfigResponse(
        config_id=config.config_id,
        company_id=config.company_id,
        company_name=config.company_name,
        qualification_thresholds=config.qualification_thresholds.model_dump(),
        qualification_rules=[r.model_dump() if hasattr(r, 'model_dump') else r for r in config.qualification_rules],
        service_prioritization=config.service_prioritization.model_dump(),
        custom_keywords=config.custom_keywords.model_dump(),
        business_hours=config.business_hours.model_dump(),
        property_details_config=config.property_details_config.model_dump(),
        service_area=config.service_area,
        industry=config.industry,
        primary_services=config.primary_services,
        version=config.version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at
    )


@router.put("/{company_id}", response_model=TenantConfigResponse)
async def update_tenant_config(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    request: TenantConfigUpdateRequest = ...,
    db=Depends(get_database)
):
    """
    Update tenant configuration.
    
    Updates only the provided fields. Previous versions are archived
    for rollback capability.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    service = TenantConfigService(db)
    
    # Build updates dict from non-None fields
    updates = {}
    
    if request.company_name is not None:
        updates["company_name"] = request.company_name
    
    if request.qualification_thresholds is not None:
        updates["qualification_thresholds"] = request.qualification_thresholds
    
    if request.qualification_rules is not None:
        updates["qualification_rules"] = request.qualification_rules
    
    if request.service_prioritization is not None:
        updates["service_prioritization"] = request.service_prioritization
    
    if request.custom_keywords is not None:
        updates["custom_keywords"] = request.custom_keywords
    
    if request.business_hours is not None:
        updates["business_hours"] = request.business_hours
    
    if request.property_details_config is not None:
        updates["property_details_config"] = request.property_details_config
    
    if request.service_area is not None:
        updates["service_area"] = request.service_area
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    config = await service.update_config(company_id, updates)
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuration for {company_id} not found")
    
    return TenantConfigResponse(
        config_id=config.config_id,
        company_id=config.company_id,
        company_name=config.company_name,
        qualification_thresholds=config.qualification_thresholds.model_dump() if hasattr(config.qualification_thresholds, 'model_dump') else config.qualification_thresholds,
        qualification_rules=[r.model_dump() if hasattr(r, 'model_dump') else r for r in config.qualification_rules],
        service_prioritization=config.service_prioritization.model_dump() if hasattr(config.service_prioritization, 'model_dump') else config.service_prioritization,
        custom_keywords=config.custom_keywords.model_dump() if hasattr(config.custom_keywords, 'model_dump') else config.custom_keywords,
        business_hours=config.business_hours.model_dump() if hasattr(config.business_hours, 'model_dump') else config.business_hours,
        property_details_config=config.property_details_config.model_dump() if hasattr(config.property_details_config, 'model_dump') else config.property_details_config,
        service_area=config.service_area,
        industry=config.industry,
        primary_services=config.primary_services,
        version=config.version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at
    )


@router.delete("/{company_id}")
async def delete_tenant_config(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    db=Depends(get_database)
):
    """
    Delete tenant configuration (soft delete).
    
    Marks the configuration as inactive. The company will use default
    configuration after deletion.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    service = TenantConfigService(db)
    deleted = await service.delete_config(company_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Configuration for {company_id} not found")
    
    return {"message": f"Configuration for {company_id} has been deleted", "company_id": company_id}


@router.get("/{company_id}/history", response_model=List[ConfigHistoryResponse])
async def get_config_history(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    limit: int = 10,
    db=Depends(get_database)
):
    """
    Get configuration version history.
    
    Returns the history of configuration changes for rollback review.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    cursor = db.tenant_configurations_history.find(
        {"company_id": company_id}
    ).sort("_archived_at", -1).limit(limit)
    
    history = []
    async for doc in cursor:
        history.append(ConfigHistoryResponse(
            version=doc.get("version", 0),
            updated_at=doc.get("_archived_at", doc.get("updated_at")),
            updated_by=doc.get("updated_by"),
            changes_summary=None  # Could be computed by comparing versions
        ))
    
    return history


@router.post("/{company_id}/rollback/{version}")
async def rollback_config(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    version: int = Path(..., description="Version number to rollback to"),
    db=Depends(get_database)
):
    """
    Rollback configuration to a previous version.
    
    Restores the configuration to the specified version number.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Find the historical version
    historical = await db.tenant_configurations_history.find_one({
        "company_id": company_id,
        "version": version
    })
    
    if not historical:
        raise HTTPException(
            status_code=404, 
            detail=f"Version {version} not found for {company_id}"
        )
    
    # Archive current version
    current = await db.tenant_configurations.find_one({"company_id": company_id})
    if current:
        current["_archived_at"] = datetime.utcnow()
        await db.tenant_configurations_history.insert_one(current)
    
    # Restore historical version
    historical.pop("_id", None)
    historical.pop("_archived_at", None)
    historical["updated_at"] = datetime.utcnow()
    historical["version"] = (current.get("version", 0) + 1) if current else version + 1
    
    await db.tenant_configurations.replace_one(
        {"company_id": company_id},
        historical,
        upsert=True
    )
    
    # Invalidate cache
    service = TenantConfigService(db)
    service.invalidate_cache(company_id)
    
    return {
        "message": f"Configuration rolled back to version {version}",
        "company_id": company_id,
        "new_version": historical["version"]
    }


@router.post("/{company_id}/rules", status_code=201)
async def add_qualification_rule(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    rule: QualificationRuleRequest = ...,
    db=Depends(get_database)
):
    """
    Add a new qualification rule to the tenant configuration.
    
    Rules are evaluated in priority order during call processing.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    service = TenantConfigService(db)
    config = await service.get_config(company_id)
    
    # Check if config exists (not just default)
    existing = await db.tenant_configurations.find_one({"company_id": company_id})
    if not existing:
        raise HTTPException(
            status_code=404, 
            detail=f"No configuration found for {company_id}. Create one first."
        )
    
    # Add the new rule
    new_rule = QualificationRule(**rule.model_dump())
    rules = [r.model_dump() if hasattr(r, 'model_dump') else r for r in config.qualification_rules]
    
    # Check for duplicate rule_id
    if any(r.get("rule_id") == rule.rule_id for r in rules):
        raise HTTPException(status_code=409, detail=f"Rule {rule.rule_id} already exists")
    
    rules.append(new_rule.model_dump())
    
    await service.update_config(company_id, {"qualification_rules": rules})
    
    return {"message": f"Rule {rule.rule_id} added", "rule": new_rule.model_dump()}


@router.post("/{company_id}/services", status_code=201)
async def add_service_config(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    service_config: ServiceConfigRequest = ...,
    db=Depends(get_database)
):
    """
    Add a new service configuration to the tenant.
    
    Services control prioritization and scoring adjustments.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    service = TenantConfigService(db)
    config = await service.get_config(company_id)
    
    # Check if config exists
    existing = await db.tenant_configurations.find_one({"company_id": company_id})
    if not existing:
        raise HTTPException(
            status_code=404, 
            detail=f"No configuration found for {company_id}. Create one first."
        )
    
    # Get current services
    sp = config.service_prioritization
    services = [s.model_dump() if hasattr(s, 'model_dump') else s for s in sp.services]
    
    # Check for duplicate
    if any(s.get("service_type") == service_config.service_type for s in services):
        raise HTTPException(
            status_code=409, 
            detail=f"Service {service_config.service_type} already exists"
        )
    
    # Add new service
    new_service = ServiceConfig(**service_config.model_dump())
    services.append(new_service.model_dump())
    
    await service.update_config(
        company_id, 
        {"service_prioritization": {"services": services, **sp.model_dump()}}
    )
    
    return {"message": f"Service {service_config.service_type} added", "service": new_service.model_dump()}

