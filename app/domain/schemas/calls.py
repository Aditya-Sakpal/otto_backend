"""
Call and call-logs response schemas for API documentation.
"""
from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class CallLogsSummary(BaseModel):
    """Summary statistics for call logs."""
    total_calls: int = Field(..., description="Total calls in scope")
    qualified: int = Field(..., description="Count of qualified calls")
    booked: int = Field(..., description="Count of booked calls")
    abandoned: int = Field(..., description="Count of abandoned calls")


class CallLogEntry(BaseModel):
    """Single call log entry in the logs list."""
    call_id: str
    lead_id: Optional[str] = None
    call_received: Optional[str] = None
    duration: Optional[str] = None
    csr_name: Optional[str] = None
    answered_by_display: Optional[str] = None
    customer_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_qualified: Optional[bool] = None
    is_booked: Optional[bool] = None
    booking_status: Optional[str] = None
    is_service_offered: Optional[bool] = None
    is_existing_customer: Optional[bool] = None
    lead_source: Optional[str] = None
    audio_url: Optional[str] = None
    call_summary: Optional[str] = None
    key_items: Optional[List[Any]] = None
    action_items: Optional[List[Any]] = None
    score: Optional[float] = None
    objections: Optional[str] = None
    tags: Optional[str] = None
    transcript: Optional[str] = None


class CallLogsResponse(BaseModel):
    """Response for GET /calls/logs."""
    summary: CallLogsSummary = Field(..., description="Aggregate statistics")
    calls: List[CallLogEntry] = Field(..., description="Filtered list of call log entries")
    total: int = Field(..., description="Total count matching filters")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records returned")


# ============================================================================
# Recording Analysis Schemas (Post-Meeting Insights)
# ============================================================================


class PendingActionDetail(BaseModel):
    """Structured pending action extracted from call."""
    type: str = Field(..., description="Action type (e.g., send_info, follow_up_call)")
    owner: str = Field(..., description="Owner role (e.g., customer_rep, sales_rep)")
    raw_text: str = Field(..., description="Raw text of the action item")
    due_at: Optional[datetime] = Field(None, description="When the action is due")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")
    contact_method: Optional[str] = Field(None, description="Contact method (e.g., email, phone)")


class RecordingSummary(BaseModel):
    """Summary section of recording analysis."""
    summary: str = Field(..., description="Call summary text")
    key_points: List[str] = Field(default_factory=list, description="Key points from the call")
    pending_actions: List[PendingActionDetail] = Field(default_factory=list, description="Structured pending actions")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (0-1)")


class ObjectionDetail(BaseModel):
    """Detailed objection with category and handling information."""
    category_id: int = Field(..., description="Objection category ID")
    category_text: str = Field(..., description="Objection category name")
    objection_text: str = Field(..., description="The actual objection raised")
    overcome: bool = Field(..., description="Whether the objection was overcome")
    severity: str = Field(..., description="Severity level (low, medium, high)")
    confidence_score: float = Field(..., description="Confidence score (0-1)")
    response_suggestions: List[str] = Field(default_factory=list, description="Suggested responses for future")


class RecordingObjections(BaseModel):
    """Objections section of recording analysis."""
    objections: List[ObjectionDetail] = Field(default_factory=list, description="List of detailed objections")
    total_count: int = Field(..., description="Total number of objections detected")


class ComplianceStageDetail(BaseModel):
    """Compliance details for a specific SOP stage."""
    score: float = Field(..., description="Stage compliance score (0-1)")
    issues: List[str] = Field(default_factory=list, description="Issues identified in this stage")


class RecordingCompliance(BaseModel):
    """SOP compliance section of recording analysis."""
    score: float = Field(..., description="Overall SOP compliance score (0-1)")
    stages: Dict[str, ComplianceStageDetail] = Field(default_factory=dict, description="Compliance by stage")
    positive_behaviors: List[str] = Field(default_factory=list, description="Positive behaviors observed")
    issues: List[str] = Field(default_factory=list, description="Overall compliance issues")


class RecordingQualification(BaseModel):
    """Qualification section of recording analysis."""
    overall_score: float = Field(..., description="Overall qualification score (0-1)")
    bant_scores: Dict[str, float] = Field(default_factory=dict, description="BANT scores (need, budget, authority, timeline)")
    qualification_status: str = Field(..., description="Qualification status (e.g., warm, hot, cold)")


class RecordingLeadScore(BaseModel):
    """Lead scoring section of recording analysis."""
    total_score: int = Field(..., description="Total lead score (0-100)")
    lead_band: str = Field(..., description="Lead band/category (e.g., warm, hot)")


class RecordingAnalysisResponse(BaseModel):
    """Complete recording analysis response for post-meeting insights."""
    call_id: str = Field(..., description="Call UUID")
    status: str = Field(..., description="Analysis status (completed, pending, failed)")
    summary: RecordingSummary = Field(..., description="Summary with key points and actions")
    objections: RecordingObjections = Field(..., description="Objections detected and handled")
    compliance: RecordingCompliance = Field(..., description="SOP compliance details")
    qualification: RecordingQualification = Field(..., description="Qualification assessment")
    lead_score: RecordingLeadScore = Field(..., description="Lead scoring details")
