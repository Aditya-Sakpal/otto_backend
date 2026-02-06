"""
Sales rep API routes.

Provides follow-ups and tasks for an appointment (from call analysis),
and pending leads for a rep.
"""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.schemas.sales_rep import PendingLeadsResponse
from app.domain.users.models import User
from app.services.lead_service import LeadService
from app.services.sales_rep_service import SalesRepService

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
