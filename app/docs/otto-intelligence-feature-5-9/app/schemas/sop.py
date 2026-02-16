"""
Otto Intelligence Service - SOP Schemas

Pydantic schemas for SOP API requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

from app.models.enums import SOPType, SOPStatus, ProcessingStatus
from app.utils.uuid_validator import validate_uuid


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class SOPUploadRequest(BaseModel):
    """Request schema for SOP document upload"""
    company_id: str = Field(..., description="Company identifier (UUID format required)")
    target_role: Optional[str] = Field(None, description="Target role (null for company-wide)")
    sop_name: str = Field(..., description="SOP document name")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for completion callback")
    
    @field_validator('company_id')
    @classmethod
    def validate_company_id(cls, v):
        return validate_uuid(v, "company_id")


class SOPStatusUpdateRequest(BaseModel):
    """Request schema for updating SOP status"""
    status: SOPStatus = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for status change")


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class SOPUploadResponse(BaseModel):
    """Response schema for SOP document upload"""
    job_id: str
    status: ProcessingStatus
    message: str
    file_name: str
    file_size: int
    status_url: str
    created_at: datetime


class SOPProgressInfo(BaseModel):
    """Progress information for SOP processing"""
    percent: int
    current_step: str
    steps_completed: List[str] = []
    steps_remaining: List[str] = []


class SOPProcessingResults(BaseModel):
    """Results of SOP processing"""
    sop_id: str
    sop_name: str
    sop_type: SOPType
    is_company_wide: bool
    target_role: Optional[str] = None
    metrics_extracted: int
    chunks_indexed: int
    page_count: int
    word_count: int


class SOPStatusResponse(BaseModel):
    """Response schema for SOP processing status"""
    job_id: str
    status: ProcessingStatus
    progress: SOPProgressInfo
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    results: Optional[SOPProcessingResults] = None
    error: Optional[Dict[str, Any]] = None


class MetricResponse(BaseModel):
    """Response schema for individual metric"""
    metric_id: str
    metric_name: str
    description: str
    evaluation_method: str
    target_value: float
    weight: float
    applicable_roles: List[str]
    evaluation_criteria: Optional[Dict[str, Any]] = None


class SOPMetricsResponse(BaseModel):
    """Response schema for SOP metrics"""
    sop_id: str
    sop_name: str
    sop_type: SOPType
    target_role: Optional[str] = None
    is_company_wide: bool
    version: Optional[int] = None
    total_metrics: int
    metrics: List[MetricResponse]
    created_at: datetime
    status: SOPStatus


class CompanySOPMetricsResponse(BaseModel):
    """Response schema for company SOP metrics"""
    company_id: str
    active_sops: List[SOPMetricsResponse]
    company_wide_sops: List[SOPMetricsResponse]


class SOPSectionInfo(BaseModel):
    """Section information"""
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class MetricCategorySummary(BaseModel):
    """Metrics by category"""
    category: str
    count: int


class SOPDocumentResponse(BaseModel):
    """Response schema for SOP document details"""
    sop_id: str
    company_id: str
    sop_name: str
    sop_type: SOPType
    target_role: Optional[str] = None
    is_company_wide: bool
    
    file_info: Dict[str, Any]
    sections: List[SOPSectionInfo] = []
    
    metrics_summary: Dict[str, Any]
    
    status: SOPStatus
    version: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class SOPListItem(BaseModel):
    """List item for SOP documents"""
    sop_id: str
    sop_name: str
    sop_type: SOPType
    target_role: Optional[str] = None
    is_company_wide: bool
    status: SOPStatus
    version: Optional[int] = None
    metrics_count: int
    created_at: datetime


class SOPListResponse(BaseModel):
    """Response schema for SOP document list"""
    company_id: str
    total: int
    page: int
    limit: int
    documents: List[SOPListItem]


class SOPStatusUpdateResponse(BaseModel):
    """Response schema for SOP status update"""
    sop_id: str
    previous_status: SOPStatus
    new_status: SOPStatus
    updated_at: datetime


# ============================================================================
# SOP EVALUATION SCHEMAS (for call processing integration)
# ============================================================================

class MetricScoreResponse(BaseModel):
    """Individual metric score"""
    metric_id: str
    metric_name: str
    score: float
    target: float
    weight: float
    weighted_score: float
    rating: str
    evidence: Optional[str] = None
    improvement_suggestion: Optional[str] = None


class ImprovementAreaResponse(BaseModel):
    """Improvement area"""
    area: str
    suggestion: str
    current_score: float


class SOPEvaluationResponse(BaseModel):
    """SOP evaluation for a call"""
    sop_id: str
    sop_name: str
    sop_version: Optional[int] = None
    sop_version_history_id: Optional[str] = None
    overall_compliance: float
    metric_scores: List[MetricScoreResponse]
    top_strengths: List[str]
    improvement_areas: List[ImprovementAreaResponse]
    evaluated_at: datetime


# ============================================================================
# ERROR RESPONSE SCHEMAS
# ============================================================================

class SOPErrorDetail(BaseModel):
    """Detailed error information"""
    rejection_reason: Optional[str] = None
    confidence: Optional[float] = None
    suggestions: List[str] = []


class SOPErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[SOPErrorDetail] = None

