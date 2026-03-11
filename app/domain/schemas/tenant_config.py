"""
Tenant Configuration request/response schemas.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class TenantConfigCreateRequest(BaseModel):
    """Request to create a tenant configuration."""
    company_id: UUID
    company_name: str
    qualification_thresholds: Optional[Dict[str, Any]] = None
    service_prioritization: Optional[Dict[str, Any]] = None
    custom_keywords: Optional[Dict[str, Any]] = None
    qualification_rules: Optional[List[Dict[str, Any]]] = None
    business_hours: Optional[Dict[str, Any]] = None
    service_area: Optional[List[str]] = None
    industry: Optional[str] = "home_services"
    primary_services: Optional[List[str]] = None


class TenantConfigUpdateRequest(BaseModel):
    """Request to update a tenant configuration."""
    company_name: Optional[str] = None
    qualification_thresholds: Optional[Dict[str, Any]] = None
    service_prioritization: Optional[Dict[str, Any]] = None
    custom_keywords: Optional[Dict[str, Any]] = None
    qualification_rules: Optional[List[Dict[str, Any]]] = None
    business_hours: Optional[Dict[str, Any]] = None
    service_area: Optional[List[str]] = None
    industry: Optional[str] = None
    primary_services: Optional[List[str]] = None


class TenantConfigResponse(BaseModel):
    """Tenant configuration response."""
    id: UUID
    company_id: UUID
    company_name: str
    shunya_config_id: Optional[str] = None
    qualification_thresholds: Optional[Dict[str, Any]] = None
    service_prioritization: Optional[Dict[str, Any]] = None
    custom_keywords: Optional[Dict[str, Any]] = None
    qualification_rules: Optional[List[Dict[str, Any]]] = None
    business_hours: Optional[Dict[str, Any]] = None
    service_area: Optional[List[str]] = None
    industry: Optional[str] = None
    primary_services: Optional[List[str]] = None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
