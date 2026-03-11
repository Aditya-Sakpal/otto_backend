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
    """Extended coaching session response with cycle info."""
    id: UUID = Field(..., description="Coaching session UUID")
    company_id: UUID = Field(..., description="Company UUID")
    rep_user_id: UUID = Field(..., description="User UUID of the rep being coached")
    coach_user_id: UUID = Field(..., description="User UUID of the coach/manager")
    focus_areas: List[str] = Field(..., description="Metrics being focused on")
    targets: Optional[Dict[str, float]] = Field(None, description="Target scores")
    baseline_scores: Optional[Dict[str, float]] = Field(None, description="Baseline from start of this cycle")
    status: str = Field(..., description="Session status: in_progress, completed, stopped")
    follow_up_days: int = Field(..., description="Follow-up period length in days")
    follow_up_end_date: Optional[datetime] = Field(None, description="When this cycle ends")
    impact_scores: Optional[Dict[str, float]] = Field(None, description="Post-cycle scores")
    overall_improved: Optional[bool] = Field(None, description="Whether improvement was detected")
    improvement_pct: Optional[float] = Field(None, description="Improvement percentage")
    targets_met: Optional[Dict[str, bool]] = Field(None, description="Which targets were met")
    notes: Optional[str] = Field(None, description="Coaching notes")
    coached_at: datetime = Field(..., description="When coaching started")
    created_at: datetime = Field(..., description="Record creation time")
    cycle_number: int = Field(1, description="Which 7-day cycle this is (1, 2, 3, ...)")
    parent_session_id: Optional[UUID] = Field(None, description="Original session ID linking all cycles")
    auto_created: bool = Field(False, description="Whether this cycle was auto-created by the system")


class CoachingSessionHistoryResponse(BaseModel):
    """All cycles for a coaching session chain."""
    original_session_id: UUID = Field(..., description="The first session in the chain")
    rep_user_id: UUID = Field(..., description="Rep being coached")
    total_cycles: int = Field(..., description="Total number of completed + active cycles")
    active_cycle: Optional[CoachingSessionCycleResponse] = Field(None, description="Currently active cycle (if any)")
    completed_cycles: List[CoachingSessionCycleResponse] = Field(..., description="All completed cycles, newest first")


class StopCoachingRequest(BaseModel):
    """Request to stop auto-cycling for a coaching session."""
    notes: Optional[str] = Field(None, description="Optional reason for stopping")
