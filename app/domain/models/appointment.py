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
    outcome: Optional[AppointmentOutcome] = Field(None, description="Appointment outcome")
    assigned_rep_id: Optional[UUID] = Field(None, description="Assigned sales rep")
    interaction_id: Optional[UUID] = Field(None, description="Associated call/interaction ID")
    audio_url: Optional[str] = Field(None, description="Audio recording URL")
    recording_status: Optional[str] = Field(None, description="Recording status (e.g. uploaded)")
    analysis_status: Optional[str] = Field(None, description="Analysis status (e.g. processing, completed)")
    shunya_job_id: Optional[str] = Field(None, description="Shunya processing job ID")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

