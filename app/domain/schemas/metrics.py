"""
Metrics response schemas.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class CompanyOverviewResponse(BaseModel):
    """Company overview metrics.

    Qualified leads include leads with status: qualified_booked, qualified_unbooked,
    or qualified_service_not_offered.
    """
    total_leads: int = Field(..., description="Total number of leads in date range")
    active_leads: int = Field(..., description="Number of active (non-closed) leads")
    qualified_leads: Optional[int] = Field(None, description="Number of qualified leads (qualified_booked + qualified_unbooked + qualified_service_not_offered)")
    total_calls: int = Field(..., description="Total number of calls in date range")
    missed_calls: int = Field(..., description="Number of missed calls")
    total_appointments: int = Field(..., description="Total appointments in date range")
    conversion_rate: float = Field(..., description="Lead-to-sale conversion rate (0-100)")
    booked_leads: Optional[int] = Field(None, description="Number of leads with booked appointments")
    total_revenue: float = Field(..., description="Total revenue from closed-won deals")
    start_date: Optional[str] = Field(None, description="Start of date range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End of date range (YYYY-MM-DD)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_leads": 250,
                "active_leads": 180,
                "qualified_leads": 95,
                "total_calls": 420,
                "missed_calls": 35,
                "total_appointments": 65,
                "conversion_rate": 18.5,
                "booked_leads": 42,
                "total_revenue": 125000.00,
                "start_date": "2026-02-20",
                "end_date": "2026-03-20",
            }
        }
    }


class CSRDashboardResponse(BaseModel):
    """CSR dashboard metrics."""
    total_calls: int = Field(..., description="Total calls handled by this CSR")
    missed_calls: int = Field(..., description="Number of missed calls")
    calls_today: int = Field(..., description="Calls handled today")
    avg_call_duration: float = Field(..., description="Average call duration in seconds")
    leads_assigned: int = Field(..., description="Number of leads assigned to this CSR")
    appointments_scheduled: int = Field(..., description="Number of appointments scheduled by this CSR")
    start_date: Optional[str] = Field(None, description="Start of date range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End of date range (YYYY-MM-DD)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_calls": 85,
                "missed_calls": 5,
                "calls_today": 12,
                "avg_call_duration": 145.5,
                "leads_assigned": 30,
                "appointments_scheduled": 15,
                "start_date": "2026-02-20",
                "end_date": "2026-03-20",
            }
        }
    }


class BookingRateImprovementResponse(BaseModel):
    """Booking rate improvement metrics."""
    # Legacy single-period fields (made optional to support dual-period response)
    current_rate: Optional[float] = None
    previous_rate: Optional[float] = None
    improvement_percentage: Optional[float] = None
    total_bookings: Optional[int] = None
    total_qualified: Optional[int] = None
    booked_appointments: Optional[int] = None
    booked_calls: Optional[int] = None
    booked_leads: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    previous_period_start: Optional[str] = None
    previous_period_end: Optional[str] = None
    # Optional dual-period series for frontend comparison (new mode)
    period_a: Optional[Dict[str, Any]] = None
    period_b: Optional[Dict[str, Any]] = None
    x_axis: Optional[List[str]] = None
    y_axis: Optional[List[float]] = None


class CloseRateTrendsResponse(BaseModel):
    """Close rate trends metrics (similar to booking rate but for closed/won deals)."""
    # Legacy single-period fields (made optional to support dual-period response)
    current_rate: Optional[float] = None
    previous_rate: Optional[float] = None
    improvement_percentage: Optional[float] = None
    total_closed: Optional[int] = None
    total_qualified: Optional[int] = None
    closed_appointments: Optional[int] = None
    closed_leads: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    previous_period_start: Optional[str] = None
    previous_period_end: Optional[str] = None
    # Optional dual-period series for frontend comparison (new mode)
    period_a: Optional[Dict[str, Any]] = None
    period_b: Optional[Dict[str, Any]] = None
    x_axis: Optional[List[str]] = None
    y_axis: Optional[List[float]] = None


class TopObjectionResponse(BaseModel):
    """Top objection data."""
    objection_type: str = Field(..., description="Objection type from CSRObjectionType enum (e.g. 'service_fee_concerns', 'scheduling_conflicts')")
    count: int = Field(..., description="Number of calls with this objection")
    percentage: float = Field(..., description="Percentage of total calls with objections (0-100)")


class TopObjectionsResponse(BaseModel):
    """Top objections list."""
    objections: List[TopObjectionResponse] = Field(..., description="List of top objections sorted by frequency")
    total_calls_with_objections: int = Field(..., description="Total number of calls that had at least one objection")
    start_date: Optional[str] = Field(None, description="Start of date range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End of date range (YYYY-MM-DD)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "objections": [
                    {"objection_type": "service_fee_concerns", "count": 28, "percentage": 35.0},
                    {"objection_type": "scheduling_conflicts", "count": 20, "percentage": 25.0},
                    {"objection_type": "customer_needs_time_to_decide", "count": 15, "percentage": 18.75},
                ],
                "total_calls_with_objections": 80,
                "start_date": "2026-02-20",
                "end_date": "2026-03-20",
            }
        }
    }


class MissedCallsResponse(BaseModel):
    """Missed calls metrics."""
    missed_calls: int = Field(..., description="Number of missed calls")
    total_calls: int = Field(..., description="Total number of calls")
    miss_rate: float = Field(..., description="Missed call rate (0-100)")
    picked_up: int = Field(0, description="Number of missed calls that were later picked up")
    booked: int = Field(0, description="Number of missed calls that resulted in bookings")
    booking_percentage: float = Field(0.0, description="Booking percentage from missed calls (0-100)")
    recent_missed: List[Dict[str, Any]] = Field(default_factory=list, description="List of recent missed call details")
    start_date: Optional[str] = Field(None, description="Start of date range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End of date range (YYYY-MM-DD)")


class CoachingOpportunityResponse(BaseModel):
    """Coaching opportunity data."""
    call_id: UUID
    rep_id: Optional[UUID]
    sop_compliance_score: float
    sop_stages_missed: List[str]
    sentiment_score: Optional[float]


class CoachingOpportunitiesResponse(BaseModel):
    """Coaching opportunities list."""
    opportunities: List[CoachingOpportunityResponse]
    total_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class MostCoachingNeedItem(BaseModel):
    """Per-objection coaching need: objection name with % Unbooked and # Unbooked/Qualified."""
    objection: str
    pct_unbooked: float = Field(..., description="% Unbooked (unbooked/qualified * 100)")
    unbooked_qualified_ratio: str = Field(..., description="# Unbooked / Qualified (e.g. '3/10')")
    unbooked_count: int = 0
    qualified_count: int = 0


class MostCoachingOpportunityResponse(BaseModel):
    """Most coaching opportunity data for an employee."""
    user_id: str
    csr_name: str
    success_rate: float
    booked_qualified_ratio: str
    booked_leads: int
    qualified_leads: int
    total_calls: int
    most_coaching_need: List[MostCoachingNeedItem]  # Top 3 objections with % Unbooked and # Unbooked/Qualified


class MostCoachingOpportunitiesResponse(BaseModel):
    """Most coaching opportunities list - top 5 employees with least success rate."""
    opportunities: List[MostCoachingOpportunityResponse]
    total_count: int
    start_date: str
    end_date: str


class ConversionMetricsResponse(BaseModel):
    """Lead to sale conversion metrics."""
    total_leads: int
    converted_leads: int
    conversion_rate: float
    avg_days_to_conversion: float
    total_revenue: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class EmergencyDroppedResponse(BaseModel):
    """Emergency/dropped calls metrics."""
    dropped_calls: int
    emergency_calls: int
    drop_rate: float
    avg_response_time: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CompanyPerformanceResponse(BaseModel):
    """Company performance metrics."""
    total_revenue: float
    total_leads: int
    conversion_rate: float
    avg_deal_size: float
    active_reps: int
    calls_per_rep: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CallsSummaryResponse(BaseModel):
    """Calls summary metrics."""
    total_calls: int
    answered_calls: int
    missed_calls: int
    avg_duration: float
    total_duration: int
    calls_today: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class BookingsSummaryResponse(BaseModel):
    """Bookings summary metrics."""
    total_bookings: int
    confirmed_bookings: int
    pending_bookings: int
    cancelled_bookings: int
    bookings_today: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class UnbookedLeadsResponse(BaseModel):
    """Unbooked leads metrics."""
    total_unbooked: int
    qualified_unbooked: int
    avg_days_unbooked: float
    leads: List[Dict[str, Any]]
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class PendingActionsResponse(BaseModel):
    """Pending actions metrics."""
    total_pending: int
    follow_ups_needed: int
    calls_to_make: int
    appointments_to_schedule: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ConversionsPendingToBookedResponse(BaseModel):
    """Conversions from pending to booked."""
    converted_count: int
    conversion_rate: float
    avg_days_to_book: float
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class ObjectionsSummaryResponse(BaseModel):
    """Objections summary."""
    total_objections: int
    unique_objection_types: int
    top_objection: str
    objections_by_type: Dict[str, int]
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ObjectionCallsResponse(BaseModel):
    """Calls with specific objection type."""
    objection_type: str
    total_calls: int
    calls: List[Dict[str, Any]]


class CoachingInsight(BaseModel):
    """Coaching insight item."""
    type: str = Field(..., description="Type of insight: objection_handling, script_adherence, response_time, lead_qualification")
    title: str = Field(..., description="Title of the insight")
    message: str = Field(..., description="Detailed message/feedback")
    status: str = Field(..., description="Status: positive, warning, recommendation")
    improvement_percentage: Optional[float] = Field(None, description="Improvement percentage if applicable")


class ExecutiveViewMetrics(BaseModel):
    """Executive view metrics."""
    booking_rate: float = Field(..., description="Booking rate percentage")
    conversion_rate: float = Field(..., description="Conversion rate percentage")
    calls_answered: int = Field(..., description="Number of calls answered")
    total_calls: int = Field(..., description="Total number of calls")
    avg_response_time: float = Field(..., description="Average response time in seconds")
    response_time_target: float = Field(default=15.0, description="Target response time in seconds")


class CSRProfileResponse(BaseModel):
    """CSR profile with all metrics and insights."""
    # User info
    user_id: UUID
    name: str = Field(..., description="Full name (first_name + last_name)")
    email: str
    role: str
    rank: Optional[int] = Field(None, description="Rank among CSRs (1-based)")
    total_csrs: int = Field(..., description="Total number of CSRs in company")
    
    # KPIs
    total_calls: int
    calls_answered: int
    calls_answered_percentage: float
    missed_calls: int
    missed_calls_status: str = Field(..., description="Status: low, medium, high")
    booked_appointments: int
    total_leads: int
    qualified_leads: int
    booking_rate: float
    avg_response_time: float
    response_time_status: str = Field(..., description="Status: on_target, above_target, below_target")
    
    # Executive view
    executive_view: ExecutiveViewMetrics
    
    # Coaching insights
    coaching_insights: List[CoachingInsight]
    
    # Date range
    start_date: datetime
    end_date: datetime
