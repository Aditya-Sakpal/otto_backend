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

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_calls": 150,
                "qualified": 85,
                "booked": 42,
                "abandoned": 12,
            }
        }
    }


class CallLogEntry(BaseModel):
    """Single call log entry in the logs list."""
    call_id: str = Field(..., description="UUID of the call")
    lead_id: Optional[str] = Field(None, description="UUID of the associated lead")
    call_received: Optional[str] = Field(None, description="Formatted date/time when call was received (e.g. 'Mar 15, 2026 10:30 AM')")
    duration: Optional[str] = Field(None, description="Formatted call duration (e.g. '2m 13s')")
    csr_name: Optional[str] = Field(None, description="Name of the CSR who handled the call")
    answered_by_display: Optional[str] = Field(None, description="Display name of who answered the call")
    customer_name: Optional[str] = Field(None, description="Customer name (uppercase)")
    phone_number: Optional[str] = Field(None, description="Formatted phone number (e.g. '(555) 123-4567')")
    is_qualified: Optional[bool] = Field(None, description="Whether call was qualified")
    is_booked: Optional[bool] = Field(None, description="Whether call resulted in a booking")
    booking_status: Optional[str] = Field(None, description="Booking status text")
    is_service_offered: Optional[bool] = Field(None, description="Whether the service was offered")
    is_existing_customer: Optional[bool] = Field(None, description="Whether this is an existing customer")
    lead_source: Optional[str] = Field(None, description="Lead source identifier")
    audio_url: Optional[str] = Field(None, description="URL to the call audio recording")
    call_summary: Optional[str] = Field(None, description="AI-generated call summary")
    key_items: Optional[List[Any]] = Field(None, description="Key items extracted from the call")
    action_items: Optional[List[Any]] = Field(None, description="Action items extracted from the call")
    score: Optional[float] = Field(None, description="Call score (SOP compliance or sentiment, 0-1)")
    objections: Optional[str] = Field(None, description="Comma-separated list of objection types")
    tags: Optional[str] = Field(None, description="Comma-separated list of tags")
    transcript: Optional[str] = Field(None, description="Full call transcript text")

    model_config = {
        "json_schema_extra": {
            "example": {
                "call_id": "ede64a3e-cb73-44c4-94cc-35af4a95b0ac",
                "lead_id": "b1c2d3e4-f5a6-7890-abcd-ef1234567890",
                "call_received": "Mar 15, 2026 10:30 AM",
                "duration": "2m 13s",
                "csr_name": "Jane Smith",
                "answered_by_display": "Jane Smith",
                "customer_name": "JOHN DOE",
                "phone_number": "(555) 123-4567",
                "is_qualified": True,
                "is_booked": False,
                "booking_status": "unbooked",
                "is_service_offered": True,
                "is_existing_customer": False,
                "lead_source": "google_ads",
                "audio_url": "https://storage.example.com/recordings/call-123.mp3",
                "call_summary": "Customer called about plumbing repair for a leaking faucet.",
                "key_items": ["leaking faucet", "kitchen sink"],
                "action_items": ["Schedule appointment", "Send quote"],
                "score": 0.85,
                "objections": "service_fee_concerns, scheduling_conflicts",
                "tags": "residential, plumbing",
                "transcript": None,
            }
        }
    }


class CallLogsResponse(BaseModel):
    """Response for GET /calls/logs.

    Contains summary statistics, paginated call list, and pagination metadata.
    """
    summary: CallLogsSummary = Field(..., description="Aggregate statistics (total_calls, qualified, booked, abandoned)")
    calls: List[CallLogEntry] = Field(..., description="Filtered list of call log entries")
    total: int = Field(..., description="Total count matching filters (before pagination)")
    skip: int = Field(..., description="Number of records skipped (pagination offset)")
    limit: int = Field(..., description="Maximum records returned (page size)")


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
