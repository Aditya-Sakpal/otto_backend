"""
Appointment Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import AppointmentOutcome


class AppointmentBase(BaseModel):
    """Base schema with common appointment fields."""

    company_id: UUID = Field(..., description="Company/tenant ID")
    lead_id: UUID = Field(..., description="Associated lead ID")
    contact_card_id: UUID = Field(..., description="Associated contact card ID")
    scheduled_start: datetime = Field(..., description="Scheduled start time (UTC)")
    scheduled_end: Optional[datetime] = Field(
        None,
        description="Scheduled end time (UTC)",
    )
    location_address: Optional[str] = Field(
        None,
        description="Location/address of the appointment",
    )
    outcome: Optional[AppointmentOutcome] = Field(
        None,
        description="Outcome of the appointment",
    )
    assigned_rep_id: Optional[UUID] = Field(
        None,
        description="Assigned sales rep user ID",
    )
    extra_metadata: Optional[dict] = Field(
        None,
        description="Additional metadata for the appointment",
    )


class AppointmentCreate(AppointmentBase):
    """Schema for creating a new appointment."""

    # All fields from AppointmentBase are required/optional as defined there.
    pass


class AppointmentUpdate(BaseModel):
    """Schema for updating an existing appointment (all fields optional)."""

    scheduled_start: Optional[datetime] = Field(
        None,
        description="Updated scheduled start time (UTC)",
    )
    scheduled_end: Optional[datetime] = Field(
        None,
        description="Updated scheduled end time (UTC)",
    )
    location_address: Optional[str] = Field(
        None,
        description="Updated location/address",
    )
    outcome: Optional[AppointmentOutcome] = Field(
        None,
        description="Updated appointment outcome",
    )
    assigned_rep_id: Optional[UUID] = Field(
        None,
        description="Updated assigned sales rep user ID",
    )
    extra_metadata: Optional[dict] = Field(
        None,
        description="Updated metadata for the appointment",
    )


class AppointmentLocationUpdate(BaseModel):
    """Schema for updating an appointment's location address.

    Provide either appointment_id or lead_id (not both) to identify the appointment.
    """

    appointment_id: Optional[UUID] = Field(None, description="Appointment ID")
    lead_id: Optional[UUID] = Field(None, description="Lead ID whose appointment to update")
    location_address: str = Field(
        ...,
        min_length=1,
        description="New location/address for the appointment",
    )

    @model_validator(mode="after")
    def check_one_id_provided(self):
        if self.appointment_id and self.lead_id:
            raise ValueError("Provide either appointment_id or lead_id, not both")
        if not self.appointment_id and not self.lead_id:
            raise ValueError("Either appointment_id or lead_id is required")
        return self


class AppointmentReschedule(BaseModel):
    """Schema for rescheduling an appointment's start/end time.

    Provide either appointment_id or lead_id (not both) to identify the appointment.
    """

    appointment_id: Optional[UUID] = Field(None, description="Appointment ID")
    lead_id: Optional[UUID] = Field(None, description="Lead ID whose appointment to reschedule")
    scheduled_start: datetime = Field(..., description="New scheduled start time (UTC)")
    scheduled_end: Optional[datetime] = Field(None, description="New scheduled end time (UTC)")

    @model_validator(mode="after")
    def check_one_id_provided(self):
        if self.appointment_id and self.lead_id:
            raise ValueError("Provide either appointment_id or lead_id, not both")
        if not self.appointment_id and not self.lead_id:
            raise ValueError("Either appointment_id or lead_id is required")
        return self


class PendingActionDetail(BaseModel):
    """Structured pending action extracted from recording."""
    type: str = Field(..., description="Action type (e.g., send_info, follow_up_call)")
    owner: str = Field(..., description="Owner role (e.g., customer_rep, sales_rep)")
    raw_text: str = Field(..., description="Raw text of the action item")
    due_at: Optional[datetime] = Field(None, description="When the action is due")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")
    contact_method: Optional[str] = Field(None, description="Contact method (e.g., email, phone)")


class ObjectionDetail(BaseModel):
    """Detailed objection with category and handling information."""
    category_id: int = Field(..., description="Objection category ID")
    category_text: str = Field(..., description="Objection category name")
    objection_text: str = Field(..., description="The actual objection raised")
    overcome: bool = Field(..., description="Whether the objection was overcome")
    severity: str = Field(..., description="Severity level (low, medium, high)")
    confidence_score: float = Field(..., description="Confidence score (0-1)")
    response_suggestions: List[str] = Field(default_factory=list, description="Suggested responses for future")


class ComplianceStageDetail(BaseModel):
    """Compliance details for a specific SOP stage."""
    score: float = Field(..., description="Stage compliance score (0-1)")
    issues: List[str] = Field(default_factory=list, description="Issues identified in this stage")


class AppointmentInsightSummary(BaseModel):
    """Structured insights extracted from the related call analysis (recording analysis)."""

    # Summary section
    summary: Optional[str] = Field(None, description="Call summary text")
    key_points: List[str] = Field(default_factory=list, description="Key points from the call")
    pending_actions: List[PendingActionDetail] = Field(default_factory=list, description="Structured pending actions")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (0-1)")

    # Objections section
    objections: List[ObjectionDetail] = Field(default_factory=list, description="List of detailed objections")
    objections_total_count: int = Field(default=0, description="Total number of objections detected")

    # Compliance section (SOP)
    sop_compliance_score: Optional[float] = Field(None, description="Overall SOP compliance score (0-1)")
    sop_stages: Dict[str, ComplianceStageDetail] = Field(default_factory=dict, description="Compliance by stage")
    sop_positive_behaviors: List[str] = Field(default_factory=list, description="Positive behaviors observed")
    sop_issues: List[str] = Field(default_factory=list, description="Overall compliance issues")

    # Qualification section (BANT)
    qualification_overall_score: Optional[float] = Field(None, description="Overall qualification score (0-1)")
    bant_scores: Dict[str, float] = Field(default_factory=dict, description="BANT scores (need, budget, authority, timeline)")
    qualification_status: Optional[str] = Field(None, description="Qualification status (e.g., warm, hot, cold)")

    # Lead score section
    lead_total_score: Optional[int] = Field(None, description="Total lead score (0-100)")
    lead_band: Optional[str] = Field(None, description="Lead band/category (e.g., warm, hot)")

    # Legacy fields (for backward compatibility)
    action_items: List[str] = Field(default_factory=list, description="Action items identified (legacy)")
    follow_up_required: Optional[bool] = Field(None, description="Whether a follow-up is required")
    follow_up_reason: Optional[str] = Field(None, description="Reason for the required follow-up, if any")


class AppointmentResponse(AppointmentBase):
    """Schema for appointment API responses."""

    id: UUID = Field(..., description="Appointment UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(
        None,
        description="Last update timestamp",
    )
    appointment_name: Optional[str] = Field(
        None,
        description="Contact name (from contact card)",
    )
    sales_rep_name: Optional[str] = Field(
        None,
        description="Sales rep name (from assigned user)",
    )
    contact_details: Optional[dict] = Field(
        None,
        description="Full contact card details",
    )
    assigned_rep_details: Optional[dict] = Field(
        None,
        description="Full assigned sales rep user details",
    )
    insights: Optional[AppointmentInsightSummary] = Field(
        None,
        description="Insights derived from the associated call analysis, when available",
    )
    latitude: Optional[float] = Field(
        None,
        description="Geocoded latitude from contact card",
    )
    longitude: Optional[float] = Field(
        None,
        description="Geocoded longitude from contact card",
    )
    audio_url: Optional[str] = Field(
        None,
        description="Audio recording URL",
    )
    recording_status: Optional[str] = Field(
        None,
        description="Recording status (e.g. uploaded)",
    )

    class Config:
        from_attributes = True


# ============================================================================
# Appointment Context Schemas (Wave 2: Pre-Meeting Intelligence)
# ============================================================================


class CallSummaryItem(BaseModel):
    """Call summary with AI analysis."""

    call_id: UUID
    call_type: str  # "csr_call", "sales_call", "missed_call"
    call_date: datetime
    duration_seconds: Optional[int]
    audio_url: Optional[str]
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    handled_by_name: Optional[str] = None


class ContactCardInfo(BaseModel):
    """Contact card details."""

    id: UUID
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    primary_phone: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]


class LeadContextInfo(BaseModel):
    """Lead status and metadata."""

    id: UUID
    status: str  # LeadStatus enum value
    deal_size: Optional[float]
    deal_type: Optional[str]
    lead_score: Optional[float] = None  # Future: from intelligence service


class AggregatedObjections(BaseModel):
    """Objections aggregated across all calls."""

    unique_objections: List[str]
    objection_counts: Dict[str, int]  # objection -> count
    top_objections: List[str]  # Top 3 by frequency


class PendingActionItem(BaseModel):
    """Pending action for the lead."""

    id: UUID
    raw_text: str
    priority: Optional[int]
    status: str
    due_at: Optional[datetime]
    owner_name: Optional[str]


class AIBriefing(BaseModel):
    """AI-generated pre-meeting brief."""

    briefing_text: str
    focus_areas: List[str] = Field(default_factory=list)
    generated_at: datetime


class AppointmentAnalysis(BaseModel):
    """Analysis data from Shoonya processing of an appointment recording."""

    analysis_status: Optional[str] = None
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    qualification_status: Optional[str] = None
    booking_status: Optional[str] = None
    objection_texts: List[str] = Field(default_factory=list)
    objections_total_count: Optional[int] = None
    sop_compliance_score: Optional[float] = None
    sop_compliance_rate: Optional[float] = None
    sop_stages_completed: List[str] = Field(default_factory=list)
    sop_stages_missed: List[str] = Field(default_factory=list)
    sop_compliance_issues: List[str] = Field(default_factory=list)
    sop_compliance_positive_behaviors: List[str] = Field(default_factory=list)


class AppointmentContextResponse(BaseModel):
    """Comprehensive appointment context for pre-meeting intelligence."""

    # Appointment basics
    appointment_id: UUID
    scheduled_start: datetime
    scheduled_end: Optional[datetime]
    location_address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    outcome: Optional[str]
    recording_status: Optional[str] = None
    audio_url: Optional[str] = None

    # Analysis (nested)
    appointment_analysis: Optional[AppointmentAnalysis] = None

    # Contact and rep info
    contact_info: ContactCardInfo
    sales_rep_name: Optional[str]

    # Lead context
    lead_info: LeadContextInfo

    # Conversation history (CSR + sales calls)
    conversation_history: List[CallSummaryItem]

    # Aggregated objections
    objections: AggregatedObjections

    # Pending actions
    pending_actions: List[PendingActionItem]

    # AI briefing (may be None if Shoonya unavailable)
    ai_briefing: Optional[AIBriefing] = None

