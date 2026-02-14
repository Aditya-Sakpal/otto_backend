"""
Call and call-logs response schemas for API documentation.
"""
from typing import Optional, List, Any
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

    model_config = {"extra": "allow"}


class CallLogsResponse(BaseModel):
    """Response for GET /calls/logs."""
    summary: CallLogsSummary = Field(..., description="Aggregate statistics")
    calls: List[CallLogEntry] = Field(..., description="Filtered list of call log entries")
    total: int = Field(..., description="Total count matching filters")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records returned")
