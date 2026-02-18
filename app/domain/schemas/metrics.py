"""
Metrics response schemas.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class CompanyOverviewResponse(BaseModel):
    """Company overview metrics."""
    total_leads: int
    active_leads: int
    qualified_leads: Optional[int] = None
    total_calls: int
    missed_calls: int
    total_appointments: int
    conversion_rate: float
    booked_leads: Optional[int] = None
    total_revenue: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CSRDashboardResponse(BaseModel):
    """CSR dashboard metrics."""
    total_calls: int
    missed_calls: int
    calls_today: int
    avg_call_duration: float
    leads_assigned: int
    appointments_scheduled: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


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
    objection_type: str
    count: int
    percentage: float


class TopObjectionsResponse(BaseModel):
    """Top objections list."""
    objections: List[TopObjectionResponse]
    total_calls_with_objections: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class MissedCallsResponse(BaseModel):
    """Missed calls metrics."""
    missed_calls: int
    total_calls: int
    miss_rate: float
    recent_missed: List[Dict[str, Any]] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


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
