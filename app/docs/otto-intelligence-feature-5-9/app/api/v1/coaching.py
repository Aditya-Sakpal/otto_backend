"""
Coaching API Endpoints

REST API for closed-loop coaching impact measurement.

Based on manager decisions Q10-Q24:
- Create coaching sessions with manager-defined targets
- Auto-calculate baselines from recent calls
- Track follow-up period and measure impact
- Calculate coach effectiveness metrics
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Path
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from ...core.database import get_database
from ...services.coaching import get_coaching_service
from ...utils.uuid_validator import validate_uuid


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coaching", tags=["Coaching"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateCoachingSessionRequest(BaseModel):
    """Request to create a new coaching session"""
    company_id: str = Field(..., description="Company ID")
    rep_id: str = Field(..., description="Rep being coached")
    rep_name: str = Field(..., description="Rep name")
    coach_id: str = Field(..., description="Coach/manager ID")
    coach_name: str = Field(..., description="Coach name")
    focus_areas: List[str] = Field(..., description="Skills to improve")
    targets: dict = Field(default_factory=dict, description="Metric -> target score")
    triggering_call_ids: List[str] = Field(default_factory=list, description="Calls that led to coaching")
    follow_up_days: int = Field(14, description="Follow-up period in days")
    notes: Optional[str] = Field(None, description="Coach notes")


class CoachingSessionResponse(BaseModel):
    """Response for a coaching session"""
    session_id: str
    company_id: str
    rep_id: str
    rep_name: str
    coach_id: str
    coach_name: str
    coached_at: datetime
    focus_areas: List[str]
    targets: dict
    baseline: Optional[dict] = None
    follow_up_period_days: int
    follow_up_end_date: datetime
    status: str
    impact: Optional[dict] = None
    created_at: datetime


class CoachingImpactResponse(BaseModel):
    """Response for coaching impact"""
    session_id: str
    rep_id: str
    rep_name: str
    baseline_scores: dict
    current_scores: dict
    improvements: dict
    overall_improved: bool
    trend_direction: str
    targets_met: dict
    confidence: str
    calls_analyzed: int
    measured_at: datetime


class CoachEffectivenessResponse(BaseModel):
    """Response for coach effectiveness"""
    coach_id: str
    coach_name: str
    company_id: str
    period_start: datetime
    period_end: datetime
    total_sessions: int
    completed_sessions: int
    reps_coached: int
    reps_improved: int
    improvement_rate: float
    avg_improvement_percentage: float
    best_focus_area: Optional[str] = None
    skill_effectiveness: dict


class CoachingROIResponse(BaseModel):
    """Response for company-wide coaching ROI"""
    company_id: str
    period_start: datetime
    period_end: datetime
    total_sessions: int
    total_coaches: int
    total_reps_coached: int
    avg_improvement_rate: float
    overall_success_rate: float
    top_coaches: List[dict]
    most_effective_focus_areas: List[str]


class SessionsListResponse(BaseModel):
    """Response for sessions list"""
    company_id: str
    total: int
    limit: int
    offset: int
    sessions: List[dict]


class UpdateSessionStatusRequest(BaseModel):
    """Request to update coaching session status"""
    status: str = Field(..., description="New status: 'in_progress', 'completed', 'extended', 'insufficient_data'")
    measure_impact: bool = Field(True, description="Whether to measure impact before status change")
    extension_days: int = Field(7, ge=1, le=30, description="Days to extend follow-up period (only used when status='extended')")
    notes: Optional[str] = Field(None, description="Optional notes for the status change")


class UpdateSessionStatusResponse(BaseModel):
    """Response for session status update"""
    session_id: str
    previous_status: str
    new_status: str
    impact_measured: bool
    impact: Optional[dict] = None
    new_follow_up_end_date: Optional[datetime] = None  # Set when status='extended'
    extension_days: Optional[int] = None  # Days added when extended
    message: str


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/sessions", response_model=CoachingSessionResponse, status_code=201)
async def create_coaching_session(
    request: CreateCoachingSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Log a new coaching session.
    
    Creates a coaching session with:
    - Auto-calculated baseline from rep's recent calls
    - Manager-defined improvement targets
    - Follow-up period tracking (default 2 weeks)
    """
    # Validate company_id
    try:
        validate_uuid(request.company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        coaching_service = get_coaching_service(db)
        
        session = await coaching_service.create_session(
            company_id=request.company_id,
            rep_id=request.rep_id,
            rep_name=request.rep_name,
            coach_id=request.coach_id,
            coach_name=request.coach_name,
            focus_areas=request.focus_areas,
            targets=request.targets,
            triggering_call_ids=request.triggering_call_ids,
            follow_up_days=request.follow_up_days,
            notes=request.notes
        )
        
        return CoachingSessionResponse(
            session_id=session.session_id,
            company_id=session.company_id,
            rep_id=session.rep_id,
            rep_name=session.rep_name,
            coach_id=session.coach_id,
            coach_name=session.coach_name,
            coached_at=session.coached_at,
            focus_areas=session.focus_areas,
            targets=session.targets,
            baseline=session.baseline.model_dump() if session.baseline else None,
            follow_up_period_days=session.follow_up_period_days,
            follow_up_end_date=session.follow_up_end_date,
            status=session.status,
            impact=session.impact.model_dump() if session.impact else None,
            created_at=session.created_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create coaching session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=CoachingSessionResponse)
async def get_session(
    session_id: str = Path(..., description="Coaching session ID"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get coaching session details including impact."""
    try:
        coaching_service = get_coaching_service(db)
        session = await coaching_service.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        return CoachingSessionResponse(
            session_id=session["session_id"],
            company_id=session["company_id"],
            rep_id=session["rep_id"],
            rep_name=session["rep_name"],
            coach_id=session["coach_id"],
            coach_name=session["coach_name"],
            coached_at=session["coached_at"],
            focus_areas=session["focus_areas"],
            targets=session["targets"],
            baseline=session.get("baseline"),
            follow_up_period_days=session["follow_up_period_days"],
            follow_up_end_date=session["follow_up_end_date"],
            status=session["status"],
            impact=session.get("impact"),
            created_at=session["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=SessionsListResponse)
async def list_sessions(
    company_id: str = Query(..., description="Company ID"),
    rep_id: Optional[str] = Query(None, description="Filter by rep"),
    coach_id: Optional[str] = Query(None, description="Filter by coach"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """List coaching sessions with filters."""
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        coaching_service = get_coaching_service(db)
        
        result = await coaching_service.list_sessions(
            company_id=company_id,
            rep_id=rep_id,
            coach_id=coach_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return SessionsListResponse(
            company_id=company_id,
            total=result["total"],
            limit=result["limit"],
            offset=result["offset"],
            sessions=result["sessions"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/impact", response_model=CoachingImpactResponse)
async def get_impact_report(
    session_id: str = Path(..., description="Coaching session ID"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get detailed impact report for a coaching session."""
    try:
        coaching_service = get_coaching_service(db)
        
        # Get session
        session = await coaching_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Measure current impact
        impact = await coaching_service.measure_impact(session_id)
        
        baseline = session.get("baseline", {})
        baseline_scores = baseline.get("scores", {}) if baseline else {}
        
        return CoachingImpactResponse(
            session_id=session_id,
            rep_id=session["rep_id"],
            rep_name=session["rep_name"],
            baseline_scores=baseline_scores,
            current_scores=impact.scores,
            improvements=impact.improvements,
            overall_improved=impact.overall_improved,
            trend_direction=impact.trend_direction,
            targets_met=impact.targets_met,
            confidence=impact.confidence,
            calls_analyzed=impact.calls_analyzed,
            measured_at=impact.measured_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get impact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sessions/{session_id}/status", response_model=UpdateSessionStatusResponse)
async def update_session_status(
    request: UpdateSessionStatusRequest,
    session_id: str = Path(..., description="Coaching session ID"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Update coaching session status.
    
    Use this endpoint to:
    - Manually complete a session (status='completed')
    - Extend the follow-up period (status='extended')
    - Mark as insufficient data (status='insufficient_data')
    - Reset to in_progress for re-evaluation
    
    When measure_impact=true (default), impact is measured before status change.
    """
    valid_statuses = ["in_progress", "completed", "extended", "insufficient_data"]
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )
    
    try:
        coaching_service = get_coaching_service(db)
        
        # Get current session
        session = await coaching_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        previous_status = session.get("status")
        impact_data = None
        
        # Measure impact if requested and completing the session
        if request.measure_impact and request.status in ["completed", "insufficient_data"]:
            impact = await coaching_service.measure_impact(session_id)
            impact_data = impact.model_dump()
        
        # Build update document
        update_doc = {
            "status": request.status,
            "updated_at": datetime.utcnow()
        }
        
        if impact_data:
            update_doc["impact"] = impact_data
        
        if request.notes:
            update_doc["status_notes"] = request.notes
        
        # Handle extension - add custom days to follow_up_end_date
        if request.status == "extended":
            from datetime import timedelta
            current_end = session.get("follow_up_end_date", datetime.utcnow())
            update_doc["follow_up_end_date"] = current_end + timedelta(days=request.extension_days)
            update_doc["extended_count"] = session.get("extended_count", 0) + 1
            update_doc["last_extension_days"] = request.extension_days
        
        # Update session
        await db.coaching_sessions.update_one(
            {"session_id": session_id},
            {"$set": update_doc}
        )
        
        # Refresh coach_effectiveness cache when session is completed or insufficient_data
        # so GET /coaches/{id}/effectiveness?use_cached=true reflects the new completion
        if request.status in ["completed", "insufficient_data"]:
            await coaching_service.refresh_coach_effectiveness_cache(
                coach_id=session.get("coach_id"),
                company_id=session.get("company_id")
            )
        
        logger.info(f"Updated session {session_id} status: {previous_status} -> {request.status}")
        
        # Build response
        response_data = {
            "session_id": session_id,
            "previous_status": previous_status,
            "new_status": request.status,
            "impact_measured": impact_data is not None,
            "impact": impact_data,
            "message": f"Session status updated from '{previous_status}' to '{request.status}'"
        }
        
        # Add extension info if extended
        if request.status == "extended":
            response_data["new_follow_up_end_date"] = update_doc.get("follow_up_end_date")
            response_data["extension_days"] = request.extension_days
            response_data["message"] = f"Session extended by {request.extension_days} days. New end date: {update_doc.get('follow_up_end_date')}"
        
        return UpdateSessionStatusResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coaches/{coach_id}/effectiveness", response_model=CoachEffectivenessResponse)
async def get_coach_effectiveness(
    coach_id: str = Path(..., description="Coach ID"),
    company_id: str = Query(..., description="Company ID"),
    timeframe_days: int = Query(90, ge=7, le=365, description="Analysis timeframe"),
    use_cached: bool = Query(False, description="If true, return from coach_effectiveness cache when available (within 8 days)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get coach effectiveness metrics (per Q23). Cache is updated by the weekly job and when sessions are completed."""
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        coaching_service = get_coaching_service(db)
        
        effectiveness = await coaching_service.get_coach_effectiveness(
            coach_id=coach_id,
            company_id=company_id,
            timeframe_days=timeframe_days,
            use_cached=use_cached
        )
        
        return CoachEffectivenessResponse(
            coach_id=effectiveness.coach_id,
            coach_name=effectiveness.coach_name,
            company_id=effectiveness.company_id,
            period_start=effectiveness.period_start,
            period_end=effectiveness.period_end,
            total_sessions=effectiveness.total_sessions,
            completed_sessions=effectiveness.completed_sessions,
            reps_coached=effectiveness.reps_coached,
            reps_improved=effectiveness.reps_improved,
            improvement_rate=effectiveness.improvement_rate,
            avg_improvement_percentage=effectiveness.avg_improvement_percentage,
            best_focus_area=effectiveness.best_focus_area,
            skill_effectiveness=effectiveness.skill_effectiveness
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get coach effectiveness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roi", response_model=CoachingROIResponse)
async def get_coaching_roi(
    company_id: str = Query(..., description="Company ID"),
    timeframe_days: int = Query(90, ge=7, le=365, description="Analysis timeframe"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get company-wide coaching ROI metrics (per Q24)."""
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        from datetime import timedelta
        
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=timeframe_days)
        
        # Get all coaches in period
        cursor = db.coaching_sessions.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "coached_at": {"$gte": period_start, "$lte": period_end}
                }
            },
            {
                "$group": {
                    "_id": "$coach_id",
                    "coach_name": {"$first": "$coach_name"},
                    "sessions": {"$sum": 1},
                    "improved_count": {
                        "$sum": {"$cond": [{"$eq": ["$impact.overall_improved", True]}, 1, 0]}
                    }
                }
            }
        ])
        
        coaches_data = await cursor.to_list(length=100)
        
        # Calculate overall metrics
        total_sessions = sum(c["sessions"] for c in coaches_data)
        total_coaches = len(coaches_data)
        total_improved = sum(c["improved_count"] for c in coaches_data)
        
        # Get unique reps
        reps_cursor = db.coaching_sessions.distinct("rep_id", {
            "company_id": company_id,
            "coached_at": {"$gte": period_start}
        })
        total_reps = len(await db.coaching_sessions.distinct("rep_id", {
            "company_id": company_id,
            "coached_at": {"$gte": period_start}
        }))
        
        # Calculate rates
        avg_improvement_rate = total_improved / total_sessions if total_sessions > 0 else 0
        
        # Top coaches by improvement rate
        top_coaches = sorted(
            [
                {
                    "coach_id": c["_id"],
                    "coach_name": c["coach_name"],
                    "sessions": c["sessions"],
                    "improvement_rate": c["improved_count"] / c["sessions"] if c["sessions"] > 0 else 0
                }
                for c in coaches_data
            ],
            key=lambda x: x["improvement_rate"],
            reverse=True
        )[:5]
        
        # Get most effective focus areas
        focus_cursor = db.coaching_sessions.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "coached_at": {"$gte": period_start},
                    "status": "completed"
                }
            },
            {"$unwind": "$focus_areas"},
            {
                "$group": {
                    "_id": "$focus_areas",
                    "count": {"$sum": 1},
                    "improved": {
                        "$sum": {"$cond": [{"$eq": ["$impact.overall_improved", True]}, 1, 0]}
                    }
                }
            },
            {"$sort": {"improved": -1}},
            {"$limit": 5}
        ])
        
        focus_areas_data = await focus_cursor.to_list(length=5)
        most_effective = [f["_id"] for f in focus_areas_data]
        
        return CoachingROIResponse(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            total_sessions=total_sessions,
            total_coaches=total_coaches,
            total_reps_coached=total_reps,
            avg_improvement_rate=avg_improvement_rate,
            overall_success_rate=avg_improvement_rate,  # Same metric for now
            top_coaches=top_coaches,
            most_effective_focus_areas=most_effective
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get coaching ROI: {e}")
        raise HTTPException(status_code=500, detail=str(e))
