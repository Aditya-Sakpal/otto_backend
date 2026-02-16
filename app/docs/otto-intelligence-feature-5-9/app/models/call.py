"""
Call Processing Models

MongoDB document models for call processing pipeline.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .enums import (
    QualificationStatus,
    BookingStatus,
    AppointmentType,
    CallOutcomeCategory,
    ProcessingStatus,
    SpeakerRole,
    ObjectionSeverity,
    ActionType,
    ContactMethod
)


# ============================================================================
# CALL MODELS
# ============================================================================

class Call(BaseModel):
    """Main call document"""
    call_id: str = Field(..., description="Unique call identifier")
    company_id: str = Field(..., description="Company/tenant identifier")
    customer_id: Optional[str] = Field(None, description="Customer reference")
    phone_number: str = Field(..., description="Customer phone number")
    audio_url: str = Field(..., description="S3 URL to audio file")
    duration: Optional[int] = Field(None, description="Call duration in seconds")
    call_date: datetime = Field(..., description="When the call occurred")
    status: ProcessingStatus = Field(ProcessingStatus.QUEUED, description="Processing status")
    transcript: Optional[str] = Field(None, description="Full transcript text")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# ============================================================================
# SUMMARY COMPONENTS
# ============================================================================

class PendingAction(BaseModel):
    """Pending action item"""
    type: ActionType
    owner: str = Field(..., description="Who should complete this action")
    due_at: Optional[datetime] = None
    raw_text: str = Field(..., description="Original text mentioning the action")
    confidence: float = Field(..., ge=0.0, le=1.0)
    contact_method: Optional[ContactMethod] = None


class Objection(BaseModel):
    """Customer objection"""
    id: Optional[int] = None
    category_id: int = Field(..., description="Objection category (1-10)")
    category_text: str = Field(..., description="Category name")
    sub_objection: Optional[str] = Field(None, description="Specific objection type when category is 'Other' (category_id=9)")
    objection_text: str = Field(..., description="The actual objection")
    overcome: bool = Field(False, description="Was the objection overcome")
    speaker_id: SpeakerRole = Field(SpeakerRole.HOME_OWNER)
    timestamp: Optional[str] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    severity: ObjectionSeverity = Field(ObjectionSeverity.MEDIUM)
    response_suggestions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class BANTScores(BaseModel):
    """BANT qualification scores"""
    need: float = Field(..., ge=0.0, le=1.0, description="Need score")
    budget: float = Field(..., ge=0.0, le=1.0, description="Budget score")
    timeline: float = Field(..., ge=0.0, le=1.0, description="Timeline score")
    authority: float = Field(..., ge=0.0, le=1.0, description="Authority score")


class ServiceAddress(BaseModel):
    """Structured service address"""
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "US"


class QualificationData(BaseModel):
    """Lead qualification information - COMPLETE with all fields"""
    # BANT Qualification
    bant_scores: BANTScores
    overall_score: float = Field(..., ge=0.0, le=1.0)
    qualification_status: QualificationStatus
    
    # Booking Status
    booking_status: BookingStatus
    call_outcome_category: CallOutcomeCategory
    
    # Appointment Details (Core)
    appointment_confirmed: bool = False
    appointment_date: Optional[datetime] = None
    appointment_type: Optional[AppointmentType] = None
    
    # Appointment Details (Extended - NEW)
    appointment_timezone: Optional[str] = Field(None, description="Timezone for appointment")
    appointment_time_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence in appointment time")
    preferred_time_window: Optional[str] = Field(None, description="morning, afternoon, evening, any")
    appointment_intent: Optional[str] = Field(None, description="new, reschedule, cancel, confirm")
    original_appointment_datetime: Optional[datetime] = Field(None, description="For reschedules")
    new_requested_time: Optional[datetime] = Field(None, description="For reschedules")
    
    # Service Details
    service_requested: Optional[str] = None
    service_not_offered_reason: Optional[str] = Field(None, description="Why service was declined")
    
    # Address Information (NEW)
    service_address_raw: Optional[str] = Field(None, description="Full address as mentioned")
    service_address_structured: Optional[ServiceAddress] = Field(None, description="Parsed address components")
    address_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence in address")
    
    # Customer Information
    customer_name: Optional[str] = None
    customer_name_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    # Intelligence Fields (NEW)
    decision_makers: List[str] = Field(default_factory=list, description="People with decision authority")
    urgency_signals: List[str] = Field(default_factory=list, description="Phrases indicating urgency")
    budget_indicators: List[str] = Field(default_factory=list, description="Phrases about budget/pricing")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Overall confidence")
    
    # Follow-up Intelligence (NEW)
    follow_up_required: bool = Field(False, description="Does this lead need follow-up?")
    follow_up_reason: Optional[str] = Field(None, description="Sales briefing for next caller")
    
    # Call Context Information (Added per API documentation)
    detected_call_type: Optional[str] = Field(None, description="Call type: fresh_sales, confirmation, follow_up, etc.")
    is_existing_customer: bool = Field(False, description="Whether customer has previous interactions")
    
    class Config:
        use_enum_values = True


class SOPCompliance(BaseModel):
    """SOP compliance evaluation"""
    score: float = Field(..., ge=0.0, le=1.0)
    compliance_rate: float = Field(..., ge=0.0, le=1.0)
    stages: Dict[str, Any] = Field(default_factory=dict)
    issues: List[str] = Field(default_factory=list)
    positive_behaviors: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ComplianceData(BaseModel):
    """Compliance evaluation data"""
    call_id: str
    target_role: str = Field(default="customer_rep")
    evaluation_mode: str = Field(default="sop_only")
    sop_compliance: SOPCompliance
    timestamps: Dict[str, Any] = Field(default_factory=dict)


class SummaryData(BaseModel):
    """Call summary data"""
    summary: str = Field(..., description="Brief summary of the call")
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    pending_actions: List[PendingAction] = Field(default_factory=list)
    sentiment_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class ObjectionsData(BaseModel):
    """Objections data"""
    objections: List[Objection] = Field(default_factory=list)
    total_count: int = 0


# ============================================================================
# LEAD SCORING MODELS
# ============================================================================

class LeadScoreBreakdown(BaseModel):
    """Score breakdown for a single component - for explainability"""
    component: str = Field(..., description="BANT component or bonus/penalty type")
    points_possible: int = Field(..., description="Maximum points for this component")
    points_earned: Optional[int] = Field(None, description="Points earned (None = not determined)")
    reason: str = Field(..., description="Human-readable explanation")
    evidence: Optional[str] = Field(None, description="Supporting evidence from transcript")


class LeadScoreData(BaseModel):
    """
    BANT-based lead score with full breakdown.
    Per manager decisions Q25-Q36.
    """
    total_score: int = Field(..., ge=0, le=100, description="Final score 0-100")
    lead_band: str = Field(..., description="hot/warm/cold classification")
    breakdown: List[LeadScoreBreakdown] = Field(default_factory=list, description="Score breakdown")
    algorithm_version: str = Field(default="1.0", description="Scoring algorithm version")
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: str = Field(default="high", description="high/medium/low based on data completeness")


# ============================================================================
# MAIN SUMMARY MODEL
# ============================================================================

class CallSummary(BaseModel):
    """Complete call summary document"""
    call_id: str
    company_id: str
    summary: SummaryData
    compliance: ComplianceData
    objections: ObjectionsData
    qualification: QualificationData
    lead_score: Optional[LeadScoreData] = Field(None, description="BANT-based lead score")
    milvus_id: Optional[str] = Field(None, description="Vector ID in Milvus")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ============================================================================
# CHUNK MODELS
# ============================================================================

class ChunkSummaryData(BaseModel):
    """Chunk-level summary"""
    summary: str
    key_points: List[str] = Field(default_factory=list)
    objections: List[Objection] = Field(default_factory=list)
    sentiment_score: float = Field(..., ge=0.0, le=1.0)


class ChunkSummary(BaseModel):
    """Chunk summary document"""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    call_id: str
    company_id: str
    chunk_index: int = Field(..., ge=1, description="Chunk sequence number")
    text: str = Field(..., description="Chunk text content")
    summary: ChunkSummaryData
    milvus_id: Optional[str] = Field(None, description="Vector ID in Milvus")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ============================================================================
# CUSTOMER MODEL
# ============================================================================

class Customer(BaseModel):
    """Customer document"""
    customer_id: str
    company_id: str
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    total_calls: int = 0
    last_call_date: Optional[datetime] = None
    qualification_status: Optional[QualificationStatus] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True

