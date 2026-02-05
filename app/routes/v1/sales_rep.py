"""
Sales rep API routes.

Provides follow-ups and tasks for an appointment (from call analysis).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession, get_current_user
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
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
