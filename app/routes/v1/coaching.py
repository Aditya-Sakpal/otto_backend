"""
Coaching API routes.

Provides endpoints for the coaching dashboard:
- Single combined dashboard endpoint returning all 8 coaching sections in one call
- Coaching session CRUD (create and list)
- Smart nudge CRUD (list, read, dismiss, unread count)
- Coaching cycle management (stop, history)

All endpoints require EXECUTIVE role.
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
    TeamDashboardResponse,
    IndividualDashboardResponse,
    CreateCoachingSessionRequest,
    CoachingSessionResponse,
    CoachingSessionListResponse,
)
from app.domain.schemas.nudges import (
    SmartNudgeResponse,
    SmartNudgeListResponse,
    UnreadCountResponse,
    MarkReadResponse,
    MarkAllReadResponse,
    CoachingSessionCycleResponse,
    CoachingSessionHistoryResponse,
    StopCoachingRequest,
)
from app.services.coaching_service import CoachingService
from app.services.smart_nudge_service import SmartNudgeService
from app.services.coaching_cycle_service import CoachingCycleService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["coaching"])

RESPONSES = {
    400: {"description": "Bad request (e.g. missing company_id)"},
    403: {"description": "Forbidden – caller does not have EXECUTIVE role"},
    404: {"description": "Resource not found"},
    500: {"description": "Internal server error"},
    503: {"description": "Shunya analytics service unavailable – progression and peer_benchmark sections will be null"},
}


# ============================================================================
# Combined Dashboard
# ============================================================================


@router.get(
    "/dashboard/{user_id}",
    response_model=CoachingDashboardResponse,
    responses=RESPONSES,
    summary="Get full coaching dashboard for a rep",
    response_description="Combined coaching dashboard with all 8 sections. Sections that fail return null.",
)
async def get_coaching_dashboard(
    user_id: UUID,
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID. Required for all data scoping"),
    current_user: User = Depends(require_executive),
    start_date: Optional[date] = Query(None, description="Start date for filtering issues, strengths, objections, and nudges (YYYY-MM-DD). Defaults to 30 days ago"),
    end_date: Optional[date] = Query(None, description="End date for filtering issues, strengths, objections, and nudges (YYYY-MM-DD). Defaults to today"),
    weeks: int = Query(8, ge=1, le=52, description="Number of weeks for the progression chart (1-52). Only affects the 'progression' section"),
    days: int = Query(30, ge=7, le=365, description="Analysis period in days for peer benchmark comparison (7-365). Only affects the 'peer_benchmark' section"),
    role_filter: Optional[str] = Query(None, description="Filter team members by role (e.g. 'sales_rep', 'csr'). Only affects the 'team' section"),
    search: Optional[str] = Query(None, description="Search team members by name or email (partial match). Only affects the 'team' section"),
):
    """
    Get the full coaching dashboard for a specific rep in a single API call.

    Returns all 8 coaching sections fetched in parallel. Each section is independent –
    if one fails (e.g. Shunya API is down), that section returns `null` while the
    rest still return data.

    **Path Parameters:**
    - **user_id**: UUID of the rep to get coaching data for

    **Query Parameters:**
    - **company_id** (required): Company UUID for data scoping
    - **start_date**: Start date for date-filtered sections (defaults to 30 days ago)
    - **end_date**: End date for date-filtered sections (defaults to today)
    - **weeks**: Number of weeks for the progression chart (default 8, range 1-52)
    - **days**: Analysis period for peer benchmark (default 30, range 7-365)
    - **role_filter**: Filter team overview by role (e.g. 'sales_rep', 'csr')
    - **search**: Search team overview by name or email

    **Response Sections:**

    | Section | Source | Date-Filtered | Description |
    |---------|--------|:---:|-------------|
    | `team` | Local DB | Yes | Team overview: aggregate stats + per-member breakdown |
    | `issues` | Local DB | Yes | Coaching issues grouped by type, sorted by frequency |
    | `strengths` | Local DB | Yes | Coaching strengths grouped by behavior, sorted by frequency |
    | `progression` | Shunya API | No (uses `weeks`) | Weekly metric trends with anomaly detection |
    | `peer_benchmark` | Shunya API | No (uses `days`) | Rep vs team on 5 metrics (compliance, booking, objection handling, rapport, script adherence) |
    | `impact` | Local DB | No | All coaching sessions with baseline vs post-coaching scores |
    | `objections` | Local DB | Yes | Objection categories with rep overcome rate vs team average |
    | `nudges` | Computed | Yes | AI-generated coaching recommendations |

    **Notes:**
    - `progression` and `peer_benchmark` are proxied from the Shunya analytics API and may be null if Shunya is unavailable
    - `nudges` are computed from issues (frequency >= 2 → immediate), objections (overcome < 30% → pre_call), and compliance trend (declining → weekly)
    - Date filtering (start_date/end_date) applies to: team, issues, strengths, objections, nudges
    - The `weeks` param only affects progression; the `days` param only affects peer_benchmark

    Required role: EXECUTIVE
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
# Split Dashboard Endpoints
# ============================================================================


@router.get(
    "/team-dashboard",
    response_model=TeamDashboardResponse,
    responses=RESPONSES,
    summary="Get team coaching overview",
    response_description="High-level team overview with aggregate stats and per-member summaries.",
)
async def get_team_dashboard(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID. Required for all data scoping"),
    current_user: User = Depends(require_executive),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD). Defaults to 30 days ago"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD). Defaults to today"),
    role_filter: Optional[str] = Query(None, description="Filter team members by role (e.g. 'sales_rep', 'csr')"),
    search: Optional[str] = Query(None, description="Search team members by name or email (partial match)"),
):
    """
    Get a high-level team coaching overview.

    Use this endpoint when the user first lands on the coaching page to display
    team-level stats and a per-member breakdown. No specific rep user_id is needed.

    When a manager clicks on a team member, call the
    `/individual-dashboard/{user_id}` endpoint for their detailed coaching data.

    **Query Parameters:**
    - **company_id** (required): Company UUID for data scoping
    - **start_date**: Start date for filtering (defaults to 30 days ago)
    - **end_date**: End date for filtering (defaults to today)
    - **role_filter**: Filter by role (e.g. 'sales_rep', 'csr')
    - **search**: Search by name or email

    **Response:**
    - **team**: Aggregate `TeamStats` (avg compliance, avg booking rate, open issues, team size) and a list of `TeamMemberSummary` per member

    Required role: EXECUTIVE
    """
    try:
        service = CoachingService(db)
        return await service.get_team_dashboard(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            role_filter=role_filter,
            search=search,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team dashboard: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/individual-dashboard/{user_id}",
    response_model=IndividualDashboardResponse,
    responses=RESPONSES,
    summary="Get individual rep coaching dashboard",
    response_description="Detailed coaching data for a specific rep with all 7 sections. Sections that fail return null.",
)
async def get_individual_dashboard(
    user_id: UUID,
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID. Required for all data scoping"),
    current_user: User = Depends(require_executive),
    start_date: Optional[date] = Query(None, description="Start date for filtering issues, strengths, objections, and nudges (YYYY-MM-DD). Defaults to 30 days ago"),
    end_date: Optional[date] = Query(None, description="End date for filtering issues, strengths, objections, and nudges (YYYY-MM-DD). Defaults to today"),
    weeks: int = Query(8, ge=1, le=52, description="Number of weeks for the progression chart (1-52). Only affects the 'progression' section"),
    days: int = Query(30, ge=7, le=365, description="Analysis period in days for peer benchmark comparison (7-365). Only affects the 'peer_benchmark' section"),
):
    """
    Get detailed coaching data for a specific rep.

    Use this endpoint when a manager clicks on a team member from the team overview
    to see their full coaching details. Returns all 7 rep-specific sections fetched
    in parallel.

    **Path Parameters:**
    - **user_id**: UUID of the rep to get coaching data for

    **Query Parameters:**
    - **company_id** (required): Company UUID for data scoping
    - **start_date**: Start date for date-filtered sections (defaults to 30 days ago)
    - **end_date**: End date for date-filtered sections (defaults to today)
    - **weeks**: Number of weeks for the progression chart (default 8, range 1-52)
    - **days**: Analysis period for peer benchmark (default 30, range 7-365)

    **Response Sections:**

    | Section | Source | Date-Filtered | Description |
    |---------|--------|:---:|-------------|
    | `issues` | Local DB | Yes | Coaching issues grouped by type, sorted by frequency |
    | `strengths` | Local DB | Yes | Coaching strengths grouped by behavior, sorted by frequency |
    | `progression` | Shunya API | No (uses `weeks`) | Weekly metric trends with anomaly detection |
    | `peer_benchmark` | Shunya API | No (uses `days`) | Rep vs team on 5 metrics |
    | `impact` | Local DB | No | Coaching sessions with baseline vs post-coaching scores |
    | `objections` | Local DB | Yes | Objection categories with rep overcome rate vs team average |
    | `nudges` | Computed | Yes | AI-generated coaching recommendations |

    **Notes:**
    - `progression` and `peer_benchmark` are proxied from the Shunya analytics API and may be null if Shunya is unavailable
    - Each section is independent – if one fails, it returns null while the rest succeed

    Required role: EXECUTIVE
    """
    try:
        service = CoachingService(db)
        return await service.get_individual_dashboard(
            user_id=user_id,
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            weeks=weeks,
            days=days,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting individual dashboard: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Coaching Sessions CRUD
# ============================================================================


@router.post(
    "/sessions",
    response_model=CoachingSessionResponse,
    status_code=201,
    responses=RESPONSES,
    summary="Create a new coaching session",
    response_description="The created coaching session with auto-computed baseline scores",
)
async def create_coaching_session(
    request: CreateCoachingSessionRequest,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Create a new coaching session for a rep.

    When a session is created:
    1. **Baseline scores** are auto-computed by averaging the rep's last 5 completed call analyses
       (metrics: compliance_score, booking_rate, rapport_score)
    2. A **follow-up end date** is set to `now + follow_up_days` (default 14 days)
    3. Status is set to `in_progress`

    The impact can later be measured by comparing baseline_scores against
    call analyses that occur during the follow-up period.

    **Request Body Fields:**
    - **company_id**: Company UUID
    - **rep_user_id**: UUID of the rep being coached
    - **coach_user_id**: UUID of the manager/coach
    - **focus_areas**: List of metric names to focus on (e.g. `["compliance_score", "booking_rate"]`)
    - **targets**: Target scores to achieve as `{metric: score}` (0-1 scale, e.g. `{"compliance_score": 0.85}`)
    - **follow_up_days**: Days to measure impact (default 14)
    - **notes**: Optional free-text coaching notes

    Required role: EXECUTIVE
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


@router.get(
    "/sessions",
    response_model=CoachingSessionListResponse,
    responses=RESPONSES,
    summary="List coaching sessions",
    response_description="Paginated list of coaching sessions with total count",
)
async def list_coaching_sessions(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID. Required for data scoping"),
    current_user: User = Depends(require_executive),
    rep_user_id: Optional[UUID] = Query(None, description="Filter sessions by rep user UUID. Omit to get all sessions for the company"),
    session_status: Optional[str] = Query(None, alias="status", description="Filter by session status: 'in_progress' or 'completed'. Omit to get all statuses"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of sessions to return (1-200, default 50)"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip for pagination (default 0)"),
):
    """
    List coaching sessions with optional filters and pagination.

    **Query Parameters:**
    - **company_id** (required): Company UUID
    - **rep_user_id**: Filter by rep (omit for all reps)
    - **status**: Filter by status: 'in_progress' or 'completed' (omit for all)
    - **limit**: Page size (default 50, max 200)
    - **offset**: Skip N records for pagination (default 0)

    Sessions are sorted by coached_at descending (most recent first).

    Required role: EXECUTIVE
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


# ============================================================================
# Smart Nudges
# ============================================================================


@router.get(
    "/nudges",
    response_model=SmartNudgeListResponse,
    responses=RESPONSES,
    summary="List smart nudges",
    response_description="Paginated list of smart nudges with per-user read status and unread count.",
)
async def list_nudges(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_executive),
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="Filter by read status: 'unread', 'read', 'dismissed'. Omit for all.",
    ),
    priority: Optional[str] = Query(
        None,
        description="Filter by priority: 'critical', 'high', 'medium', 'low', 'positive'.",
    ),
    rep_user_id: Optional[UUID] = Query(None, description="Filter by rep UUID"),
    limit: int = Query(50, ge=1, le=200, description="Page size (default 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List smart nudges for the current user's company.

    The frontend should poll this endpoint periodically to show new notifications.
    Each nudge has a `read_status` field that is per-user: 'unread', 'read', or 'dismissed'.

    Required role: EXECUTIVE
    """
    try:
        service = SmartNudgeService(db)
        result = await service.list_nudges(
            company_id=company_id,
            current_user_id=current_user.id,
            status_filter=status_filter,
            priority_filter=priority,
            rep_user_id=rep_user_id,
            limit=limit,
            offset=offset,
        )
        return SmartNudgeListResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing nudges: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/nudges/unread-count",
    response_model=UnreadCountResponse,
    responses=RESPONSES,
    summary="Get unread nudge count",
    response_description="Lightweight unread count for notification badge.",
)
async def get_unread_nudge_count(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_executive),
):
    """
    Get the number of unread nudges for the current user.

    Use this lightweight endpoint for notification badge polling (every 30-60s).

    Required role: EXECUTIVE
    """
    try:
        service = SmartNudgeService(db)
        count = await service.get_unread_count(company_id, current_user.id)
        return UnreadCountResponse(unread_count=count)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting unread count: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/nudges/{nudge_id}/read",
    response_model=MarkReadResponse,
    responses=RESPONSES,
    summary="Mark nudge as read",
)
async def mark_nudge_read(
    nudge_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Mark a specific nudge as read for the current user.

    Required role: EXECUTIVE
    """
    try:
        service = SmartNudgeService(db)
        await service.mark_read(nudge_id, current_user.id)
        return MarkReadResponse(nudge_id=nudge_id, status="read")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking nudge read: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/nudges/{nudge_id}/dismiss",
    response_model=MarkReadResponse,
    responses=RESPONSES,
    summary="Dismiss a nudge",
)
async def dismiss_nudge(
    nudge_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Dismiss a specific nudge for the current user.

    Required role: EXECUTIVE
    """
    try:
        service = SmartNudgeService(db)
        await service.mark_dismissed(nudge_id, current_user.id)
        return MarkReadResponse(nudge_id=nudge_id, status="dismissed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing nudge: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/nudges/mark-all-read",
    response_model=MarkAllReadResponse,
    responses=RESPONSES,
    summary="Mark all nudges as read",
)
async def mark_all_nudges_read(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_executive),
):
    """
    Mark all unread nudges as read for the current user.

    Required role: EXECUTIVE
    """
    try:
        service = SmartNudgeService(db)
        count = await service.mark_all_read(company_id, current_user.id)
        return MarkAllReadResponse(marked_count=count)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking all nudges read: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Coaching Cycle Management
# ============================================================================


@router.patch(
    "/sessions/{session_id}/stop",
    response_model=CoachingSessionCycleResponse,
    responses=RESPONSES,
    summary="Stop auto-cycling for a coaching session",
)
async def stop_coaching_session(
    session_id: UUID,
    db: DbSession,
    request: StopCoachingRequest = None,
    current_user: User = Depends(require_executive),
):
    """
    Stop the 7-day auto-cycling for a coaching session.

    This sets the current active cycle to 'stopped' status, preventing the
    system from auto-creating the next cycle. The session's impact data is
    preserved.

    Pass the original session_id or any cycle's id — the system will find
    and stop the currently active cycle in the chain.

    Required role: EXECUTIVE
    """
    try:
        service = CoachingCycleService(db)
        notes = request.notes if request else None
        session = await service.stop_coaching(session_id, notes=notes)
        return CoachingSessionCycleResponse(
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
            cycle_number=session.cycle_number,
            parent_session_id=session.parent_session_id,
            auto_created=session.auto_created,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping coaching session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sessions/{session_id}/history",
    response_model=CoachingSessionHistoryResponse,
    responses=RESPONSES,
    summary="Get coaching session cycle history",
)
async def get_session_history(
    session_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Get all 7-day cycles for a coaching session chain.

    Pass any session_id in the chain (original or any cycle) and the system
    will return the full history of all cycles.

    Required role: EXECUTIVE
    """
    try:
        service = CoachingCycleService(db)
        history = await service.get_session_history(session_id)

        def _to_cycle_response(s):
            return CoachingSessionCycleResponse(
                id=s.id,
                company_id=s.company_id,
                rep_user_id=s.rep_user_id,
                coach_user_id=s.coach_user_id,
                focus_areas=s.focus_areas or [],
                targets=s.targets,
                baseline_scores=s.baseline_scores,
                status=s.status,
                follow_up_days=s.follow_up_days,
                follow_up_end_date=s.follow_up_end_date,
                impact_scores=s.impact_scores,
                overall_improved=s.overall_improved,
                improvement_pct=s.improvement_pct,
                targets_met=s.targets_met,
                notes=s.notes,
                coached_at=s.coached_at,
                created_at=s.created_at,
                cycle_number=s.cycle_number,
                parent_session_id=s.parent_session_id,
                auto_created=s.auto_created,
            )

        return CoachingSessionHistoryResponse(
            original_session_id=history["original_session_id"],
            rep_user_id=history["rep_user_id"],
            total_cycles=history["total_cycles"],
            active_cycle=(
                _to_cycle_response(history["active_cycle"])
                if history["active_cycle"]
                else None
            ),
            completed_cycles=[
                _to_cycle_response(c) for c in history["completed_cycles"]
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session history: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
