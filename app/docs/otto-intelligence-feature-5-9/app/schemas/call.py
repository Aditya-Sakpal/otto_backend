"""
Call Processing API Schemas

Pydantic schemas for API request/response validation.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from ..models.call import (
    CallSummary,
    ChunkSummary,
    SummaryData,
    ComplianceData,
    ObjectionsData,
    QualificationData
)
from ..models.enums import ProcessingStatus
from ..utils.uuid_validator import validate_uuid


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ProcessingOptions(BaseModel):
    """Processing options"""
    skip_rag_indexing: bool = False
    skip_summary_generation: bool = False
    priority: str = Field("normal", pattern="^(normal|high|low)$")


class RepMetadata(BaseModel):
    """Required rep metadata for call processing"""
    rep_id: str = Field(..., description="Unique identifier for the sales representative")
    rep_name: str = Field(..., description="Display name of the representative")
    team: Optional[str] = Field(None, description="Team name for grouping analytics")
    campaign: Optional[str] = Field(None, description="Campaign or source identifier")
    
    class Config:
        extra = "allow"  # Allow additional fields


class ProcessCallRequest(BaseModel):
    """Request to process a call"""
    call_id: str = Field(..., description="Unique call identifier (string or UUID)")
    company_id: str = Field(..., description="Company/tenant identifier (UUID format required)")
    audio_url: str = Field(..., description="S3 URL to audio file")
    phone_number: str = Field(..., description="Customer phone number")
    rep_role: str = Field("customer_rep", description="Representative role: 'customer_rep' or 'sales_rep'")
    duration: Optional[int] = Field(None, ge=0, description="Call duration in seconds")
    call_date: Optional[datetime] = Field(None, description="When the call occurred")
    timezone: Optional[str] = Field("UTC", description="Timezone for call_date")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional: rep_id, rep_name, or metadata.agent.id, metadata.agent.name for progression/coaching")
    webhook_url: Optional[HttpUrl] = Field(None, description="Callback URL when processing completes")
    options: ProcessingOptions = Field(default_factory=ProcessingOptions)
    allow_reprocess: bool = Field(False, description="Allow reprocessing if call_id already exists")
    
    @field_validator('company_id')
    @classmethod
    def validate_company_id(cls, v):
        return validate_uuid(v, "company_id")
    
    @field_validator('metadata')
    @classmethod
    def validate_metadata_rep_info(cls, v):
        """
        Validate and normalize rep information from metadata when provided.
        
        Accepts two formats (all optional):
        1. Nested agent structure: metadata.agent.id and metadata.agent.name
        2. Flat structure (legacy): metadata.rep_id and metadata.rep_name
        
        When present, values must be non-empty strings. Normalizes to flat structure for internal use.
        """
        # Check for nested agent structure (current client format)
        agent = v.get('agent')
        if agent and isinstance(agent, dict):
            rep_id = agent.get('id')
            rep_name = agent.get('name')
            
            # Optional: only validate type when provided
            if rep_id is not None:
                if not isinstance(rep_id, str) or not rep_id.strip():
                    raise ValueError("metadata.agent.id must be a non-empty string when provided")
                v['rep_id'] = rep_id
            if rep_name is not None:
                if not isinstance(rep_name, str) or not rep_name.strip():
                    raise ValueError("metadata.agent.name must be a non-empty string when provided")
                v['rep_name'] = rep_name
            
            # Copy optional agent fields when present
            if agent.get('email'):
                v['rep_email'] = agent.get('email')
            if agent.get('pic_url'):
                v['rep_pic_url'] = agent.get('pic_url')
            
            return v
        
        # Flat structure (legacy): rep_id and rep_name are optional
        rep_id = v.get('rep_id')
        rep_name = v.get('rep_name')
        if rep_id is not None and (not isinstance(rep_id, str) or not rep_id.strip()):
            raise ValueError("metadata.rep_id must be a non-empty string when provided")
        if rep_name is not None and (not isinstance(rep_name, str) or not rep_name.strip()):
            raise ValueError("metadata.rep_name must be a non-empty string when provided")
        return v


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ProcessCallResponse(BaseModel):
    """Response after submitting call for processing"""
    job_id: str
    call_id: str
    status: ProcessingStatus
    message: str
    estimated_completion_time: Optional[datetime] = None
    status_url: str
    created_at: datetime
    
    class Config:
        use_enum_values = True


class ProgressInfo(BaseModel):
    """Processing progress information"""
    percent: int = Field(..., ge=0, le=100)
    current_step: str
    steps_completed: List[str] = Field(default_factory=list)
    steps_remaining: List[str] = Field(default_factory=list)
    steps_failed: List[str] = Field(default_factory=list)


class ProcessingResults(BaseModel):
    """Links to processing results"""
    summary_url: str
    chunks_url: str
    transcript_url: str


class ProcessingMetadata(BaseModel):
    """Processing metadata"""
    chunks_generated: int = 0
    summaries_generated: int = 0
    vectors_indexed: int = 0
    transcript_words: int = 0
    transcript_duration: int = 0


class ErrorInfo(BaseModel):
    """Error information"""
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Job status response"""
    job_id: str
    call_id: str
    status: ProcessingStatus
    progress: ProgressInfo
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    estimated_completion: Optional[datetime] = None
    results: Optional[ProcessingResults] = None
    metadata: Optional[ProcessingMetadata] = None
    error: Optional[ErrorInfo] = None
    retry_available: bool = False
    retry_url: Optional[str] = None
    
    class Config:
        use_enum_values = True


class CallSummaryResponse(BaseModel):
    """Call summary response"""
    call_id: str
    company_id: str
    status: str
    processed_at: datetime
    summary: SummaryData
    compliance: ComplianceData
    objections: ObjectionsData
    qualification: QualificationData


class ChunkInfo(BaseModel):
    """Chunk information for response"""
    chunk_id: str
    chunk_index: int
    summary: Dict[str, Any]
    milvus_id: Optional[str] = None
    created_at: datetime


class ChunksResponse(BaseModel):
    """Chunks response"""
    call_id: str
    total_chunks: int
    chunks: List[ChunkInfo]


class RetryJobRequest(BaseModel):
    """Request to retry failed job"""
    pass  # No body needed, job_id in path


class RetryJobResponse(BaseModel):
    """Response after retrying job"""
    job_id: str
    original_job_id: str
    call_id: str
    status: ProcessingStatus
    message: str
    retry_attempt: int
    status_url: str
    
    class Config:
        use_enum_values = True


# ============================================================================
# TRANSCRIPT SCHEMAS
# ============================================================================

class TranscriptSegment(BaseModel):
    """Transcript segment"""
    speaker: str
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class TranscriptResponse(BaseModel):
    """Transcript response"""
    call_id: str
    company_id: str
    full_transcript: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    duration: Optional[int] = None
    word_count: int
    created_at: datetime

