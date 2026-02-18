"""
Metrics API routes.

Provides analytics and metrics endpoints with date range filtering.
Most endpoints require either company_id or user_id (with user_id taking precedence if both are provided).
All endpoints support start_date/end_date for filtering.
"""
from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession, get_current_user
from app.core.permissions import require_executive, require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.models.pending_action import PendingAction
from app.domain.schemas.metrics import (
    CompanyOverviewResponse,
    CSRDashboardResponse,
    MissedCallsResponse,
    BookingRateImprovementResponse,
    CloseRateTrendsResponse,
    TopObjectionsResponse,
    ObjectionsSummaryResponse,
    CoachingOpportunitiesResponse,
    MostCoachingOpportunitiesResponse,
    ConversionMetricsResponse,
    ConversionsPendingToBookedResponse,
    EmergencyDroppedResponse,
    CompanyPerformanceResponse,
    CallsSummaryResponse,
    BookingsSummaryResponse,
    UnbookedLeadsResponse,
    PendingActionsResponse,
    CSRProfileResponse,
)
from app.services.metrics_service import MetricsService
from app.services.analytics_service import AnalyticsService
from app.services.pending_action_service import PendingActionService

router = APIRouter(tags=["metrics"])

RESPONSES = {
    400: {"description": "Bad request (e.g. missing company_id or user_id)"},
    403: {"description": "Forbidden"},
    404: {"description": "Resource not found"},
    500: {"description": "Internal server error"},
}


@router.get("/exec/company-overview", response_model=CompanyOverviewResponse, responses=RESPONSES)
async def get_company_overview(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope overview metrics to a single user (optional)"),
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get company overview metrics within date range.
    
    - **company_id**: Company UUID (optional if user_id is provided)
    - **user_id**: User UUID (optional). If provided, metrics are calculated only for that user. If both company_id and user_id are provided, user_id is used.
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total leads, active leads, qualified leads, calls, missed calls, appointments,
    conversion rate, and total revenue.
    
    Qualified leads include leads with status: qualified_booked, qualified_unbooked, 
    or qualified_service_not_offered.
    
    Required role: EXECUTIVE
    """
    # Resolution rules:
    # - If user_id is provided: prefer user_id (even if company_id is also provided)
    # - Else if company_id is provided: use company_id
    # - Else: error
    if not company_id and not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )

    if user_id:
        company_id = None  # ensure user_id takes precedence (service will derive company_id from user)

    service = MetricsService(db)
    return await service.get_company_overview(
        company_id=company_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/exec/csr/dashboard", response_model=CSRDashboardResponse, responses=RESPONSES)
async def get_csr_dashboard(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope dashboard metrics to a single user (optional)"),
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get CSR dashboard metrics within date range.
    
    - **company_id**: Company UUID (optional if user_id is provided)
    - **user_id**: User UUID (optional). If provided, metrics are calculated only for that user. If both company_id and user_id are provided, user_id is used.
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total calls, missed calls, calls today, average call duration,
    leads assigned, and appointments scheduled.
    
    Required role: EXECUTIVE
    """
    # Resolution rules:
    # - If user_id is provided: prefer user_id (even if company_id is also provided)
    # - Else if company_id is provided: use company_id
    # - Else: error
    if not company_id and not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )

    if user_id:
        company_id = None  # ensure user_id takes precedence (service will derive company_id from user)

    service = MetricsService(db)
    return await service.get_csr_dashboard(
        company_id=company_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/exec/missed-calls", response_model=MissedCallsResponse, responses=RESPONSES)
async def get_missed_calls(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get missed calls metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns missed call count, total calls, miss rate, and recent missed calls.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_missed_calls(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/csr/auto-queued-leads", responses=RESPONSES)
async def get_auto_queued_leads(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of leads to return"),
):
    """
    Get auto-queued leads for CSR within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    - **limit**: Maximum number of leads (default: 20)
    
    Returns leads prioritized by status (hot > warm > new).
    
    Required role: CSR or EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_auto_queued_leads(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/booking-rate-improvement", response_model=BookingRateImprovementResponse, responses=RESPONSES)
async def get_booking_rate_improvement(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope booking rate improvement to a single user (optional)"),
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    # Backwards-compatible single-period params:
    start_date: Optional[date] = Query(None, description="(legacy) Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="(legacy) End date for filtering (YYYY-MM-DD)"),
    # New dual-period params for frontend: period A and period B
    start_a: Optional[date] = Query(None, description="Period A start date (YYYY-MM-DD)"),
    end_a: Optional[date] = Query(None, description="Period A end date (YYYY-MM-DD)"),
    start_b: Optional[date] = Query(None, description="Period B start date (YYYY-MM-DD)"),
    end_b: Optional[date] = Query(None, description="Period B end date (YYYY-MM-DD)"),
):
    """
    Get booking rate improvement metrics within date range.

    - **company_id**: Company UUID (optional if user_id is provided). Either company_id or user_id is required.
    - **user_id**: User UUID (optional). If provided, metrics are calculated only for that user. If both company_id and user_id are provided, user_id is used.
    - **start_date**: Start of the current period (defaults to 30 days ago)
    - **end_date**: End of the current period (defaults to today)

    **Dual-period mode (for charts):**
    - **start_a, end_a**: Period A date range
    - **start_b, end_b**: Period B date range
    - Returns per-day booking rate percentage: (booked leads / qualified leads) × 100
    - series[].y = booking rate % (0-100), y_axis = percentage ticks
    - period summary includes average_booking_rate (avg of daily rates)

    **Legacy mode:** Compares booking rate between current period and previous period of same length.
    Returns current rate, previous rate, improvement percentage, and totals.

    Resolution Rules:
    - If user_id is provided: prefer user_id (even if company_id is also provided)
    - Else if company_id is provided: use company_id
    - Else: return 400 error "Either company_id or user_id is required"

    Required role: Any authenticated user
    """
    # Resolution rules:
    # - If user_id is provided: prefer user_id (even if company_id is also provided)
    # - Else if company_id is provided: use company_id
    # - Else: error
    if not company_id and not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )

    if user_id:
        company_id = None  # ensure user_id takes precedence (service will derive company_id from user)

    service = MetricsService(db)
    # If new dual-period params provided, pass them through; else use legacy start_date/end_date
    if start_a and start_b and end_a and end_b:
        return await service.get_booking_rate_improvement(
            company_id=company_id,
            user_id=user_id,
            start_a=start_a,
            end_a=end_a,
            start_b=start_b,
            end_b=end_b,
        )
    else:
        return await service.get_booking_rate_improvement(
            company_id=company_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )


@router.get("/close-rate-trends", response_model=CloseRateTrendsResponse, responses=RESPONSES)
async def get_close_rate_trends(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope close rate trends to a single user (optional)"),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    # Backwards-compatible single-period params:
    start_date: Optional[date] = Query(None, description="(legacy) Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="(legacy) End date for filtering (YYYY-MM-DD)"),
    # New dual-period params for frontend: period A and period B
    start_a: Optional[date] = Query(None, description="Period A start date (YYYY-MM-DD)"),
    end_a: Optional[date] = Query(None, description="Period A end date (YYYY-MM-DD)"),
    start_b: Optional[date] = Query(None, description="Period B start date (YYYY-MM-DD)"),
    end_b: Optional[date] = Query(None, description="Period B end date (YYYY-MM-DD)"),
):
    """
    Get close rate trends within date range.

    - **company_id**: Company UUID (optional if user_id is provided). Either company_id or user_id is required.
    - **user_id**: User UUID (optional). If provided, metrics are calculated only for that user.
    - **start_date**: Start of the current period (defaults to 30 days ago)
    - **end_date**: End of the current period (defaults to today)

    **Dual-period mode (for charts):**
    - **start_a, end_a**: Period A date range
    - **start_b, end_b**: Period B date range
    - Returns per-day close rate percentage: (won appointments / total appointments) × 100
    - series[].y = close rate % (0-100), y_axis = percentage ticks
    - period summary includes average_close_rate (avg of daily rates)

    **Legacy mode:** Compares close rate between current period and previous period of same length.
    Tracks appointments with outcome='won' and leads with status='closed_won'.
    Returns current rate, previous rate, improvement percentage, and totals.
    """
    # Validate that at least one of company_id or user_id is provided
    if not company_id and not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )

    if user_id:
        company_id = None  # ensure user_id takes precedence

    service = MetricsService(db)
    # If new dual-period params provided, pass them through; else use legacy start_date/end_date
    if start_a and start_b and end_a and end_b:
        return await service.get_close_rate_trends(
            company_id=company_id,
            user_id=user_id,
            start_a=start_a,
            end_a=end_a,
            start_b=start_b,
            end_b=end_b,
        )
    else:
        return await service.get_close_rate_trends(
            company_id=company_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )


@router.get("/bookings/summary", response_model=BookingsSummaryResponse, responses=RESPONSES)
async def get_bookings_summary(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get bookings summary metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total, confirmed, pending, cancelled bookings and bookings today.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_bookings_summary(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/objections/top", responses=RESPONSES)
async def get_top_objections(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope top objections to a single user (optional)"),
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: Optional[int] = Query(None, ge=1, le=20, description="Number of top objections to return (optional, returns all if not specified)"),
):
    """
    Get top objections aggregated by company or user.
    
    **When called by company_id:** Returns objections with objection_type, count, affected_leads_count;
    plus booking_rate, booked, unbooked, booking_rate_trend (start to end date);
    most_coaching_needs (user_id, user details, unbooked count for that objection, call_logs per user);
    and call_logs (all call details where that objection occurred for the company).
    
    **When called by user_id:** Returns objections with objection_type, count, affected_leads_count;
    plus call_logs (call details where that objection occurred for that user only).
    
    - **company_id**: Company UUID (optional if user_id is provided)
    - **user_id**: User UUID (optional). If provided, objections are scoped to that user. If both provided, user_id is used.
    - **start_date**, **end_date**: Filter objections by call date range.
    - **limit**: Optional limit on number of top objections returned.
    
    Required role: CSR, SALES_REP, or EXECUTIVE
    """
    if not company_id and not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )

    if user_id:
        company_id = None  # user_id takes precedence (service derives company_id from user)

    service = AnalyticsService(db)
    result = await service.get_top_objections(
        company_id=company_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    if limit is not None:
        result["objections"] = result["objections"][:limit]
    
    return result


@router.get("/objections/summary", response_model=ObjectionsSummaryResponse, responses=RESPONSES)
async def get_objections_summary(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get objections summary within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total objections, unique types, top objection, and breakdown by type.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_objections_summary(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/objections/{objection_type}/calls", responses=RESPONSES)
async def get_objection_calls(
    objection_type: str,
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    owner_id: Optional[UUID] = Query(None, description="CSR/owner UUID to filter by"),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD) - currently ignored"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD) - currently ignored"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of calls to return (optional)"),
):
    """
    Get calls filtered by objection type and optionally by CSR owner.
    
    Returns list of calls with:
    - call_id: UUID of the call
    - contact_card: Full contact card object
    - audio_url: URL to call audio recording
    - qualification_status: Qualification status from analysis
    - booking_status: Booking status from analysis
    
    - **objection_type**: Type of objection (e.g., price, timing, authority)
    - **company_id**: Company UUID (required)
    - **owner_id**: Optional - Filter by specific CSR/owner UUID
    - **start_date**: Currently ignored
    - **end_date**: Currently ignored
    - **limit**: Optional limit on number of calls returned
    
    Required role: CSR, SALES_REP, or EXECUTIVE
    """
    service = AnalyticsService(db)
    result = await service.get_objection_calls(
        company_id=company_id,
        objection=objection_type,
        owner_id=owner_id,
    )
    
    # Apply limit if provided
    if limit is not None:
        result = result[:limit]
    
    return result


@router.get("/coaching/opportunities", response_model=CoachingOpportunitiesResponse, responses=RESPONSES)
async def get_coaching_opportunities(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of opportunities to return"),
):
    """
    Get coaching opportunities based on low SOP compliance within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    - **limit**: Maximum number of opportunities (default: 10)
    
    Returns calls with SOP compliance < 70%.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_coaching_opportunities(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/coaching/most-opportunities", response_model=MostCoachingOpportunitiesResponse, responses=RESPONSES)
async def get_most_coaching_opportunities(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get most coaching opportunities - top 5 employees with least success rate.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns top 5 employees with least success rate, where:
    - Success rate = qualified_leads / booked_leads
    - Qualified leads: qualification_status in ['hot', 'cold', 'warm', 'qualified']
    - Booked leads: booking_status == 'booked'
    - For each employee, includes top 3 objections (most coaching need) with:
      - **objection**: Highest need / objection name
      - **pct_unbooked**: % Unbooked (unbooked/qualified * 100)
      - **unbooked_qualified_ratio**: # Unbooked / Qualified (e.g. "3/10")
      - **unbooked_count**, **qualified_count**: Raw counts
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_most_coaching_opportunities(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/conversion/lead-to-sale", response_model=ConversionMetricsResponse, responses=RESPONSES)
async def get_lead_to_sale_conversion(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get lead to sale conversion metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total leads, converted leads, conversion rate, avg days to conversion,
    and total revenue.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_lead_to_sale_conversion(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/conversions/pending-to-booked", response_model=ConversionsPendingToBookedResponse, responses=RESPONSES)
async def get_conversions_pending_to_booked(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get conversions from pending leads to booked within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns converted count, conversion rate, and average days to book.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_conversions_pending_to_booked(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/emergencies/dropped", response_model=EmergencyDroppedResponse, responses=RESPONSES)
async def get_emergencies_dropped(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get emergency/dropped calls metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns dropped calls, emergency calls (negative sentiment), and drop rate.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_emergencies_dropped(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/company/performance", response_model=CompanyPerformanceResponse, responses=RESPONSES)
async def get_company_performance(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get company performance metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns revenue, leads, conversion rate, avg deal size, active reps,
    and calls per rep.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_company_performance(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/calls/summary", response_model=CallsSummaryResponse, responses=RESPONSES)
async def get_calls_summary(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get calls summary metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total calls, answered, missed, avg duration, total duration,
    and calls today.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_calls_summary(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/leads/unbooked", response_model=UnbookedLeadsResponse, responses=RESPONSES)
async def get_unbooked_leads(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of leads to return"),
):
    """
    Get unbooked leads metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    - **limit**: Maximum number of leads (default: 20)
    
    Returns total unbooked, average days unbooked, and list of leads.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_unbooked_leads(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/actions/pending", response_model=PendingActionsResponse, responses=RESPONSES)
async def get_pending_actions(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get pending actions metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total pending, follow-ups needed, calls to make,
    and appointments to schedule.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_pending_actions(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.patch(
    "/actions/pending/{action_id}/complete",
    response_model=PendingAction,
    summary="Complete pending action",
    description="Mark a pending action as completed (e.g. CSR marking their assigned action done). Returns the updated PendingAction with status: completed.",
    responses={**RESPONSES, 404: {"description": "Pending action not found"}},
)
async def complete_pending_action(
    action_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Mark a pending action as completed (e.g. CSR marking their assigned action done).
    
    Required role: CSR, SALES_REP, EXECUTIVE
    """
    service = PendingActionService(db)
    updated = await service.mark_completed(action_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    return updated


@router.patch(
    "/actions/pending/{action_id}/reopen",
    response_model=PendingAction,
    summary="Reopen pending action",
    description="Reopen a pending action (set status back to pending). Use when a CSR or sales rep mistakenly marked an action as complete and needs to undo it. Returns the updated PendingAction with status: pending.",
    responses={**RESPONSES, 404: {"description": "Pending action not found"}},
)
async def reopen_pending_action(
    action_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Reopen a pending action (set status back to pending).
    Use when a CSR or sales rep mistakenly marked an action as complete and needs to undo it.
    
    Required role: CSR, SALES_REP, EXECUTIVE
    """
    service = PendingActionService(db)
    updated = await service.reopen(action_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    return updated


@router.get("/csr/me/profile", response_model=CSRProfileResponse, responses={**RESPONSES, 403: {"description": "Only available for CSR users"}})
async def get_my_csr_profile(
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(get_current_user),
    current_user: User = Depends(get_current_user),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get current CSR's own profile with all metrics, rank, and coaching insights.
    
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns:
    - User information (name, email, role, rank)
    - Key Performance Indicators (calls, leads, appointments, booking rate, response time)
    - Executive view metrics (booking rate, conversion rate, calls answered, response time)
    - Coaching insights (objection handling, script adherence, response time, lead qualification)
    
    Required role: CSR (returns own profile)
    """
    if current_user.role != UserRole.CSR.value:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for CSR users"
        )
    
    service = MetricsService(db)
    return await service.get_csr_profile(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/csr/{user_id}/profile", response_model=CSRProfileResponse, responses=RESPONSES)
async def get_csr_profile(
    user_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get comprehensive CSR profile with all metrics, rank, and coaching insights.
    
    - **user_id**: CSR user UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns:
    - User information (name, email, role, rank)
    - Key Performance Indicators (calls, leads, appointments, booking rate, response time)
    - Executive view metrics (booking rate, conversion rate, calls answered, response time)
    - Coaching insights (objection handling, script adherence, response time, lead qualification)
    
    Required role: CSR or EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_csr_profile(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

@router.get("/sales_rep/kpi", response_model=dict)
async def get_sales_rep_kpi(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope KPI to a single sales rep (optional)"),
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get sales rep KPIs for any sales rep (or company).

    - **company_id**: Company UUID (optional if user_id is provided)
    - **user_id**: User UUID (optional). If provided, KPIs are for that sales rep. If both provided, user_id is used.
    - **start_date**, **end_date**: Filter by appointment/lead date range.

    Returns: win_rate, first_touch_win_rate, follow_up_win_rate, attendance,
    average_deal_size, average_follow_up_per_deal.

    Required role: SALES_REP, CSR, or EXECUTIVE
    """
    if not company_id and not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either company_id or user_id is required",
        )
    if user_id:
        company_id = None
    service = MetricsService(db)
    return await service.get_sales_rep_kpi(
        company_id=company_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )