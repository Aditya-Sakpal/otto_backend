"""
Metrics response schemas.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel


class CompanyOverviewResponse(BaseModel):
    """Company overview metrics."""
    total_leads: int
    active_leads: int
    total_calls: int
    missed_calls: int
    total_appointments: int
    conversion_rate: float
    total_revenue: float


class CSRDashboardResponse(BaseModel):
    """CSR dashboard metrics."""
    total_calls: int
    missed_calls: int
    calls_today: int
    avg_call_duration: float
    leads_assigned: int
    appointments_scheduled: int


class BookingRateImprovementResponse(BaseModel):
    """Booking rate improvement metrics."""
    current_rate: float
    previous_rate: float
    improvement_percentage: float
    total_bookings: int
    total_qualified: int


class TopObjectionResponse(BaseModel):
    """Top objection data."""
    objection_type: str
    count: int
    percentage: float


class TopObjectionsResponse(BaseModel):
    """Top objections list."""
    objections: List[TopObjectionResponse]
    total_calls_with_objections: int


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


class ConversionMetricsResponse(BaseModel):
    """Lead to sale conversion metrics."""
    total_leads: int
    converted_leads: int
    conversion_rate: float
    avg_days_to_conversion: float
    total_revenue: float


class EmergencyDroppedResponse(BaseModel):
    """Emergency/dropped calls metrics."""
    dropped_calls: int
    emergency_calls: int
    drop_rate: float
    avg_response_time: float


class CompanyPerformanceResponse(BaseModel):
    """Company performance metrics."""
    total_revenue: float
    total_leads: int
    conversion_rate: float
    avg_deal_size: float
    active_reps: int
    calls_per_rep: float


class CallsSummaryResponse(BaseModel):
    """Calls summary metrics."""
    total_calls: int
    answered_calls: int
    missed_calls: int
    avg_duration: float
    total_duration: int
    calls_today: int


class BookingsSummaryResponse(BaseModel):
    """Bookings summary metrics."""
    total_bookings: int
    confirmed_bookings: int
    pending_bookings: int
    cancelled_bookings: int
    bookings_today: int


class UnbookedLeadsResponse(BaseModel):
    """Unbooked leads metrics."""
    total_unbooked: int
    qualified_unbooked: int
    avg_days_unbooked: float
    leads: List[Dict[str, Any]]


class PendingActionsResponse(BaseModel):
    """Pending actions metrics."""
    total_pending: int
    follow_ups_needed: int
    calls_to_make: int
    appointments_to_schedule: int


class ConversionsPendingToBookedResponse(BaseModel):
    """Conversions from pending to booked."""
    converted_count: int
    conversion_rate: float
    avg_days_to_book: float
    period_start: datetime
    period_end: datetime


class ObjectionsSummaryResponse(BaseModel):
    """Objections summary."""
    total_objections: int
    unique_objection_types: int
    top_objection: str
    objections_by_type: Dict[str, int]


class ObjectionCallsResponse(BaseModel):
    """Calls with specific objection type."""
    objection_type: str
    total_calls: int
    calls: List[Dict[str, Any]]

