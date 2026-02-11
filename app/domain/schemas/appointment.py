"""
Appointment Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

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


class AppointmentInsightSummary(BaseModel):
    """Structured insights extracted from the related call analysis."""

    summary: Optional[str] = Field(
        None,
        description="Summary of the associated call",
    )
    key_points: List[str] = Field(
        default_factory=list,
        description="Key points discussed during the call",
    )
    sop_stages_completed: List[str] = Field(
        default_factory=list,
        description="SOP stages that were completed",
    )
    sop_stages_missed: List[str] = Field(
        default_factory=list,
        description="SOP stages that were missed",
    )
    objections: List[str] = Field(
        default_factory=list,
        description="Objections raised during the call",
    )
    action_items: List[str] = Field(
        default_factory=list,
        description="Action items identified during the call",
    )
    follow_up_required: Optional[bool] = Field(
        None,
        description="Whether a follow-up is required",
    )
    follow_up_reason: Optional[str] = Field(
        None,
        description="Reason for the required follow-up, if any",
    )


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

    class Config:
        from_attributes = True

