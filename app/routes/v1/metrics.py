"""
Metrics API routes.

Provides analytics and metrics endpoints with date range filtering.
Most endpoints require either company_id or user_id (with user_id taking precedence if both are provided).
All endpoints support start_date/end_date for filtering.
"""
from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, get_current_user
from app.core.permissions import require_executive, require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.services.metrics_service import MetricsService
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["metrics"])


@router.get("/exec/company-overview")
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


@router.get("/exec/csr/dashboard")
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


@router.get("/exec/missed-calls")
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


@router.get("/csr/auto-queued-leads")
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


@router.get("/booking-rate-improvement")
async def get_booking_rate_improvement(
    db: DbSession,
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope booking rate improvement to a single user (optional)"),
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get booking rate improvement metrics within date range.
    
    - **company_id**: Company UUID (optional if user_id is provided). Either company_id or user_id is required.
    - **user_id**: User UUID (optional). If provided, metrics are calculated only for that user. If both company_id and user_id are provided, user_id is used.
    - **start_date**: Start of the current period (defaults to 30 days ago)
    - **end_date**: End of the current period (defaults to today)
    
    Compares booking rate between current period and previous period of same length.
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
    return await service.get_booking_rate_improvement(
        company_id=company_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/bookings/summary")
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


@router.get("/objections/top")
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


@router.get("/objections/summary")
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


@router.get("/objections/{objection_type}/calls")
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


@router.get("/coaching/opportunities")
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


@router.get("/coaching/most-opportunities")
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


@router.get("/conversion/lead-to-sale")
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


@router.get("/conversions/pending-to-booked")
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


@router.get("/emergencies/dropped")
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


@router.get("/company/performance")
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


@router.get("/calls/summary")
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


@router.get("/leads/unbooked")
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


@router.get("/actions/pending")
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


@router.get("/csr/me/profile", response_model=dict)
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


@router.get("/csr/{user_id}/profile", response_model=dict)
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