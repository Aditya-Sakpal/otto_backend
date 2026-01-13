"""
Analytics API routes.

Provides analytics endpoints for objections and calls.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/top-objections")
async def get_top_objections(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get top objections aggregated by company.

    Returns:
    - objection_type: Type of objection (price, timing, authority, need, competitor, other)
    - count: Number of times this objection appeared
    - affected_leads_count: Number of unique leads affected by this objection

    Required role: CSR, SALES_REP, or EXECUTIVE
    """
    service = AnalyticsService(db)
    return await service.get_top_objections(company_id=company_id)


@router.get("/objection-calls")
async def get_objection_calls(
    db: DbSession,
    objection: str = Query(..., description="Objection type (e.g., price, timing, authority)"),
    owner_id: Optional[UUID] = Query(None, description="CSR/owner UUID to filter by"),
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional, inferred from user if not provided)"),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get calls filtered by objection type and optionally by CSR owner.

    Returns:
    - call_id: UUID of the call
    - contact_card: Full contact card object
    - audio_url: URL to call audio recording
    - qualification_status: Qualification status from analysis
    - booking_status: Booking status from analysis

    Query Parameters:
    - objection: Required - Objection type to filter by
    - owner_id: Optional - Filter by specific CSR/owner
    - company_id: Optional - Company UUID (defaults to user's company)

    Required role: CSR, SALES_REP, or EXECUTIVE
    """
    # Use company_id from query or fall back to current user's company
    if not company_id and current_user.company_id:
        company_id = current_user.company_id

    if not company_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="company_id is required. Either provide it as a query parameter or ensure user has a company_id."
        )

    service = AnalyticsService(db)
    return await service.get_objection_calls(
        company_id=company_id,
        objection=objection,
        owner_id=owner_id,
    )
