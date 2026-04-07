"""
Sales rep API routes.

Provides follow-ups and tasks for an appointment (from call analysis),
pending leads for a rep, and dashboard endpoints.
"""
from datetime import date
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.schemas.sales_rep import PendingLeadsResponse
from app.domain.users.repository import UserRepository
from app.domain.schemas.sales_rep_dashboard import (
    RidealongEntry,
    SalesTeamStatsEntry,
    SalesRepDashboardResponse,
)
from app.domain.schemas.sales_rep_stat import SalesRepStatResponse
from app.domain.schemas.appointment_details import AppointmentDetailsResponse
from app.domain.users.models import User
from app.services.appointment_service import AppointmentService
from app.services.lead_service import LeadService
from app.services.sales_rep_service import SalesRepService
from app.services.sales_rep_dashboard_service import SalesRepDashboardService
from app.services.sales_rep_stat_service import SalesRepStatService

router = APIRouter(tags=["sales_rep"])


@router.get("/follow_up")
async def get_follow_up(
    db: DbSession,
    appointment_id: UUID = Query(..., description="Appointment UUID"),
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """
    Get follow-ups needed for an appointment from the call analysis.

    Returns follow_up_required, follow_up_reason, and follow_ups (next_steps from analysis).
    Requires the appointment to have an interaction (call) with analysis.
    """
    service = SalesRepService(db)
    result = await service.get_follow_up_for_appointment(appointment_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or has no call analysis",
        )
    return result


@router.get("/pending-leads", response_model=PendingLeadsResponse)
async def get_pending_leads(
    db: DbSession,
    rep_id: UUID = Query(..., description="Filter leads assigned to this rep (e.g. Chris Anderson)"),
    status: Optional[str] = Query(
        None,
        description='Filter by "pending", "closed", or "lost"',
    ),
    urgency: bool = Query(False, description="If true, return only High Urgency leads"),
    sort_by: Optional[str] = Query(
        "last_touched",
        description="Sort by last_touched or appointment_date",
    ),
    limit: int = Query(10, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> PendingLeadsResponse:
    """
    Get pending (or filtered) leads for a sales rep.

    Returns leads with customer info, sales context, appointment, and workflow.
    Requires rep_id; company scope is taken from the current user's company.
    """
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no company",
        )
    # Ensure rep_id refers to a user with role sales_rep
    user_repo = UserRepository(db)
    rep_user = await user_repo.get_by_id(rep_id)
    if rep_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="rep_id: user not found",
        )
    if rep_user.role != UserRole.SALES_REP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rep_id must be a user with role sales_rep",
        )
    service = LeadService(db)
    return await service.get_pending_leads(
        company_id=current_user.company_id,
        rep_id=rep_id,
        status_filter=status,
        urgency_only=urgency,
        sort_by=sort_by or "last_touched",
        limit=limit,
        offset=offset,
    )


@router.get(
    "/exec/stat/{sales_rep_id}",
    response_model=SalesRepStatResponse,
    summary="Get sales rep stat",
)
async def get_sales_rep_stat(
    sales_rep_id: UUID,
    db: DbSession,
    start_date: Optional[date] = Query(
        None,
        description="Inclusive start date for stats (YYYY-MM-DD). Defaults to 30 days before end_date or now.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Inclusive end date for stats (YYYY-MM-DD). Defaults to today (UTC).",
    ),
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> SalesRepStatResponse:
    """
    Get sales rep stat: personal stats (recordings, win rates, attendance, etc.)
    and pending leads. All metrics scoped to start_date/end_date (default last 30 days).
    """
    try:
        service = SalesRepStatService(db)
        return await service.get_sales_rep_stat(
            sales_rep_id=sales_rep_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

@router.get(
    "/exec/appointments/{appointment_id}",
    response_model=AppointmentDetailsResponse,
    summary="Get appointment details (exec view)",
)
async def get_appointment_details(
    appointment_id: UUID,
    db: DbSession,
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> AppointmentDetailsResponse:
    """
    Get appointment details for exec: customer name, sales rep name, status,
    and appointment overview (deal_size, deal_type, appointment_summary,
    sop_stages_completed, sop_stages_missed, appointment_booking if available).
    """
    service = AppointmentService(db)
    result = await service.get_appointment_details(appointment_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return result

@router.get(
    "/exec/dashboard/ridealongs_list",
    response_model=list[RidealongEntry],
    summary="Get ridealongs list with filters",
)
async def get_ridealongs_list(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    start_date: Optional[str] = Query(
        None,
        description="Filter appointments on or after this date (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="Filter appointments on or before this date (YYYY-MM-DD)",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by outcome: pending, won, lost, no_show, rescheduled, or 'In Progress'",
    ),
    outcome: Optional[str] = Query(
        None,
        description="Same filter as status; use when the client sends outcome= (e.g. won) instead of status=",
    ),
    ghost_mode: Optional[bool] = Query(
        None,
        description="Filter by assigned rep's ghost mode (true/false)",
    ),
    sales_rep_name: Optional[str] = Query(
        None,
        description="Filter by sales rep name (partial match)",
    ),
    search: Optional[str] = Query(
        None,
        description="Search contact name/phone, rep name, or location (tokens ANDed)",
    ),
    q: Optional[str] = Query(None, description="Alias for search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> list[RidealongEntry]:
    """
    Get ridealongs (appointments) with optional filters.
    """
    start_d = None
    end_d = None
    if start_date:
        try:
            start_d = date.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")
    if end_date:
        try:
            end_d = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date must be YYYY-MM-DD")

    service = SalesRepDashboardService(db)
    status_effective = (outcome.strip() if outcome and outcome.strip() else None) or status
    search_effective = (search or q or "").strip() or None
    return await service.get_ridealongs_list(
        company_id=company_id,
        start_date=start_d,
        end_date=end_d,
        status=status_effective,
        ghost_mode=ghost_mode,
        sales_rep_name=sales_rep_name,
        search=search_effective,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/exec/dashboard/sales_team_stats",
    response_model=list[SalesTeamStatsEntry],
    summary="Get sales team stats",
)
async def get_sales_team_stats(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(
        None,
        description="Max results. Omit for all (up to 500)",
    ),
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> list[SalesTeamStatsEntry]:
    """
    Get sales team stats: rep_name, total_recordings, win_rate,
    process_score, skills_score, otto_usage_hours. Supports pagination.
    """
    service = SalesRepDashboardService(db)
    return await service.get_sales_team_stats(
        company_id=company_id,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/exec/dashboard",
    response_model=SalesRepDashboardResponse,
    summary="Get sales rep dashboard",
)
async def get_dashboard(
    db: DbSession,
    company_id: UUID = Query(
        ...,
        description="Company UUID",
        example="6d40b509-82bc-4d21-9614-de91cc25dc1b",
    ),
    start_date: Optional[str] = Query(
        None,
        description="Start date for filtering objections (YYYY-MM-DD)",
        example="2026-02-14",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date for filtering objections (YYYY-MM-DD)",
        example="2026-02-20",
    ),
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])
    ),
) -> SalesRepDashboardResponse:
    """
    Get main dashboard: ridealongs_list (latest 9 appointments of the day),
    sales_team_stats (top 3 reps), and objections (same format as /metrics/objections/top).
    """
    from datetime import date as date_type
    
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = date_type.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be in YYYY-MM-DD format",
            )
    if end_date:
        try:
            end_dt = date_type.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be in YYYY-MM-DD format",
            )
    
    service = SalesRepDashboardService(db)
    return await service.get_dashboard(company_id=company_id, start_date=start_dt, end_date=end_dt)


@router.get("/tasks")
async def get_tasks(
    db: DbSession,
    appointment_id: UUID = Query(..., description="Appointment UUID"),
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """
    Get tasks needed further for an appointment from the call analysis.

    Returns action_items, next_steps, and pending_actions from analysis.
    """
    service = SalesRepService(db)
    result = await service.get_tasks_for_appointment(appointment_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or has no call analysis",
        )
    return result
