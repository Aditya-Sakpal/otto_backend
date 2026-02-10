"""
Sales rep stat API schemas.

Response model for GET /sales_rep/stat/{sales_rep_id}.
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PersonalStat(BaseModel):
    """Personal stats for a sales rep."""

    total_recordings: int = Field(..., description="Total number of call recordings")
    win_rate: float = Field(..., description="Win rate percentage")
    win_rate_first_touch: float = Field(..., description="First-touch win rate percentage")
    win_rate_follow_ups: float = Field(..., description="Follow-up win rate percentage")
    average_follow_up_per_lead: float = Field(
        ..., description="Average follow-up touches per lead"
    )
    average_follow_up_to_win: float = Field(
        ..., description="Average follow-up touches to close a won deal"
    )
    attendance_rate: float = Field(..., description="Attendance rate percentage")
    tardiness: int = Field(..., description="Average tardiness in minutes")
    average_deal_size: float = Field(..., description="Average deal size")


class PendingLeadItem(BaseModel):
    """Single pending lead in sales rep stat."""

    name: str = Field(..., description="Contact name")
    looking_for: str = Field("", description="Intent / what they are looking for")
    objection: str = Field("", description="Primary objection (e.g. price/insurance)")
    last_touched: Optional[str] = Field(None, description="Last touched date (YYYY-MM-DD)")
    sales_rep: str = Field("", description="Assigned sales rep name")
    address: str = Field("", description="Contact address")
    date_of_appointment: Optional[str] = Field(
        None, description="Appointment date (YYYY-MM-DD)"
    )
    follow_up: int = Field(0, description="Follow-up count")
    tasks: str = Field("", description="Tasks as semicolon-separated string")
    appointment_recording: str = Field("", description="Recording URL")
    summary: str = Field("", description="Summary notes")


class SalesRepStatResponse(BaseModel):
    """Response for GET /sales_rep/stat/{sales_rep_id}."""

    id: UUID = Field(..., description="Sales rep user UUID")
    rep_name: str = Field(..., description="Sales rep display name")
    personal_stat: PersonalStat = Field(..., description="Personal statistics")
    pending_lead: List[PendingLeadItem] = Field(
        default_factory=list,
        description="Pending leads for this rep",
    )
