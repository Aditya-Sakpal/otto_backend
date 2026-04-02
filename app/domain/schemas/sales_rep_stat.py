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

    lead_id: UUID = Field(..., description="Lead UUID")
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


SALES_REP_STAT_RESPONSE_EXAMPLE = {
    "id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
    "rep_name": "Anthony Bonom",
    "personal_stat": {
        "total_recordings": 12,
        "win_rate": 0.5,
        "win_rate_first_touch": 0.11,
        "win_rate_follow_ups": 0.4,
        "average_follow_up_per_lead": 0.18,
        "average_follow_up_to_win": 0.18,
        "attendance_rate": 0.94,
        "tardiness": 0,
        "average_deal_size": 14718.2,
    },
    "pending_lead": [
        {
            "lead_id": "263f1cac-f634-4b57-9a7a-a22715c82839",
            "name": "MICHAEL PINA",
            "looking_for": "new",
            "objection": "",
            "last_touched": "2026-03-28",
            "sales_rep": "Anthony Bonom",
            "address": "Phoenix, AZ, 85001",
            "date_of_appointment": "2026-03-25",
            "follow_up": 0,
            "tasks": (
                "Technician to arrive for the scheduled inspection on 2026-03-25 within the "
                "7:30–9:00 AM window.; Technician to call the customer about 30 minutes before "
                "arrival and review roof photos/findings, then send multiple proposal options to "
                "the provided email."
            ),
            "appointment_recording": (
                "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/"
                "1a872128-35b1-441d-9422-54bcb97e3f4d/4107271985.mp3"
            ),
            "summary": (
                "Bronte from Arizona Roofers returned a missed call and confirmed the homeowner, "
                "Michael Pina, is seeking roofing help after receiving unexpected roofing-related "
                "calls. Michael wants to replace/redo both a connected flat-roof section (including "
                "a smaller addition tied into a patio/carport area) and the asphalt shingle portion, "
                "prompted by minor leaks believed to be on both the flat and shingled areas. Bronte "
                "gathered property details (address, roof type mix, no solar, no HOA, no gate/access "
                "issues), confirmed Michael is the property owner, and collected contact preferences "
                "(text confirmations) and an email for sending multiple proposal options. They "
                "scheduled a complimentary full roof inspection and estimate for Wednesday, "
                "2026-03-25 with a 7:30–9:00 AM arrival window, with the technician to call about "
                "30 minutes before arrival."
            ),
        },
    ],
}


class SalesRepStatResponse(BaseModel):
    """Response for GET /sales_rep/stat/{sales_rep_id}."""

    id: UUID = Field(..., description="Sales rep user UUID")
    rep_name: str = Field(..., description="Sales rep display name")
    personal_stat: PersonalStat = Field(..., description="Personal statistics")
    pending_lead: List[PendingLeadItem] = Field(
        default_factory=list,
        description="Pending leads for this rep",
    )

    model_config = {
        "json_schema_extra": {"example": SALES_REP_STAT_RESPONSE_EXAMPLE},
    }
