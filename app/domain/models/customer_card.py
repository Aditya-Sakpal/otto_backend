"""
Customer Card domain model.

Comprehensive response model for the customer card view that shows
when a user clicks on a lead in the pipeline.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field


class _Slim(PydanticBaseModel):
    """Lightweight Pydantic model for sub-objects."""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ── Header ────────────────────────────────────────────────────────────────────

class CardContact(_Slim):
    """Contact information shown in the card header."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    initials: Optional[str] = None
    primary_phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None


class CardRepInfo(_Slim):
    """Sales rep info for footer / appointment tab."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None


class PipelineStageInfo(_Slim):
    """Single pipeline stage for the progress bar."""
    name: str
    label: str
    status: str = Field(description="done | active | future")
    order: int


# ── Lead Tab ──────────────────────────────────────────────────────────────────

class CardEngagement(_Slim):
    """Overall engagement section."""
    last_touched: Optional[datetime] = None
    next_move: Optional[str] = None
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)


class SOPChecklistItem(_Slim):
    """Single item in the SOP compliance checklist."""
    stage_name: str
    status: str = Field(description="completed | missed")
    score: Optional[float] = None


class CardConversation(_Slim):
    """A single call/conversation in the lead tab."""
    id: UUID
    call_type: Optional[str] = None
    phone_number: Optional[str] = None
    duration_seconds: Optional[int] = None
    missed_call: bool = False
    created_at: datetime
    answered_at: Optional[datetime] = None
    call_recording_url: Optional[str] = None

    # Analysis
    booking_status: Optional[str] = None
    qualification_status: Optional[str] = None
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None

    # CSR qualification extracted from call analysis
    service_requested: Optional[str] = None
    property_details: Optional[Dict[str, Any]] = None

    # SOP compliance for this call
    sop_compliance_score: Optional[float] = None
    sop_compliance_rate: Optional[float] = None
    sop_checklist: List[SOPChecklistItem] = Field(default_factory=list)
    sop_compliance_issues: List[str] = Field(default_factory=list)
    sop_compliance_positive_behaviors: List[str] = Field(default_factory=list)
    compliance_target_role: Optional[str] = None


class CardLeadTab(_Slim):
    """Lead tab — CSR stage data."""
    id: UUID
    status: str
    overall_engagement: CardEngagement
    conversations: List[CardConversation] = Field(default_factory=list)
    coaching_tips: Optional[str] = None


# ── Appointment Tab ───────────────────────────────────────────────────────────

class CardAppointmentTab(_Slim):
    """Appointment tab data."""
    id: UUID
    contact_name: str
    sales_rep: Optional[CardRepInfo] = None
    status: str = Field(description="scheduled | completed | cancelled | won | lost")
    outcome: Optional[str] = None
    location_address: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: Optional[datetime] = None
    meeting_url: Optional[str] = None
    deal_size: Optional[float] = None
    title: Optional[str] = Field(None, description="Appointment headline, e.g. 'Torn Shingles, Roof Sold'")
    arrival_time: Optional[datetime] = Field(None, description="Actual rep arrival time")

    # Appointment recording & transcript
    audio_url: Optional[str] = None
    transcript: Optional[str] = None
    duration_seconds: Optional[int] = None

    # Appointment analysis
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    objection_texts: List[str] = Field(default_factory=list)

    # SOP compliance for the appointment
    sop_compliance_score: Optional[float] = None
    sop_compliance_rate: Optional[float] = None
    sop_checklist: List[SOPChecklistItem] = Field(default_factory=list)
    sop_compliance_issues: List[str] = Field(default_factory=list)
    sop_compliance_positive_behaviors: List[str] = Field(default_factory=list)
    compliance_target_role: Optional[str] = None

    # Posts / comments
    posts: List["CardPost"] = Field(default_factory=list)


# ── Result Tab ────────────────────────────────────────────────────────────────

class CardFollowUpTask(_Slim):
    """A single follow-up / pending action."""
    id: UUID
    action_type: str
    raw_text: Optional[str] = None
    status: str = "pending"
    due_at: Optional[datetime] = None
    priority: Optional[int] = None


class CardFollowUpTracking(_Slim):
    """Follow-up tracking summary for the result tab."""
    follow_up_attempts: int = 0
    last_touched: Optional[datetime] = None
    is_overdue: bool = False
    next_follow_up: Optional[datetime] = None
    tasks: List[CardFollowUpTask] = Field(default_factory=list)


class CardResultTab(_Slim):
    """Result tab — outcome & follow-up."""
    outcome: Optional[str] = None
    outcome_summary: Optional[str] = None
    deal_size: Optional[float] = None
    key_lesson: Optional[str] = None

    overall_engagement: CardEngagement
    conversations: List[CardConversation] = Field(default_factory=list)

    # Follow-up tracking
    follow_up: CardFollowUpTracking = Field(default_factory=CardFollowUpTracking)


# ── Posts ─────────────────────────────────────────────────────────────────────

class CardPostAuthor(_Slim):
    """Author info for a post/comment."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    initials: Optional[str] = None


class CardPost(_Slim):
    """A comment/post on an appointment."""
    id: UUID
    author: Optional[CardPostAuthor] = None
    note: Optional[str] = None
    tags: Optional[str] = None
    likes: int = 0
    created_at: Optional[datetime] = None


# ── Top-level Customer Card ───────────────────────────────────────────────────

class CustomerCard(_Slim):
    """
    Complete customer card response.

    Returned when clicking on a lead in the pipeline view.
    Contains header info + 3 tabs (lead, appointment, result).
    """
    # Header
    id: UUID
    company_id: UUID
    status: str
    deal_status: Optional[str] = None
    pipeline_stage: Optional[str] = None
    deal_size: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    contact: CardContact
    assigned_rep: Optional[CardRepInfo] = None
    pipeline_stages: List[PipelineStageInfo] = Field(default_factory=list)

    # Tabs
    lead: CardLeadTab
    appointment: Optional[CardAppointmentTab] = None
    result: Optional[CardResultTab] = None


# Rebuild forward refs for CardAppointmentTab.posts
CardAppointmentTab.model_rebuild()
