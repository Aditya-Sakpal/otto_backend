"""
Metrics API routes.

Provides analytics and metrics endpoints with date range filtering.
All endpoints require company_id and support start_date/end_date for filtering.
"""
from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_executive, require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/exec/company-overview")
async def get_company_overview(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get company overview metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total leads, active leads, calls, missed calls, appointments,
    conversion rate, and total revenue.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_company_overview(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/exec/csr/dashboard")
async def get_csr_dashboard(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get CSR dashboard metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    
    Returns total calls, missed calls, calls today, average call duration,
    leads assigned, and appointments scheduled.
    
    Required role: EXECUTIVE
    """
    service = MetricsService(db)
    return await service.get_csr_dashboard(
        company_id=company_id,
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
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get booking rate improvement metrics within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the current period (defaults to 30 days ago)
    - **end_date**: End of the current period (defaults to today)
    
    Compares booking rate between current period and previous period of same length.
    Returns current rate, previous rate, improvement percentage, and totals.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_booking_rate_improvement(
        company_id=company_id,
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
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: int = Query(5, ge=1, le=20, description="Number of top objections to return"),
):
    """
    Get top objections from call analyses within date range.
    
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    - **limit**: Number of top objections (default: 5)
    
    Returns list of objections with counts and percentages.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_top_objections(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


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
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of calls to return"),
):
    """
    Get calls with specific objection type within date range.
    
    - **objection_type**: Type of objection (price, timing, authority, need, competitor, other)
    - **company_id**: Company UUID
    - **start_date**: Start of the date range (defaults to 30 days ago)
    - **end_date**: End of the date range (defaults to today)
    - **limit**: Maximum number of calls (default: 20)
    
    Returns list of calls where this objection was raised.
    
    Required role: Any authenticated user
    """
    service = MetricsService(db)
    return await service.get_objection_calls(
        company_id=company_id,
        objection_type=objection_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


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
