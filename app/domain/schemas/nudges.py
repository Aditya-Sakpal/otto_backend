"""
Smart Nudge API schemas.

Pydantic models for smart nudge CRUD endpoints: list, read, dismiss,
unread count, and mark-all-read.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# --- Nudge Response ---


class SmartNudgeResponse(BaseModel):
    """A single smart nudge with per-user read status."""
    id: UUID = Field(..., description="Nudge UUID")
    company_id: UUID = Field(..., description="Company UUID")
    rep_user_id: UUID = Field(..., description="User UUID of the rep this nudge is about")
    rep_name: Optional[str] = Field(None, description="Display name of the rep")
    nudge_type: str = Field(..., description="Nudge type: metric_improvement, metric_decline, critical_decline, recurring_issue, objection_weakness, objection_improvement, coaching_target_met, coaching_target_missed, new_strength, cycle_summary")
    priority: str = Field("medium", description="Priority: critical, high, medium, low, positive")
    title: str = Field(..., description="Short title (max 255 chars)")
    message: str = Field(..., description="Detailed coaching message")
    metric_name: Optional[str] = Field(None, description="Which metric triggered this nudge")
    previous_value: Optional[float] = Field(None, description="Metric value before the change")
    current_value: Optional[float] = Field(None, description="Metric value after the change")
    change_pct: Optional[float] = Field(None, description="Percentage change")
    window_description: Optional[str] = Field(None, description="Time window (e.g. 'last 24 hours', 'cycle 3')")
    source_session_id: Optional[UUID] = Field(None, description="Related coaching session UUID if applicable")
    extra_data: Optional[Dict[str, Any]] = Field(None, description="Additional context data")
    created_at: datetime = Field(..., description="When the nudge was generated (ISO 8601)")
    expires_at: Optional[datetime] = Field(None, description="When the nudge expires (ISO 8601)")
    read_status: str = Field("unread", description="Per-user read status: 'unread', 'read', or 'dismissed'")
    read_at: Optional[datetime] = Field(None, description="When the current user read this nudge (null if unread)")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
                "rep_user_id": "3eed8382-6b30-44c9-82f6-6d70570e175e",
                "rep_name": "Ananya Sharma",
                "nudge_type": "metric_decline",
                "priority": "high",
                "title": "Ananya's SOP compliance dropped 15%",
                "message": "CSR Ananya's SOP compliance dropped by 15% compared to last cycle's baseline (0.72 → 0.61).",
                "metric_name": "compliance_score",
                "previous_value": 0.72,
                "current_value": 0.61,
                "change_pct": -15.3,
                "window_description": "last 24 hours vs cycle baseline",
                "created_at": "2026-03-11T02:00:00Z",
                "expires_at": "2026-03-18T02:00:00Z",
                "read_status": "unread",
                "read_at": None,
            }]
        }
    }


class SmartNudgeListResponse(BaseModel):
    """Paginated list of smart nudges with unread count."""
    total: int = Field(..., description="Total number of nudges matching filters")
    unread_count: int = Field(..., description="Number of unread nudges for the current user")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Pagination offset")
    nudges: List[SmartNudgeResponse] = Field(..., description="List of nudges sorted by created_at descending")


class UnreadCountResponse(BaseModel):
    """Lightweight response for notification badge polling."""
    unread_count: int = Field(..., description="Number of unread nudges for the current user")


class MarkReadResponse(BaseModel):
    """Response after marking a nudge as read or dismissed."""
    success: bool = Field(True, description="Whether the operation succeeded")
    nudge_id: UUID = Field(..., description="The nudge that was marked")
    status: str = Field(..., description="New status: 'read' or 'dismissed'")


class MarkAllReadResponse(BaseModel):
    """Response after marking all nudges as read."""
    success: bool = Field(True, description="Whether the operation succeeded")
    marked_count: int = Field(..., description="Number of nudges marked as read")


# --- Coaching Session Updates ---


class CoachingSessionCycleResponse(BaseModel):
    """
    Extended coaching session response with 7-day cycle tracking info.

    Each coaching session auto-restarts every 7 days. This response includes
    cycle-specific fields like `cycle_number`, `parent_session_id`, and `auto_created`
    in addition to the standard session fields.
    """
    id: UUID = Field(..., description="Coaching session UUID (unique per cycle)")
    company_id: UUID = Field(..., description="Company UUID")
    rep_user_id: UUID = Field(..., description="User UUID of the rep being coached")
    coach_user_id: UUID = Field(..., description="User UUID of the coach/manager")
    focus_areas: List[str] = Field(..., description="Metrics being focused on (e.g. ['compliance_score', 'booking_rate'])")
    targets: Optional[Dict[str, float]] = Field(None, description="Target scores to achieve. Keys: metric name, values: target (0-1 scale)")
    baseline_scores: Optional[Dict[str, float]] = Field(None, description="Scores at the start of this cycle. For cycle 1, auto-computed from last 5 calls. For subsequent cycles, uses previous cycle's end scores.")
    status: str = Field(..., description="Cycle status: 'in_progress' (active), 'completed' (auto-completed, next cycle created), 'stopped' (manually stopped)")
    follow_up_days: int = Field(..., description="Cycle duration in days (default 7)")
    follow_up_end_date: Optional[datetime] = Field(None, description="When this cycle ends (ISO 8601). System auto-completes the cycle after this date.")
    impact_scores: Optional[Dict[str, float]] = Field(None, description="Scores at end of this cycle (null while in_progress). Computed from call analyses during the cycle window.")
    overall_improved: Optional[bool] = Field(None, description="Whether majority of metrics improved vs baseline (null while in_progress)")
    improvement_pct: Optional[float] = Field(None, description="Average improvement percentage across all metrics (null while in_progress)")
    targets_met: Optional[Dict[str, bool]] = Field(None, description="Which target metrics were achieved. Keys: metric name, values: true/false (null while in_progress)")
    notes: Optional[str] = Field(None, description="Coaching notes. Auto-created cycles include 'Auto-created cycle N'")
    coached_at: datetime = Field(..., description="When this cycle started (ISO 8601)")
    created_at: datetime = Field(..., description="Record creation timestamp (ISO 8601)")
    cycle_number: int = Field(1, description="Which 7-day cycle this is in the chain (1, 2, 3, ...)")
    parent_session_id: Optional[UUID] = Field(None, description="UUID of the original session that started this chain. Null for the first cycle (cycle_number=1).")
    auto_created: bool = Field(False, description="true if this cycle was auto-created by the cron job, false if manually created")


class CoachingSessionHistoryResponse(BaseModel):
    """
    Full cycle history for a coaching session chain.

    Contains the currently active cycle (if any) and all previously completed cycles,
    ordered newest first. Use this to show a timeline of coaching progress over
    multiple 7-day cycles.
    """
    original_session_id: UUID = Field(..., description="UUID of the first session that started this coaching chain")
    rep_user_id: UUID = Field(..., description="UUID of the rep being coached")
    total_cycles: int = Field(..., description="Total number of cycles in the chain (completed + active + stopped)")
    active_cycle: Optional[CoachingSessionCycleResponse] = Field(None, description="Currently running cycle (null if coaching was stopped)")
    completed_cycles: List[CoachingSessionCycleResponse] = Field(..., description="All completed/stopped cycles, sorted by cycle_number descending (newest first)")


class StopCoachingRequest(BaseModel):
    """
    Request body to stop auto-cycling for a coaching session.

    The request body is optional — you can send an empty body or omit it entirely.
    """
    notes: Optional[str] = Field(None, description="Optional reason for stopping (e.g. 'Rep promoted', 'Focus areas changed')")
