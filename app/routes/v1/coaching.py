"""
Coaching API routes.

Provides endpoints for the coaching dashboard:
- Single combined dashboard endpoint for all coaching data
- Coaching session CRUD
"""
import traceback
from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession, get_current_user
from app.core.permissions import require_executive
from app.domain.users.models import User
from app.domain.schemas.coaching import (
    CoachingDashboardResponse,
    CreateCoachingSessionRequest,
    CoachingSessionResponse,
    CoachingSessionListResponse,
)
from app.services.coaching_service import CoachingService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["coaching"])

RESPONSES = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Resource not found"},
    500: {"description": "Internal server error"},
    503: {"description": "Shunya service not available"},
}


# ============================================================================
# Combined Dashboard
# ============================================================================


@router.get(
    "/dashboard/{user_id}",
    response_model=CoachingDashboardResponse,
    responses=RESPONSES,
)
async def get_coaching_dashboard(
    user_id: UUID,
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_executive),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    weeks: int = Query(8, ge=1, le=52, description="Progression weeks"),
    days: int = Query(30, ge=7, le=365, description="Peer benchmark period in days"),
    role_filter: Optional[str] = Query(None, description="Filter team by role"),
    search: Optional[str] = Query(None, description="Search team by name or email"),
):
    """
    Get the full coaching dashboard for a rep.

    Returns all sections in parallel: team overview, issues, strengths,
    progression, peer benchmark, impact, objections, and smart nudges.
    Sections that fail individually return null instead of failing the
    entire request.
    """
    try:
        service = CoachingService(db)
        return await service.get_dashboard(
            user_id=user_id,
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            weeks=weeks,
            days=days,
            role_filter=role_filter,
            search=search,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coaching dashboard: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Coaching Sessions CRUD
# ============================================================================


@router.post("/sessions", response_model=CoachingSessionResponse, status_code=201, responses=RESPONSES)
async def create_coaching_session(
    request: CreateCoachingSessionRequest,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Create a new coaching session.

    Auto-computes baseline scores from the rep's recent call analyses.
    Sets a follow-up period (default 14 days) for impact measurement.
    """
    try:
        service = CoachingService(db)
        session = await service.create_coaching_session(
            company_id=request.company_id,
            rep_user_id=request.rep_user_id,
            coach_user_id=request.coach_user_id,
            focus_areas=request.focus_areas,
            targets=request.targets,
            follow_up_days=request.follow_up_days,
            notes=request.notes,
        )
        return CoachingSessionResponse(
            id=session.id,
            company_id=session.company_id,
            rep_user_id=session.rep_user_id,
            coach_user_id=session.coach_user_id,
            focus_areas=session.focus_areas or [],
            targets=session.targets,
            baseline_scores=session.baseline_scores,
            status=session.status,
            follow_up_days=session.follow_up_days,
            follow_up_end_date=session.follow_up_end_date,
            impact_scores=session.impact_scores,
            overall_improved=session.overall_improved,
            improvement_pct=session.improvement_pct,
            targets_met=session.targets_met,
            notes=session.notes,
            coached_at=session.coached_at,
            created_at=session.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating coaching session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=CoachingSessionListResponse, responses=RESPONSES)
async def list_coaching_sessions(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_executive),
    rep_user_id: Optional[UUID] = Query(None, description="Filter by rep user ID"),
    session_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List coaching sessions with filters.
    """
    try:
        service = CoachingService(db)
        return await service.list_coaching_sessions(
            company_id=company_id,
            rep_user_id=rep_user_id,
            status=session_status,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing coaching sessions: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
