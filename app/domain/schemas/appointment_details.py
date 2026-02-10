"""
Appointment details schema for GET /sales_rep/exec/appointments/{appointment_id}.
"""
from typing import List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field


class AppointmentOverview(BaseModel):
    """Appointment overview: deal info, summary, SOP stages, and optional CSR booking data."""

    deal_size: Optional[float] = Field(None, description="Deal size (e.g. 25600)")
    deal_type: Optional[str] = Field(None, description="Deal/service type (e.g. Roof replacement)")
    appointment_summary: List[str] = Field(
        default_factory=list,
        description="Summary bullets from the appointment/call analysis",
    )
    sop_stages_completed: List[str] = Field(
        default_factory=list,
        description="SOP stages completed",
    )
    sop_stages_missed: List[str] = Field(
        default_factory=list,
        description="SOP stages missed",
    )
    appointment_booking: Optional[dict[str, Any]] = Field(
        None,
        description="Data on how the CSR booked the appointment, if available",
    )


class AppointmentDetailsResponse(BaseModel):
    """Response for GET /sales_rep/exec/appointments/{appointment_id}."""

    appointment_id: UUID = Field(..., description="Appointment UUID")
    customer_name: str = Field(..., description="Customer/contact name")
    sales_rep_name: str = Field(..., description="Assigned sales rep name")
    status: str = Field(..., description="Status (e.g. Won, Lost, In Progress)")
    appointment_overview: AppointmentOverview = Field(
        ...,
        description="Deal info, summary, SOP stages, and optional booking data",
    )
