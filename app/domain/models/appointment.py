"""
Appointment domain model.

Represents a scheduled meeting/visit.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import AppointmentOutcome


class Appointment(BaseModel):
    """
    Appointment model.

    Represents a scheduled meeting or sales visit.
    """
    company_id: UUID = Field(..., description="Company/tenant ID")
    lead_id: UUID = Field(..., description="Associated lead")
    contact_card_id: UUID = Field(..., description="Associated contact")
    scheduled_start: datetime = Field(..., description="Scheduled start time")
    scheduled_end: Optional[datetime] = Field(None, description="Scheduled end time")
    location_address: Optional[str] = Field(None, description="Location address")
    latitude: Optional[float] = Field(None, description="Geocoded latitude")
    longitude: Optional[float] = Field(None, description="Geocoded longitude")
    outcome: Optional[AppointmentOutcome] = Field("pending", description="Appointment outcome")
    assigned_rep_id: Optional[UUID] = Field(None, description="Assigned sales rep")
    interaction_id: Optional[UUID] = Field(None, description="Associated call/interaction ID")
    audio_url: Optional[str] = Field(None, description="Audio recording URL")
    transcript: Optional[str] = Field(None)
    duration_seconds: Optional[int] = Field(None)
    summary: Optional[str] = Field(None)
    objections: Optional[list[str]] = Field(None)
    objection_texts: Optional[list[str]] = Field(None)
    objections_total_count: Optional[int] = Field(None)
    qualification_status: Optional[str] = Field(None)
    booking_status: Optional[str] = Field(None)
    handled_by_user_id: Optional[UUID] = Field(None)
    extra_metadata: Optional[dict] = Field(None)
    sop_stages_completed: Optional[list[str]] = Field(None)
    sop_stages_missed: Optional[list[str]] = Field(None)
    sop_stages_total: Optional[int] = Field(None)
    sop_compliance_score: Optional[float] = Field(None)
    sop_compliance_rate: Optional[float] = Field(None)
    sop_compliance_confidence: Optional[float] = Field(None)
    sop_compliance_issues: Optional[list[str]] = Field(None)
    sop_compliance_positive_behaviors: Optional[list[str]] = Field(None)
    compliance_target_role: Optional[str] = Field(None)
    sentiment_score: Optional[float] = Field(None)
    key_points: Optional[list[str]] = Field(None)
    action_items: Optional[list[str]] = Field(None)
    next_steps: Optional[list[str]] = Field(None)
    pending_actions_data: Optional[dict] = Field(None)
    recording_status: Optional[str] = Field(None)
    analysis_status: Optional[str] = Field(None)
    shunya_job_id: Optional[str] = Field(None)

