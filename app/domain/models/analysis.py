"""
Analysis domain models.

Represents AI analysis results for calls.
"""
from typing import Optional, List, Union
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import AnalysisStatus


class CallAnalysis(BaseModel):
    """
    Call analysis model.

    Stores complete AI analysis results for a call from Shunya Summary API:
    - Summary with action items, next steps, pending actions
    - Compliance with issues and positive behaviors
    - Objections with detailed information
    - Qualification with BANT scores and appointment details
    - Customer and service information
    """
    call_id: UUID = Field(..., description="Associated call ID")
    company_id: UUID = Field(..., description="Company/tenant ID")
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING, description="Analysis status")

    # Qualification
    qualification_status: Optional[str] = Field(None, description="Qualification status")
    booking_status: Optional[str] = Field(None, description="Booking status")

    # Objections
    # Note: Using List[str] instead of List[ObjectionType] because Shunya sends arbitrary objection types
    # that may not match our enum values (e.g., "Itinerary/booking error (complaint)")
    objections: List[str] = Field(default_factory=list, description="Detected objections (as strings from Shunya)")
    objection_texts: List[str] = Field(default_factory=list, description="Objection details")
    objections_total_count: int = Field(default=0, description="Total number of objections detected")

    # SOP Compliance
    # Note: Using List[str] instead of List[SOPStage] because Shunya sends descriptive stage names
    # that don't match our enum values (e.g., "Greeting & Identification", "Needs Discovery")
    sop_stages_completed: List[str] = Field(default_factory=list, description="Completed SOP stages (as strings from Shunya)")
    sop_stages_missed: List[str] = Field(default_factory=list, description="Missed SOP stages (as strings from Shunya)")
    sop_stages_total: Optional[int] = Field(None, description="Total number of SOP stages evaluated")
    sop_compliance_score: Optional[float] = Field(None, description="SOP compliance score (0-1)")
    sop_compliance_rate: Optional[float] = Field(None, description="SOP compliance rate (0-1)")
    sop_compliance_confidence: Optional[float] = Field(None, description="SOP compliance confidence score (0-1)")
    sop_compliance_issues: List[str] = Field(default_factory=list, description="List of SOP compliance issues")
    sop_compliance_positive_behaviors: List[str] = Field(default_factory=list, description="List of positive behaviors observed")

    # Sentiment
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (0-1)")

    # Summary
    summary: Optional[str] = Field(None, description="Call summary text")
    key_points: List[str] = Field(default_factory=list, description="Key points from call")
    action_items: List[str] = Field(default_factory=list, description="Action items identified")
    next_steps: List[str] = Field(default_factory=list, description="Next steps identified")
    pending_actions: Optional[List[dict]] = Field(None, description="Pending actions with details (type, owner, due_at, raw_text, confidence, contact_method)")
    summary_confidence_score: Optional[float] = Field(None, description="Confidence score for summary (0-1)")

    # BANT Scores
    bant_need_score: Optional[float] = Field(None, description="BANT Need score (0-1)")
    bant_budget_score: Optional[float] = Field(None, description="BANT Budget score (0-1)")
    bant_timeline_score: Optional[float] = Field(None, description="BANT Timeline score (0-1)")
    bant_authority_score: Optional[float] = Field(None, description="BANT Authority score (0-1)")
    qualification_overall_score: Optional[float] = Field(None, description="Overall qualification score (0-1)")
    qualification_confidence_score: Optional[float] = Field(None, description="Confidence score for qualification assessment (0-1)")
    call_outcome_category: Optional[str] = Field(None, description="Call outcome category (e.g., qualified_but_unbooked)")

    # Appointment
    appointment_confirmed: bool = Field(default=False, description="Whether appointment was confirmed")
    appointment_date: Optional[datetime] = Field(None, description="Scheduled appointment date and time")
    appointment_type: Optional[str] = Field(None, description="Appointment type (e.g., in-person, virtual, phone)")
    appointment_timezone: Optional[str] = Field(None, description="Timezone for appointment")
    appointment_time_confidence: Optional[float] = Field(None, description="Confidence score for appointment time extraction (0-1)")
    preferred_time_window: Optional[str] = Field(None, description="Preferred time window for appointment")
    appointment_intent: Optional[str] = Field(None, description="Appointment intent (e.g., new, reschedule, cancel)")
    original_appointment_datetime: Optional[datetime] = Field(None, description="Original appointment datetime (for reschedules)")
    new_requested_time: Optional[datetime] = Field(None, description="New requested appointment time (for reschedules)")

    # Service
    service_requested: Optional[str] = Field(None, description="Service requested by customer")
    service_not_offered_reason: Optional[str] = Field(None, description="Reason if service was not offered")
    service_address_raw: Optional[str] = Field(None, description="Raw service address as mentioned in call")
    service_address_structured: Optional[dict] = Field(None, description="Structured service address: {line1, city, state, postal_code, country}")
    address_confidence: Optional[float] = Field(None, description="Confidence score for address extraction (0-1)")

    # Customer
    customer_name: Optional[str] = Field(None, description="Customer name extracted from call")
    customer_name_confidence: Optional[float] = Field(None, description="Confidence score for customer name extraction (0-1)")
    decision_makers: List[str] = Field(default_factory=list, description="List of decision makers identified")
    urgency_signals: List[str] = Field(default_factory=list, description="Urgency signals detected (quotes or phrases)")
    budget_indicators: List[str] = Field(default_factory=list, description="Budget indicators detected (quotes or phrases)")

    # Follow-up
    follow_up_required: bool = Field(default=False, description="Whether follow-up is required")
    follow_up_reason: Optional[str] = Field(None, description="Reason why follow-up is required")

    # Compliance
    compliance_target_role: Optional[str] = Field(None, description="The role this call was evaluated against")

    # Additional qualification fields (from Shunya Summary API)
    detected_call_type: Optional[str] = Field(None, description="Type of call: fresh_sales, follow_up_inquiry, existing_customer_service")
    is_existing_customer: Optional[bool] = Field(None, description="Whether this is an existing customer")
    is_deprioritized: Optional[bool] = Field(None, description="Whether service is deprioritized per tenant rules")
    service_wait_time_weeks: Optional[int] = Field(None, description="Wait time in weeks if service is deferred")
    applied_rules: List[str] = Field(default_factory=list, description="Tenant-specific rules that were applied")
    property_details: Optional[dict] = Field(None, description="Home services property information (roof_type, roof_age_years, stories, hoa_status, etc.)")
    customer_details: Optional[dict] = Field(None, description="Customer details with address, phone, email, decision_makers")

    # Scope
    scope: Optional[str] = Field(None, description="Whether call is in-scope or out-of-scope (in/out)")

    # Raw analysis data
    raw_analysis: Optional[dict] = Field(None, description="Raw analysis data from AI")

    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

