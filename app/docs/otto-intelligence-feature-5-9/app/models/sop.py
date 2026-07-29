"""
Otto Intelligence Service - SOP Models

MongoDB models for SOP document ingestion and metrics.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId

from app.models.enums import SOPType, SOPStatus, ChunkType


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class SOPFileInfo(BaseModel):
    """File information for uploaded SOP"""
    original_filename: str
    file_type: str
    file_size: int
    file_hash: str
    s3_key: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None


class SOPSection(BaseModel):
    """Section extracted from SOP document"""
    title: str
    content: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class SOPTable(BaseModel):
    """Table extracted from SOP document"""
    title: Optional[str] = None
    headers: List[str]
    rows: List[List[str]]


class ExtractedContent(BaseModel):
    """Content extracted from SOP document"""
    raw_text: str
    sections: List[SOPSection] = []
    tables: List[SOPTable] = []


class ProcessingMetadata(BaseModel):
    """Metadata about SOP processing"""
    job_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    chunks_created: int = 0
    vectors_indexed: int = 0


class EvaluationCriteria(BaseModel):
    """Evaluation criteria for a metric"""
    excellent: Optional[Dict[str, Any]] = None
    good: Optional[Dict[str, Any]] = None
    needs_improvement: Optional[Dict[str, Any]] = None
    poor: Optional[Dict[str, Any]] = None


class SOPMetric(BaseModel):
    """Individual performance metric"""
    metric_id: str
    metric_name: str
    description: str
    evaluation_method: str
    target_value: float = 1.0
    weight: float = 0.1
    applicable_roles: List[str] = []
    evaluation_criteria: Optional[Dict[str, Any]] = None
    source_section: Optional[str] = None
    category: Optional[str] = None


class SOPDocument(BaseModel):
    """SOP document in MongoDB"""
    sop_id: str
    company_id: str
    sop_name: str
    sop_type: SOPType
    target_role: Optional[str] = None
    is_company_wide: bool = False
    
    # Version control fields (per Q1-Q4)
    version: int = Field(default=1, description="Current version number (auto-incremented)")
    version_history_id: Optional[str] = Field(None, description="Reference to sop_version_history")
    activation_date: Optional[datetime] = Field(None, description="For scheduled activation")
    
    status: SOPStatus = SOPStatus.PROCESSING
    
    file_info: SOPFileInfo
    extracted_content: Optional[ExtractedContent] = None
    processing_metadata: Optional[ProcessingMetadata] = None
    
    metadata: Optional[Dict[str, Any]] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


class SOPMetricsDocument(BaseModel):
    """SOP metrics collection document"""
    sop_id: str
    company_id: str
    target_role: Optional[str] = None
    is_company_wide: bool = False
    status: SOPStatus = SOPStatus.ACTIVE
    
    metrics: List[SOPMetric] = []
    total_metrics: int = 0
    total_weight: float = 0.0
    
    categories: List[str] = []
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


class SOPChunk(BaseModel):
    """SOP chunk for vector indexing"""
    chunk_id: str
    sop_id: str
    company_id: str
    
    chunk_index: int
    chunk_type: ChunkType
    section_title: Optional[str] = None
    parent_section: Optional[str] = None
    
    text: str
    token_count: int
    
    milvus_id: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


class SOPMetricScore(BaseModel):
    """Individual metric score in call evaluation"""
    metric_id: str
    metric_name: str
    score: float
    target: float
    weight: float
    weighted_score: float
    rating: str
    evidence: Optional[str] = None
    improvement_suggestion: Optional[str] = None


class SOPImprovementArea(BaseModel):
    """Area needing improvement"""
    area: str
    suggestion: str
    current_score: float
    related_metrics: List[str] = []


class SOPEvaluation(BaseModel):
    """SOP-based evaluation for a call"""
    sop_id: str
    sop_name: str
    sop_version: Optional[int] = None  # Changed to int for version tracking
    sop_version_history_id: Optional[str] = None  # Reference for historical lookup
    
    overall_compliance: float
    
    metric_scores: List[SOPMetricScore] = []
    
    top_strengths: List[str] = []
    improvement_areas: List[SOPImprovementArea] = []
    
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


# ============================================================================
# SOP VERSION CONTROL MODELS (per Q1-Q9 decisions)
# ============================================================================

class SOPVersionHistory(BaseModel):
    """
    Historical record of SOP versions.
    
    Per manager decisions:
    - Q1: Version numbers are automatic (v1, v2, v3...)
    - Q2: Old versions are archived immediately on new upload
    - Q4: Scheduled activation supported with activation_date
    """
    history_id: str = Field(..., description="Unique version history ID")
    sop_id: str = Field(..., description="Reference to parent SOP")
    company_id: str
    version: int = Field(..., ge=1, description="Auto-incremented version number")
    sop_name: str
    
    # Version metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(None, description="Manager who uploaded")
    activation_date: Optional[datetime] = Field(None, description="Scheduled or immediate activation")
    archived_at: Optional[datetime] = None
    status: str = Field(default="active", description="active, archived, scheduled")
    
    # Full snapshot of metrics at this version
    metrics_snapshot: List[SOPMetric] = Field(default_factory=list)
    total_metrics: int = 0
    total_weight: float = 0.0
    
    # File reference
    file_hash: str = Field(..., description="SHA256 hash to detect duplicate uploads")
    original_filename: str

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


class CallReanalysis(BaseModel):
    """
    Store re-analysis results separately (per Q8: Store both original + re-analyzed).
    
    Per manager decisions:
    - Q5: No automatic re-analysis (manual trigger only)
    - Q6: Default lookback period is 14 days
    - Q7: Re-analyze ALL calls in selected period (not just failures)
    """
    reanalysis_id: str = Field(..., description="Unique reanalysis record ID")
    call_id: str
    company_id: str
    
    # Original evaluation
    original_sop_version: int
    original_sop_version_history_id: str
    original_compliance: dict = Field(default_factory=dict)
    original_overall_score: float
    original_evaluated_at: datetime
    
    # Re-analyzed evaluation
    new_sop_version: int
    new_sop_version_history_id: str
    new_compliance: dict = Field(default_factory=dict)
    new_overall_score: float
    reanalyzed_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Comparison metrics
    score_delta: float = Field(..., description="new_score - original_score")
    metrics_changed: List[str] = Field(default_factory=list, description="Which metrics were affected")
    improved_metrics: List[str] = Field(default_factory=list)
    declined_metrics: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True


class ReanalysisJob(BaseModel):
    """Track re-analysis job progress"""
    job_id: str
    sop_id: str
    company_id: str
    new_sop_version: int
    lookback_days: int = 14
    
    # Progress
    status: str = Field(default="queued", description="queued, processing, completed, failed")
    total_calls: int = 0
    processed_calls: int = 0
    failed_calls: int = 0
    
    # Results summary
    avg_score_change: Optional[float] = None
    calls_improved: int = 0
    calls_declined: int = 0
    calls_unchanged: int = 0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

