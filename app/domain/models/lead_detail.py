"""
Lead detail domain model.

Comprehensive lead details for the lead details page.
"""
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field

from app.domain.models.base import BaseModel


class _SlimModel(PydanticBaseModel):
    """Lightweight Pydantic model (no auto id/created_at/updated_at) for sub-objects."""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ContactInfo(BaseModel):
    """Contact information."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_phone: str
    email: Optional[str] = None


class AgentInfo(BaseModel):
    """Assigned agent information."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str


class OverallEngagement(BaseModel):
    """Overall engagement section."""
    summary: Optional[str] = Field(None, description="Aggregated summary from all call analyses")
    key_points: List[str] = Field(default_factory=list, description="Key points from call analyses")
    action_items: List[str] = Field(default_factory=list, description="Pending action items")
    appointment_status: Optional[str] = Field(None, description="Appointment status based on lead status")


class Conversation(BaseModel):
    """Conversation (call) with the lead."""
    id: UUID
    call_type: Optional[str] = None
    lead_source: Optional[str] = None
    phone_number: str
    duration_seconds: Optional[int] = None
    missed_call: bool = False
    transcript: Optional[str] = None
    call_recording_url: Optional[str] = Field(None, description="Audio recording URL")
    handled_by_user_id: Optional[UUID] = None
    created_at: datetime
    
    # Analysis data (if available)
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    sop_compliance_score: Optional[float] = None
    qualification_status: Optional[str] = None
    booking_status: Optional[str] = None
    phases: Optional[dict] = Field(
        None,
        description="Live conversation phase payload from Shoonya call phases API",
    )


class PipelineEngagement(_SlimModel):
    """Overall engagement section for the pipeline lead detail view."""
    last_touched: Optional[datetime] = Field(None, description="Most recent call/interaction date")
    next_move: Optional[str] = Field(None, description="Next recommended action from latest call analysis")
    summary: Optional[str] = Field(None, description="Aggregated summary from all call analyses")
    key_points: List[str] = Field(default_factory=list)


class PipelineConversation(_SlimModel):
    """A single call with analysis data for the pipeline lead detail view."""
    id: UUID
    call_type: Optional[str] = None
    lead_source: Optional[str] = None
    duration_seconds: Optional[int] = None
    created_at: datetime
    booking_status: Optional[str] = None
    qualification_status: Optional[str] = None
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    call_recording_url: Optional[str] = None
    phases: Optional[dict] = Field(
        None,
        description="Live conversation phase payload from Shoonya GET .../calls/{call_id}/phases",
    )


class SalesRepInfo(_SlimModel):
    """Sales rep assigned to an appointment."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class AppointmentDetails(_SlimModel):
    """Details sub-section of appointment tab."""
    id: UUID
    contact_name: str
    sales_rep: Optional[SalesRepInfo] = None
    status: str = Field(description="Appointment status: scheduled, completed, cancelled, etc.")
    outcome: Optional[str] = None
    location_address: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: Optional[datetime] = None
    meeting_url: Optional[str] = None
    deal_size: Optional[float] = None

    # Appointment recording & transcript
    audio_url: Optional[str] = None
    transcript: Optional[str] = None
    duration_seconds: Optional[int] = None

    # Appointment analysis
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)


class FollowUpTask(_SlimModel):
    """
    A single follow-up item: legacy `pending_actions` and/or `follow_up_otto` (GoMotto).
    """
    id: UUID
    action_type: str
    raw_text: Optional[str] = None
    status: str = "pending"
    due_at: Optional[datetime] = None
    priority: Optional[int] = None

    # When row comes from follow_up_otto (GoMotto agent)
    source: Optional[str] = Field(
        None,
        description="pending_action | follow_up_otto",
    )
    message_content: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    external_message_id: Optional[str] = None
    attempt_number: Optional[int] = None
    queue_type: Optional[str] = None
    company_id: Optional[UUID] = None
    assigned_rep_id: Optional[UUID] = None
    pending_action_id: Optional[UUID] = Field(
        None,
        description="Linked pending_actions.id when nudge created a task",
    )
    opening_line: Optional[str] = None
    close_approach: Optional[str] = None
    objections: Optional[List[Any]] = None
    key_talking_points: Optional[List[Any]] = None
    error_message: Optional[str] = None
    ai_reasoning: Optional[Any] = None


class FollowUpTracking(_SlimModel):
    """Follow-up tracking summary for pipeline detail (appointment.follow_up or root follow_up)."""
    follow_up_attempts: int = 0
    last_touched: Optional[datetime] = None
    is_overdue: bool = False
    next_follow_up: Optional[datetime] = None
    follow_up_content: List[FollowUpTask] = Field(
        default_factory=list,
        description="All follow_up_otto and standalone pending_action items for this lead",
    )


class AppointmentTab(_SlimModel):
    """Appointment tab data — split into details and follow_up sub-sections."""
    # Top-level summary fields (shown as appointment header)
    title: Optional[str] = Field(None, description="Appointment headline, e.g. 'Torn Shingles, Roof Sold'")
    location_address: Optional[str] = Field(None, description="Full address, e.g. '123 Main St, Phoenix, AZ'")
    sales_rep_name: Optional[str] = Field(None, description="Assigned sales rep full name")
    deal_size: Optional[float] = Field(None, description="Deal value in dollars")
    status: Optional[str] = Field(None, description="Appointment status: scheduled, completed, won, lost, etc.")
    scheduled_start: Optional[datetime] = Field(None, description="Scheduled appointment date & time")
    arrival_time: Optional[datetime] = Field(None, description="Actual rep arrival time")

    # Sub-sections
    details: AppointmentDetails
    follow_up: FollowUpTracking = Field(default_factory=FollowUpTracking)


class ResultTab(_SlimModel):
    """Result tab data — shown when appointment has been conducted and has an outcome/analysis."""
    outcome: Optional[str] = None
    outcome_summary: Optional[str] = None
    deal_size: Optional[float] = None
    key_lesson: Optional[str] = None

    overall_engagement: PipelineEngagement
    conversations: List[PipelineConversation] = Field(default_factory=list)

    # Follow-up tracking intentionally omitted from `result` tab.
    # GoMotto follow-ups are shown under `appointment.follow_up` only.
    follow_up: Optional[FollowUpTracking] = None


class PipelineLeadTab(_SlimModel):
    """Lead tab — CSR stage data."""
    id: UUID
    status: str
    overall_engagement: PipelineEngagement
    conversations: List[PipelineConversation] = Field(default_factory=list)


class PipelineLeadDetail(_SlimModel):
    """
    3-tab pipeline lead detail response.

    - lead: always present (CSR stage view — calls & overall engagement)
    - appointment: present when lead has a linked appointment
    - result: present when the appointment has been conducted (has outcome or analysis)
    - follow_up: when there is no appointment tab, GoMotto + pending_actions live here
      so follow-ups are still returned for qualified-unbooked leads without an appointment row.
    """
    pipeline_stage: Optional[str] = None
    lead: PipelineLeadTab
    appointment: Optional[AppointmentTab] = None
    result: Optional[ResultTab] = None
    follow_up: Optional[FollowUpTracking] = Field(
        None,
        description="Follow-up tracking when appointment tab is absent",
    )


class LeadDetail(BaseModel):
    """Detailed lead information for lead details page."""
    # Basic info
    id: UUID
    company_id: UUID
    status: str
    deal_status: Optional[str] = None
    pipeline_stage: Optional[str] = None
    deal_size: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Contact info
    contact: ContactInfo
    
    # Agent info
    agent: Optional[AgentInfo] = None
    
    # Overall engagement
    overall_engagement: OverallEngagement
    
    # Conversations (sorted by most recent first)
    conversations: List[Conversation] = Field(default_factory=list, description="All conversations with this lead, sorted by most recent first")
