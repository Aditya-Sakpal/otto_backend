"""
Sales rep dashboard schemas.

Response models for /sales_rep/dashboard and sub-endpoints.
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RidealongEntry(BaseModel):
    """Single ridealong (appointment) entry for dashboard."""

    appointment_id: UUID = Field(..., description="Appointment UUID")
    lead_id: Optional[UUID] = Field(None, description="Lead UUID associated with this appointment")
    customer_name: str = Field(..., description="Contact/customer name")
    sales_rep: str = Field(..., description="Assigned sales rep name")
    service_type: str = Field(..., description="Service type (e.g. Roof replacement estimate)")
    scheduled_time: str = Field(..., description="Scheduled time formatted (e.g. 9:00AM)")
    arrival_time: Optional[str] = Field(None, description="Arrival time if available (e.g. 8:55 AM)")
    status: str = Field(..., description="Status (In Progress, Won, Lost, No Show, Rescheduled)")
    ghost_mode: str = Field(..., description="Ghost mode active for rep: True or False")


class SalesTeamStatsEntry(BaseModel):
    """Single sales team stats entry."""

    sales_rep_id: UUID = Field(..., description="Sales rep user UUID")
    rep_name: str = Field(..., description="Sales rep display name")
    total_recordings_hours: float = Field(..., description="Total recording hours")
    win_rate: float = Field(..., description="Win rate percentage (0-100)")
    process_score: float = Field(..., description="Process/SOP compliance score")
    skills_score: float = Field(..., description="Skills score")
    otto_usage_hours: float = Field(..., description="Ask Otto usage hours")


class ObjectionBreakdownEntry(BaseModel):
    """Single objection in objections_breakdown (legacy format - kept for backward compatibility)."""

    objection_text: str = Field(..., description="Objection label (e.g. I need a lower price)")
    percentage: float = Field(..., description="Percentage (0-100)")


class CallLogEntry(BaseModel):
    """Single call log entry in objections call_logs."""

    call_id: str = Field(..., description="Call UUID")
    lead_id: Optional[str] = Field(None, description="Lead UUID")
    contact_name: str = Field(..., description="Contact name")
    phone_number: str = Field(..., description="Phone number")
    audio_url: Optional[str] = Field(None, description="Audio recording URL")
    call_type: Optional[str] = Field(None, description="Call type")
    duration_seconds: Optional[int] = Field(None, description="Duration in seconds")
    created_at: Optional[str] = Field(None, description="Call creation timestamp (ISO format)")
    qualification_status: Optional[str] = Field(None, description="Qualification status")
    booking_status: Optional[str] = Field(None, description="Booking status")
    transcript: Optional[str] = Field(None, description="Call transcript")
    summary: Optional[str] = Field(None, description="Call summary")


class MostCoachingNeedEntry(BaseModel):
    """Single entry in most_coaching_need array."""

    csr_id: str = Field(..., description="User ID (CSR or Sales Rep)")
    csr_name: str = Field(..., description="User name (CSR or Sales Rep)")
    unbooked_calls: int = Field(..., description="Number of unbooked calls/appointments with this objection")


class ObjectionEntry(BaseModel):
    """Single objection entry matching metrics/objections/top format."""

    objection_type: str = Field(..., description="Objection type (e.g., price, timing, authority)")
    count: int = Field(..., description="Number of calls/appointments with this objection")
    affected_leads_count: int = Field(..., description="Number of unique leads affected")
    call_logs: List[CallLogEntry] = Field(
        default_factory=list,
        description="List of calls/appointments with this objection",
    )
    most_coaching_need: List[MostCoachingNeedEntry] = Field(
        default_factory=list,
        description="List of CSRs/Sales Reps with unbooked calls/appointments for this objection",
    )


class AppointmentLogEntry(BaseModel):
    """Single appointment log entry for objections in sales dashboard."""

    call_id: Optional[str] = Field(None, description="Call UUID")
    appointment_id: Optional[str] = Field(None, description="Appointment UUID")
    lead_id: Optional[str] = Field(None, description="Lead UUID")
    contact_name: str = Field(..., description="Contact name")
    phone_number: str = Field(..., description="Phone number")
    audio_url: Optional[str] = Field(None, description="Audio recording URL")
    call_type: Optional[str] = Field(None, description="Call type")
    duration_seconds: Optional[int] = Field(None, description="Duration in seconds")
    created_at: Optional[str] = Field(None, description="Call creation timestamp (ISO format)")
    appointment_status: Optional[str] = Field(None, description="Appointment/qualification status")
    transcript: Optional[str] = Field(None, description="Call transcript")
    summary: Optional[str] = Field(None, description="Call/appointment summary")


class ObjectionAppointmentEntry(BaseModel):
    """Objection entry formatted for sales rep dashboard (appointment-focused)."""

    objection_type: str = Field(..., description="Objection type (e.g., price, timing, authority)")
    count: int = Field(..., description="Number of appointments with this objection")
    affected_appointments_count: int = Field(..., description="Number of unique appointments affected")
    appointment_logs: List[AppointmentLogEntry] = Field(
        default_factory=list,
        description="List of appointment logs with this objection",
    )


class CoreKpis(BaseModel):
    """Core KPIs for sales overview."""

    revenue: float = Field(..., description="Total revenue")
    avg_deal_size: float = Field(..., description="Average deal size")
    total_conversations: int = Field(..., description="Total conversations/calls")
    avg_recording_duration: str = Field(..., description="Average recording duration (e.g. 1h45m)")
    team_win_rate: float = Field(..., description="Team win rate percentage (0-100)")
    first_touch_win_rate: float = Field(..., description="First-touch win rate percentage")
    follow_up_win_rate: float = Field(..., description="Follow-up win rate percentage")
    follow_up_rate: float = Field(..., description="Follow-up rate percentage")
    follow_up_growth_percent: float = Field(..., description="Follow-up growth percentage")


class CloseRatePoint(BaseModel):
    """Single point in close_rate_series."""

    date: str = Field(..., description="Date label (e.g. Sep 1)")
    value: float = Field(..., description="Close rate value")


class SalesIncrease(BaseModel):
    """Sales increase trend."""

    percentage: float = Field(..., description="Percentage increase")
    value_increase: float = Field(..., description="Value increase")
    weekly_data: List[Optional[float]] = Field(
        default_factory=list,
        description="Weekly data points",
    )


class Trends(BaseModel):
    """Trends for sales overview."""

    close_rate_series: List[CloseRatePoint] = Field(
        default_factory=list,
        description="Close rate over time",
    )
    sales_increase: Optional[SalesIncrease] = Field(
        None,
        description="Sales increase metrics",
    )


class SalesOverview(BaseModel):
    """Sales overview section."""

    core_kpis: CoreKpis = Field(..., description="Core KPIs")
    trends: Trends = Field(..., description="Trends (close rate series, sales increase)")


class OttoAssistedSales(BaseModel):
    """Otto-assisted sales metrics."""

    deals_count: int = Field(..., description="Number of Otto-assisted deals")
    revenue_saved: float = Field(..., description="Revenue saved via Otto")


class AttendanceMetrics(BaseModel):
    """Attendance metrics."""

    rate: float = Field(..., description="Attendance rate percentage (0-100)")
    avg_tardiness_min: int = Field(..., description="Average tardiness in minutes")


class TeamCoachingMetrics(BaseModel):
    """Team coaching metrics section."""

    common_objection_peak: float = Field(..., description="Peak percentage for common objection")
    script_adherence: float = Field(..., description="Script adherence percentage (0-100)")
    ask_otto_usage_hours: float = Field(..., description="Ask Otto usage hours")
    win_rate_lift: float = Field(..., description="Win rate lift percentage")
    otto_assisted_sales: OttoAssistedSales = Field(..., description="Otto-assisted sales")
    attendance: AttendanceMetrics = Field(..., description="Attendance metrics")


class SalesRepObjectionLossEntry(BaseModel):
    """Objection entry specific for sales rep coaching opportunities (appointment-based)."""

    objection: str = Field(..., description="Objection text")
    appointments_lost: float = Field(..., description="Percentage of appointments lost for this objection (0-100)")
    appointment_lost_ratio: str = Field(..., description="Lost / total_with_objection (e.g. 6/12)")


class SalesRepCoachingOpportunityEntry(BaseModel):
    """Single sales-rep coaching opportunity entry (appointment-focused)."""

    user_id: str = Field(..., description="Sales rep user UUID")
    sales_rep_name: str = Field(..., description="Sales rep display name")
    success_rate: float = Field(..., description="Success rate percentage (won / total * 100)")
    win_ratio: str = Field(..., description="Won/total string (e.g. '8/16')")
    appointments_won: int = Field(..., description="Number of appointments won")
    appointments_pending: int = Field(..., description="Number of appointments assigned (pending/resolved) - total appointments")
    total_appointments: int = Field(..., description="Total appointments (same as appointments_pending)")
    most_coaching_need: List[SalesRepObjectionLossEntry] = Field(
        default_factory=list,
        description="Top objections with appointment-lost metrics",
    )


class SalesRepDashboardResponse(BaseModel):
    """Main dashboard response with ridealongs, sales team stats, and overview sections."""

    ridealongs_list: List[RidealongEntry] = Field(
        default_factory=list,
        description="Latest appointments of the day (up to 9)",
    )
    sales_team_stats: List[SalesTeamStatsEntry] = Field(
        default_factory=list,
        description="Sales team stats (up to 3)",
    )
    objections: List[ObjectionAppointmentEntry] = Field(
        default_factory=list,
        description="Top objections (appointment-focused) with appointment_logs",
    )
    sales_overview: Optional[SalesOverview] = Field(
        None,
        description="Sales overview (core KPIs and trends)",
    )
    team_coaching_metrics: Optional[TeamCoachingMetrics] = Field(
        None,
        description="Team coaching metrics",
    )
    most_coaching_opportunities: List[SalesRepCoachingOpportunityEntry] = Field(
        default_factory=list,
        description="Most coaching opportunities for sales reps (appointment-focused list)",
    )


class SalesTeamStatsPaginatedResponse(BaseModel):
    """Paginated sales team stats response."""

    items: List[SalesTeamStatsEntry] = Field(
        default_factory=list,
        description="List of sales team stats",
    )
    total: Optional[int] = Field(
        None,
        description="Total count (when pagination used)",
    )
