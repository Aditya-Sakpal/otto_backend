"""
Appointment Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
        "pending",
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

    model_config = {
        "json_schema_extra": {
            "example": {
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "lead_id": "b1c2d3e4-f5a6-7890-abcd-ef1234567890",
                "contact_card_id": "c3d4e5f6-a7b8-9012-cdef-345678901234",
                "scheduled_start": "2026-03-25T10:00:00Z",
                "scheduled_end": "2026-03-25T11:00:00Z",
                "location_address": "123 Main St, Phoenix AZ 85001",
                "outcome": None,
                "assigned_rep_id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
            }
        }
    }


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
    phases: Optional[dict] = Field(
        None,
        description="Live conversation phase detection from Shunya (greeting, problem_discovery, qualification, objection_handling, closing, post_close)",
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


class AppointmentContextFollowUpDraft(BaseModel):
    """A contextual follow-up row saved before send (e.g. manual review)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "action_type": "sms_to_lead",
                    "status": "proposed",
                    "message_content": "Hi Jane — following up on your roof estimate. Want me to hold Tuesday 2pm?",
                    "scheduled_at": "2026-03-27T18:00:00Z",
                    "created_at": "2026-03-27T17:05:00Z",
                    "queue_type": "appointment_ran",
                    "attempt_number": 1,
                }
            ]
        }
    )

    id: UUID
    action_type: str
    status: str
    message_content: str
    scheduled_at: datetime
    created_at: datetime
    queue_type: str
    attempt_number: int


class AppointmentContextFollowUpSection(BaseModel):
    """Contextual follow-up agent: company toggle + drafts awaiting send/edit."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "manual_review_enabled": True,
                    "pending_messages": [
                        {
                            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "action_type": "sms_to_lead",
                            "status": "proposed",
                            "message_content": "Hi Jane — following up on your roof estimate. Want me to hold Tuesday 2pm?",
                            "scheduled_at": "2026-03-27T18:00:00Z",
                            "created_at": "2026-03-27T17:05:00Z",
                            "queue_type": "appointment_ran",
                            "attempt_number": 1,
                        }
                    ],
                },
                {"manual_review_enabled": False, "pending_messages": []},
            ]
        }
    )

    manual_review_enabled: bool
    pending_messages: List[AppointmentContextFollowUpDraft] = Field(default_factory=list)


# OpenAPI / Swagger: use this for GET /appointments/{id}/context response example (single source of truth).
APPOINTMENT_CONTEXT_RESPONSE_EXAMPLE: Dict[str, Any] = {
    "appointment_id": "dbd8540e-6337-4127-93a2-d8d20cb9b5dd",
    "scheduled_start": "2026-03-24T17:00:00Z",
    "scheduled_end": None,
    "location_address": "Ashken",
    "latitude": None,
    "longitude": None,
    "outcome": "pending",
    "recording_status": "uploaded",
    "audio_url": "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/appointment_dbd8540e-6337-4127-93a2-d8d20cb9b5dd.wav",
    "phases": {
        "greeting": {
            "phase": "greeting",
            "detected": True,
            "confidence": 0.5,
            "timestamps": {
                "start_ms": 1920,
                "end_ms": 4197,
                "duration_ms": 2277,
                "estimation_method": "hybrid_aligned",
            },
            "segments": [],
            "key_phrases": ["thanks for calling"],
            "quality_score": 0.7,
            "quality_notes": None,
        },
        "problem_discovery": {
            "phase": "problem_discovery",
            "detected": False,
            "confidence": 0,
            "timestamps": None,
            "segments": [],
            "key_phrases": [],
            "quality_score": None,
            "quality_notes": None,
        },
        "qualification": {
            "phase": "qualification",
            "detected": False,
            "confidence": 0,
            "timestamps": None,
            "segments": [],
            "key_phrases": [],
            "quality_score": None,
            "quality_notes": None,
        },
        "objection_handling": {
            "phase": "objection_handling",
            "detected": False,
            "confidence": 0,
            "timestamps": None,
            "segments": [],
            "key_phrases": [],
            "quality_score": None,
            "quality_notes": None,
        },
        "closing": {
            "phase": "closing",
            "detected": False,
            "confidence": 0,
            "timestamps": None,
            "segments": [],
            "key_phrases": [],
            "quality_score": None,
            "quality_notes": None,
        },
        "post_close": {
            "phase": "post_close",
            "detected": False,
            "confidence": 0,
            "timestamps": None,
            "segments": [],
            "key_phrases": [],
            "quality_score": None,
            "quality_notes": None,
        },
    },
    "appointment_analysis": {
        "analysis_status": "completed",
        "summary": "Walkthrough completed; homeowner asked about warranty.",
        "key_points": ["Discussed timeline"],
        "action_items": [],
        "next_steps": [],
        "sentiment_score": 0.72,
        "qualification_status": "warm",
        "booking_status": "booked",
        "objection_texts": [],
        "objections_total_count": 0,
        "sop_compliance_score": 0.85,
        "sop_compliance_rate": None,
        "sop_stages_completed": ["greeting", "qualification"],
        "sop_stages_missed": [],
        "sop_compliance_issues": [],
        "sop_compliance_positive_behaviors": [],
    },
    "contact_info": {
        "id": "4013a406-29d0-4eb8-aad8-2139735b4254",
        "first_name": "Jane",
        "last_name": "Doe",
        "primary_phone": "+15551234567",
        "email": "jane@example.com",
        "address": None,
        "city": None,
        "state": None,
    },
    "sales_rep_name": "Alex Smith",
    "lead_info": {
        "id": "bc175381-b349-4cfc-ac23-8085d567665e",
        "status": "qualified_booked",
        "deal_size": 12000.0,
        "deal_type": None,
        "lead_score": None,
    },
    "conversation_history": [],
    "objections": {
        "unique_objections": [],
        "objection_counts": {},
        "top_objections": [],
    },
    "pending_actions": [],
    "ai_briefing": None,
    "follow_up": None,
}


class AppointmentContextResponse(BaseModel):
    """Comprehensive appointment context for pre-meeting intelligence."""

    model_config = ConfigDict(
        json_schema_extra={"example": APPOINTMENT_CONTEXT_RESPONSE_EXAMPLE}
    )

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
    phases: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Shoonya conversation phases for the appointment interaction call "
            "(GET /api/v1/call-processing/calls/{call_id}/phases). "
            "Null when there is no interaction_id or Shoonya is unavailable."
        ),
    )

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

    # Conversation phases from Shunya
    phases: Optional[dict] = Field(
        None,
        description="Live conversation phase detection from Shunya (greeting, problem_discovery, qualification, objection_handling, closing, post_close)",
    )

    # AI briefing (may be None if Shoonya unavailable)
    ai_briefing: Optional[AIBriefing] = None

    # Contextual follow-up agent (proposed messages when manual review is on)
    follow_up: Optional[AppointmentContextFollowUpSection] = Field(
        None,
        description="When manual review is enabled for the company, lists proposed SMS/nudge drafts for this lead.",
        json_schema_extra={
            "example": {
                "manual_review_enabled": True,
                "pending_messages": [
                    {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        "action_type": "sms_to_lead",
                        "status": "proposed",
                        "message_content": "Hi Jane — following up on your roof estimate.",
                        "scheduled_at": "2026-03-27T18:00:00Z",
                        "created_at": "2026-03-27T17:05:00Z",
                        "queue_type": "appointment_ran",
                        "attempt_number": 1,
                    }
                ],
            }
        },
    )


class AppointmentsTodayCounts(BaseModel):
    total_today: int
    pending: int
    closed: int


class AppointmentsTodayResponse(BaseModel):
    appointments: List[AppointmentResponse]
    counts: AppointmentsTodayCounts
