"""
Insights API Schemas

Pydantic schemas for insights API request/response validation.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from ..models.enums import InsightType, ProcessingStatus
from ..models.insight import (
    CompanyInsightData,
    CustomerInsightData,
    ObjectionInsightData,
    TopPerformer,
    NeedsCoaching,
    WeekOverWeek,
    TrendData
)
from ..utils.uuid_validator import validate_uuid


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class InsightGenerationOptions(BaseModel):
    """Options for insight generation"""
    force_regenerate: bool = False
    include_inactive_customers: bool = False


class GenerateInsightsRequest(BaseModel):
    """Request to generate weekly insights"""
    week_start: Optional[date] = Field(None, description="Start date (defaults to last Monday)")
    week_end: Optional[date] = Field(None, description="End date (defaults to last Sunday)")
    company_ids: Optional[List[str]] = Field(None, description="Specific companies UUIDs (defaults to all active)")
    insight_types: List[InsightType] = Field(
        default_factory=lambda: [InsightType.COMPANY, InsightType.CUSTOMER, InsightType.OBJECTION],
        description="Types to generate"
    )
    webhook_url: Optional[HttpUrl] = Field(None, description="Callback URL when complete")
    options: InsightGenerationOptions = Field(default_factory=InsightGenerationOptions)
    
    @field_validator('company_ids')
    @classmethod
    def validate_company_ids(cls, v):
        if v is not None:
            # Validate each company_id is a UUID
            for company_id in v:
                validate_uuid(company_id, "company_id")
        return v
    
    class Config:
        use_enum_values = True


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class GenerateInsightsResponse(BaseModel):
    """Response after triggering insight generation"""
    job_id: str
    status: ProcessingStatus
    week_start: date
    week_end: date
    company_count: int
    insight_types: List[InsightType]
    estimated_duration: str
    status_url: str
    queued_at: datetime
    
    class Config:
        use_enum_values = True


class InsightGenerationProgress(BaseModel):
    """Progress information for insight generation"""
    percent: int = Field(..., ge=0, le=100)
    current_step: str
    companies_processed: int
    companies_total: int
    insights_generated: Dict[str, int] = Field(default_factory=dict)


class InsightGenerationResults(BaseModel):
    """Links to generated insights"""
    company_insights_url: str
    customer_insights_url: str
    objection_insights_url: str


class InsightJobStatusResponse(BaseModel):
    """Insight generation job status"""
    job_id: str
    status: ProcessingStatus
    week_start: date
    week_end: date
    progress: InsightGenerationProgress
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    estimated_completion: Optional[datetime] = None
    results: Optional[InsightGenerationResults] = None
    error: Optional[Dict[str, Any]] = None
    retry_available: bool = False
    retry_url: Optional[str] = None
    
    class Config:
        use_enum_values = True


# ============================================================================
# COMPANY INSIGHTS SCHEMAS
# ============================================================================

class CompanyInsightResponse(BaseModel):
    """Company insight response"""
    company_id: str
    week_start: date
    week_end: date
    data: CompanyInsightData
    generated_at: datetime


class CurrentCompanyInsightResponse(BaseModel):
    """Current week company insight"""
    company_id: str
    week_start: date
    week_end: date
    data: CompanyInsightData
    generated_at: datetime


# ============================================================================
# CUSTOMER INSIGHTS SCHEMAS
# ============================================================================

class CustomerInsightResponse(BaseModel):
    """Single customer insight"""
    customer_id: str
    company_id: str
    phone_number: str
    customer_name: Optional[str] = None
    week_start: date
    data: CustomerInsightData
    generated_at: datetime


class CustomerInsightListItem(BaseModel):
    """Customer insight list item (summary)"""
    customer_id: str
    phone_number: str
    customer_name: Optional[str] = None
    data: CustomerInsightData


class CustomersInsightsResponse(BaseModel):
    """List of customer insights"""
    company_id: str
    week_start: date
    total_customers: int
    page: int
    limit: int
    customers: List[CustomerInsightListItem]


# ============================================================================
# OBJECTION INSIGHTS SCHEMAS
# ============================================================================

class ObjectionInsightResponse(BaseModel):
    """Objection insights response"""
    company_id: str
    week_start: date
    week_end: date
    total_categories: int
    objections: List[ObjectionInsightData]
    generated_at: datetime


# ============================================================================
# QUERY PARAMS SCHEMAS
# ============================================================================

class CompanyInsightQueryParams(BaseModel):
    """Query params for company insights"""
    week_start: Optional[date] = None


class CustomerInsightsQueryParams(BaseModel):
    """Query params for customer insights list"""
    company_id: str = Field(..., description="Company identifier (UUID format required)")
    week_start: Optional[date] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=200)
    
    @field_validator('company_id')
    @classmethod
    def validate_company_id(cls, v):
        return validate_uuid(v, "company_id")


class ObjectionInsightsQueryParams(BaseModel):
    """Query params for objection insights"""
    week_start: Optional[date] = None
    category_id: Optional[int] = Field(None, ge=1, le=10)


# ============================================================================
# WEBHOOK PAYLOAD SCHEMAS
# ============================================================================

class InsightWebhookPayload(BaseModel):
    """Webhook payload sent when insights complete"""
    job_id: str
    status: ProcessingStatus
    week_start: date
    week_end: date
    companies_processed: int
    insights_generated: Dict[str, int]
    duration_seconds: int
    completed_at: datetime
    
    class Config:
        use_enum_values = True

