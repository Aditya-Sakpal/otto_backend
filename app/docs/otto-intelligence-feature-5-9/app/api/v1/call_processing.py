"""
Call Processing API Endpoints

REST API for call processing pipeline.
"""

import uuid
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...schemas.call import (
    ProcessCallRequest,
    ProcessCallResponse,
    JobStatusResponse,
    CallSummaryResponse,
    ChunksResponse,
    ChunkInfo,
    RetryJobResponse,
    ProgressInfo,
    ProcessingResults,
    ProcessingMetadata,
    ErrorInfo
)
from ...models.enums import ProcessingStatus
from ...core.database import get_database
from ...core.redis_client import get_redis_client
from ...core.background_tasks import get_task_manager

# Import background task functions
from ...tasks.call_tasks import process_call_background


router = APIRouter(prefix="/api/v1/call-processing", tags=["Call Processing"])


@router.post("/process", response_model=ProcessCallResponse, status_code=202)
async def process_call(
    request: ProcessCallRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Submit a call for processing.
    
    Returns immediately with a job ID for status tracking.
    Background processing happens asynchronously.
    
    Duplicate Processing Prevention:
    - By default, if a call_id is already being processed or exists, returns 409 Conflict
    - Set allow_reprocess=true in the request to force reprocessing
    """
    # Generate job ID as pure UUID
    job_id = str(uuid.uuid4())
    
    # Check if call already exists or is processing
    existing = await db.calls.find_one({"call_id": request.call_id})
    if existing:
        # If allow_reprocess flag is not set, reject duplicate
        if not request.allow_reprocess:
            status = existing.get("status", "unknown")
            if status == "processing":
                raise HTTPException(
                    status_code=409,
                    detail=f"Call {request.call_id} is already being processed. Set allow_reprocess=true to force reprocessing."
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Call {request.call_id} already exists with status '{status}'. Set allow_reprocess=true to force reprocessing."
                )
        # If allow_reprocess is true, log warning and continue
        else:
            import logging
            logging.warning(f"Reprocessing call {request.call_id} with allow_reprocess flag")
    
    # Store initial status in Redis
    try:
        redis = await get_redis_client()
        status_data = {
            "job_id": job_id,
            "call_id": request.call_id,
            "status": ProcessingStatus.QUEUED.value,
            "progress": {
                "percent": 0,
                "current_step": "queued",
                "steps_completed": [],
                "steps_remaining": [
                    "downloading", "transcribing", "chunking",
                    "summarizing", "validation", "storage"
                ]
            },
            "created_at": datetime.utcnow().isoformat()
        }
        
        await redis.setex(
            f"job:{job_id}:status",
            86400,  # 24 hours
            json.dumps(status_data)
        )
        
        # Add background task (non-blocking)
        background_tasks.add_task(
            process_call_background,
            job_id,
            request.model_dump()
        )
        
        return ProcessCallResponse(
            job_id=job_id,
            call_id=request.call_id,
            status=ProcessingStatus.QUEUED,
            message="Call processing initiated successfully",
            estimated_completion_time=None,
            status_url=f"/api/v1/call-processing/status/{job_id}",
            created_at=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate call processing: {str(e)}"
        )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get the processing status of a job.
    """
    # Validate job_id is UUID
    from ...utils.uuid_validator import validate_uuid
    try:
        validate_uuid(job_id, "job_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        redis = await get_redis_client()
        cache_key = f"job:{job_id}:status"
        
        cached_data = await redis.get(cache_key)
        if not cached_data:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        status_data = json.loads(cached_data)
        
        # Build response
        status = ProcessingStatus(status_data["status"])
        progress_data = status_data.get("progress", {})
        progress = ProgressInfo(
            percent=progress_data.get("percent", 0),
            current_step=progress_data.get("current_step", ""),
            steps_completed=progress_data.get("steps_completed", []),
            steps_remaining=progress_data.get("steps_remaining", []),
            steps_failed=progress_data.get("steps_failed", [])
        )
        
        # Helper to parse ISO dates safely
        def parse_iso_date(date_str):
            if not date_str:
                return None
            try:
                # Handle both formats: with and without microseconds
                if '.' in date_str:
                    return datetime.fromisoformat(date_str)
                else:
                    return datetime.fromisoformat(date_str)
            except:
                return None
        
        response = JobStatusResponse(
            job_id=job_id,
            call_id=status_data.get("call_id", ""),
            status=status,
            progress=progress,
            started_at=parse_iso_date(status_data.get("started_at")),
            updated_at=parse_iso_date(status_data.get("updated_at")),
            completed_at=parse_iso_date(status_data.get("completed_at")),
            failed_at=parse_iso_date(status_data.get("failed_at"))
        )
        
        # Add results if completed
        if status == ProcessingStatus.COMPLETED:
            call_id = status_data.get("call_id")
            response.results = ProcessingResults(
                summary_url=f"/api/v1/call-processing/summary/{call_id}",
                chunks_url=f"/api/v1/call-processing/chunks/{call_id}",
                transcript_url=f"/api/v1/call-processing/transcript/{call_id}"
            )
        
        # Add error if failed
        if status == ProcessingStatus.FAILED and "error" in status_data:
            error_data = status_data["error"]
            response.error = ErrorInfo(
                code=error_data.get("code", error_data.get("type", "UNKNOWN_ERROR")),
                message=error_data.get("message", "An unknown error occurred"),
                details=error_data.get("details", {})
            )
            response.retry_available = True
            response.retry_url = f"/api/v1/call-processing/retry/{job_id}"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/summary/{call_id}", response_model=CallSummaryResponse)
async def get_call_summary(
    call_id: str,
    include_chunks: bool = False,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get the summary for a processed call.
    """
    try:
        # Get summary from MongoDB
        summary_doc = await db.call_summaries.find_one({"call_id": call_id})
        if not summary_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Summary for call {call_id} not found"
            )
        
        # Get call info for status and processed_at
        call_doc = await db.calls.find_one({"call_id": call_id})
        
        # Remove MongoDB _id
        summary_doc.pop("_id", None)
        
        # Add required fields for response model
        summary_doc["status"] = call_doc.get("status", "completed") if call_doc else "completed"
        summary_doc["processed_at"] = call_doc.get("processed_at", summary_doc.get("created_at", datetime.utcnow())) if call_doc else summary_doc.get("created_at", datetime.utcnow())
        
        return CallSummaryResponse(**summary_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get call summary: {str(e)}"
        )


@router.get("/chunks/{call_id}", response_model=ChunksResponse)
async def get_call_chunks(
    call_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get chunk summaries for a call.
    """
    try:
        # Get chunks from MongoDB
        cursor = db.chunk_summaries.find({"call_id": call_id}).sort("chunk_index", 1)
        chunks = await cursor.to_list(length=None)
        
        if not chunks:
            raise HTTPException(
                status_code=404,
                detail=f"Chunks for call {call_id} not found"
            )
        
        # Format response
        chunk_infos = []
        for chunk in chunks:
            chunk_infos.append(ChunkInfo(
                chunk_id=chunk["chunk_id"],
                chunk_index=chunk["chunk_index"],
                summary=chunk.get("summary", {}),
                milvus_id=chunk.get("milvus_id"),
                created_at=chunk.get("created_at", datetime.utcnow())
            ))
        
        return ChunksResponse(
            call_id=call_id,
            total_chunks=len(chunk_infos),
            chunks=chunk_infos
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get call chunks: {str(e)}"
        )


@router.post("/retry/{job_id}", response_model=RetryJobResponse, status_code=202)
async def retry_failed_job(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retry a failed processing job.
    """
    # Validate job_id is UUID
    from ...utils.uuid_validator import validate_uuid
    try:
        validate_uuid(job_id, "job_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        redis = await get_redis_client()
        cache_key = f"job:{job_id}:status"
        
        # Get original job data
        cached_data = await redis.get(cache_key)
        if not cached_data:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        status_data = json.loads(cached_data)
        
        # Check if job failed
        if status_data["status"] != ProcessingStatus.FAILED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Job {job_id} cannot be retried (status: {status_data['status']})"
            )
        
        # Create new job
        new_job_id = str(uuid.uuid4())
        call_id = status_data.get("call_id")
        
        # Get original request data (you'd need to store this)
        # For now, we'll return an error
        raise HTTPException(
            status_code=501,
            detail="Retry not yet implemented - original request data not stored"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retry job: {str(e)}"
        )


# ============================================================================
# PHASE DETECTION ENDPOINTS (per Q49-Q60)
# ============================================================================

from ...services.call_processing.phase_detection_service import get_phase_detection_service
from ...models.phase import CallPhases, PhaseAnalytics
from ...schemas.phase import (
    PhaseResponse,
    CallPhasesResponse,
    PhaseSearchResponse,
    CompanyPhaseAnalyticsResponse
)
from ...utils.uuid_validator import validate_uuid


@router.get("/calls/{call_id}/phases", response_model=CallPhasesResponse)
async def get_call_phases(
    call_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get conversation phases for a call.
    
    Returns detected phases with timestamps and quality assessments.
    """
    try:
        validate_uuid(call_id, "call_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        # Check if phases already exist
        existing = await db.call_phases.find_one({"call_id": call_id})
        
        if existing:
            existing.pop("_id", None)
            return CallPhasesResponse(**existing)
        
        # Get call transcript and detect phases
        call = await db.calls.find_one({"call_id": call_id})
        if not call:
            raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
        
        # Get transcript - handle both string and nested dict format
        transcript = call.get("transcript", "")
        if isinstance(transcript, dict):
            transcript = transcript.get("full_text", "")
        if not transcript:
            raise HTTPException(status_code=400, detail="Call has no transcript")
        
        # Detect phases
        phase_service = get_phase_detection_service()
        
        # Get duration and convert to milliseconds if needed
        call_duration_ms = None
        if call.get("duration"):
            # Duration is in seconds, convert to ms
            call_duration_ms = int(call.get("duration") * 1000)
        elif call.get("duration_ms"):
            # Already in ms
            call_duration_ms = call.get("duration_ms")
        elif call.get("metadata", {}).get("duration_ms"):
            # Check metadata
            call_duration_ms = call.get("metadata", {}).get("duration_ms")
        
        phases = await phase_service.detect_phases(
            transcript=transcript,
            call_id=call_id,
            company_id=call["company_id"],
            call_duration_ms=call_duration_ms,
            llm_segments=call.get("segments"),
            api_segments=call.get("segments_with_timestamps")
        )
        
        # Store results
        # Use model_dump() without mode='json' to keep datetime as datetime objects
        # This allows MongoDB date queries to work properly
        phases_dict = phases.model_dump()
        await db.call_phases.insert_one(phases_dict)
        
        return CallPhasesResponse(
            call_id=phases.call_id,
            company_id=phases.company_id,
            phases={k: v.model_dump() for k, v in phases.phases.items()},
            analytics=phases.analytics.model_dump(),
            overall_flow_score=phases.overall_flow_score,
            has_missing_phases=phases.has_missing_phases,
            missing_phases=phases.missing_phases,
            processed_at=phases.processed_at,
            algorithm_version=phases.algorithm_version
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get phases: {str(e)}")


@router.get("/phases/search")
async def search_by_phase(
    company_id: str,
    phase: Optional[str] = None,
    missing_phase: Optional[str] = None,
    detected: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Search calls by phase presence/absence.
    
    Find calls that have or are missing specific phases.
    """
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        query = {"company_id": company_id}
        
        if phase and detected is not None:
            query[f"phases.{phase}.detected"] = detected
        elif phase:
            query[f"phases.{phase}.detected"] = True
        
        if missing_phase:
            query["missing_phases"] = missing_phase
        
        total = await db.call_phases.count_documents(query)
        
        cursor = db.call_phases.find(query).skip(offset).limit(limit)
        results = await cursor.to_list(length=limit)
        
        # Clean results
        calls = []
        for r in results:
            r.pop("_id", None)
            calls.append({
                "call_id": r["call_id"],
                "has_missing_phases": r.get("has_missing_phases", False),
                "missing_phases": r.get("missing_phases", []),
                "overall_flow_score": r.get("overall_flow_score"),
                "processed_at": r.get("processed_at")
            })
        
        return {
            "company_id": company_id,
            "phase": phase,
            "missing_phase": missing_phase,
            "total": total,
            "limit": limit,
            "offset": offset,
            "calls": calls
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")


@router.get("/phases/analytics")
async def get_phase_analytics(
    company_id: str,
    days: int = 30,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get aggregated phase analytics for a company (per Q57).
    
    Returns:
    - Average time per phase
    - Detection rates
    - Commonly missing phases
    """
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        from datetime import timedelta
        
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=days)
        
        # Query that handles both datetime objects and ISO string dates
        # (old data may have been stored with model_dump(mode='json') which converts to strings)
        period_start_str = period_start.isoformat()
        period_end_str = period_end.isoformat()
        
        query = {
            "company_id": company_id,
            "$or": [
                # Match datetime objects (new format)
                {"processed_at": {"$gte": period_start, "$lte": period_end}},
                # Match ISO string dates (legacy format)
                {"processed_at": {"$gte": period_start_str, "$lte": period_end_str}}
            ]
        }
        
        cursor = db.call_phases.find(query)
        all_phases = await cursor.to_list(length=10000)
        
        if not all_phases:
            return {
                "company_id": company_id,
                "period_start": period_start,
                "period_end": period_end,
                "total_calls": 0,
                "avg_time_per_phase": {},
                "detection_rates": {},
                "commonly_missing": []
            }
        
        # Aggregate metrics
        phase_durations = {}
        phase_detections = {}
        missing_counts = {}
        
        phase_names = ["greeting", "problem_discovery", "qualification", 
                       "objection_handling", "closing", "post_close"]
        
        for phase in phase_names:
            phase_durations[phase] = []
            phase_detections[phase] = 0
            missing_counts[phase] = 0
        
        for call_phases in all_phases:
            phases = call_phases.get("phases", {})
            
            for phase in phase_names:
                phase_data = phases.get(phase, {})
                if phase_data.get("detected"):
                    phase_detections[phase] += 1
                    timestamps = phase_data.get("timestamps", {})
                    if timestamps:
                        duration = timestamps.get("duration_ms", 0)
                        if duration > 0:
                            phase_durations[phase].append(duration)
                
                if phase in call_phases.get("missing_phases", []):
                    missing_counts[phase] += 1
        
        total = len(all_phases)
        
        # Calculate averages
        avg_time = {}
        for phase, durations in phase_durations.items():
            if durations:
                avg_time[phase] = sum(durations) / len(durations)
            else:
                avg_time[phase] = 0
        
        # Detection rates
        detection_rates = {}
        for phase, count in phase_detections.items():
            detection_rates[phase] = count / total if total > 0 else 0
        
        # Commonly missing (sorted by frequency)
        commonly_missing = sorted(
            missing_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        return {
            "company_id": company_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_calls": total,
            "avg_time_per_phase": avg_time,
            "detection_rates": detection_rates,
            "commonly_missing": [p[0] for p in commonly_missing if p[1] > 0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


# ============================================================================
# CALL DATA LISTING ENDPOINTS
# ============================================================================

from typing import List
from pydantic import BaseModel, Field
from fastapi import Query


class CallSummaryListItem(BaseModel):
    """Summary item for list response"""
    call_id: str
    company_id: str
    summary: Optional[dict] = None
    compliance: Optional[dict] = None
    qualification: Optional[dict] = None
    objections: Optional[dict] = None
    lead_score: Optional[dict] = None
    sop_evaluation: Optional[dict] = None
    created_at: Optional[datetime] = None


class CallSummariesListResponse(BaseModel):
    """Response for listing call summaries"""
    company_id: str
    total: int
    limit: int
    offset: int
    summaries: List[CallSummaryListItem]


class CallListItem(BaseModel):
    """Call item for list response"""
    call_id: str
    company_id: str
    status: str
    audio_url: Optional[str] = None
    phone_number: Optional[str] = None
    rep_role: Optional[str] = None
    duration: Optional[int] = None
    duration_ms: Optional[int] = None
    call_date: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    metadata: Optional[dict] = None


class CallsListResponse(BaseModel):
    """Response for listing calls"""
    company_id: str
    total: int
    limit: int
    offset: int
    calls: List[CallListItem]


class CallDetailResponse(BaseModel):
    """Full call detail response"""
    call_id: str
    company_id: str
    status: str
    audio_url: Optional[str] = None
    phone_number: Optional[str] = None
    rep_role: Optional[str] = None
    duration: Optional[int] = None
    duration_ms: Optional[int] = None
    call_date: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    metadata: Optional[dict] = None
    transcript: Optional[str] = None
    segments: Optional[List[dict]] = None


@router.get("/summaries", response_model=CallSummariesListResponse)
async def list_call_summaries(
    company_id: str = Query(..., description="Company ID (required)"),
    rep_id: Optional[str] = Query(None, description="Filter by rep ID (from metadata.rep_id)"),
    status: Optional[str] = Query(None, description="Filter by call status"),
    from_date: Optional[datetime] = Query(None, description="Filter calls from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter calls until this date"),
    min_compliance_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum compliance score"),
    max_compliance_score: Optional[float] = Query(None, ge=0, le=1, description="Maximum compliance score"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("created_at", description="Sort field: created_at, compliance_score"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    List call summaries for a company with pagination and filters.
    
    Returns structured summaries including compliance, qualification, objections, and lead scores.
    """
    try:
        # Build query
        query = {"company_id": company_id}
        
        # Date filters
        if from_date or to_date:
            date_filter = {}
            if from_date:
                date_filter["$gte"] = from_date
            if to_date:
                date_filter["$lte"] = to_date
            if date_filter:
                query["created_at"] = date_filter
        
        # Compliance score filters
        if min_compliance_score is not None or max_compliance_score is not None:
            score_filter = {}
            if min_compliance_score is not None:
                score_filter["$gte"] = min_compliance_score
            if max_compliance_score is not None:
                score_filter["$lte"] = max_compliance_score
            if score_filter:
                query["compliance.sop_compliance.score"] = score_filter
        
        # Get total count
        total = await db.call_summaries.count_documents(query)
        
        # Determine sort direction
        sort_dir = -1 if sort_order == "desc" else 1
        sort_field = "created_at"
        if sort_by == "compliance_score":
            sort_field = "compliance.sop_compliance.score"
        
        # Fetch summaries
        cursor = db.call_summaries.find(query).sort(sort_field, sort_dir).skip(offset).limit(limit)
        summaries = await cursor.to_list(length=limit)
        
        # If rep_id filter, we need to cross-reference with calls collection
        if rep_id:
            # Get call_ids that match the rep_id
            calls_with_rep = await db.calls.find(
                {"company_id": company_id, "metadata.rep_id": rep_id},
                {"call_id": 1}
            ).to_list(length=10000)
            rep_call_ids = {c["call_id"] for c in calls_with_rep}
            
            # Filter summaries by rep
            summaries = [s for s in summaries if s.get("call_id") in rep_call_ids]
            total = len(summaries)
        
        # Format response
        summary_items = []
        for s in summaries:
            s.pop("_id", None)
            summary_items.append(CallSummaryListItem(
                call_id=s.get("call_id", ""),
                company_id=s.get("company_id", company_id),
                summary=s.get("summary"),
                compliance=s.get("compliance"),
                qualification=s.get("qualification"),
                objections=s.get("objections"),
                lead_score=s.get("lead_score"),
                sop_evaluation=s.get("sop_evaluation"),
                created_at=s.get("created_at")
            ))
        
        return CallSummariesListResponse(
            company_id=company_id,
            total=total,
            limit=limit,
            offset=offset,
            summaries=summary_items
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list summaries: {str(e)}")


@router.get("/calls", response_model=CallsListResponse)
async def list_calls(
    company_id: str = Query(..., description="Company ID (required)"),
    call_ids: Optional[str] = Query(None, description="Comma-separated list of specific call IDs"),
    rep_id: Optional[str] = Query(None, description="Filter by rep ID (from metadata.rep_id)"),
    rep_name: Optional[str] = Query(None, description="Filter by rep name (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status: queued, processing, completed, failed"),
    phone_number: Optional[str] = Query(None, description="Filter by phone number (partial match)"),
    from_date: Optional[datetime] = Query(None, description="Filter calls from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter calls until this date"),
    min_duration: Optional[int] = Query(None, ge=0, description="Minimum call duration in seconds"),
    max_duration: Optional[int] = Query(None, ge=0, description="Maximum call duration in seconds"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("call_date", description="Sort field: call_date, created_at, duration"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    List calls for a company with pagination and filters.
    
    Returns call metadata including status, duration, rep info, and timestamps.
    """
    try:
        # Build query
        query = {"company_id": company_id}
        
        # Specific call IDs filter
        if call_ids:
            id_list = [cid.strip() for cid in call_ids.split(",")]
            query["call_id"] = {"$in": id_list}
        
        # Rep filters
        if rep_id:
            query["metadata.rep_id"] = rep_id
        if rep_name:
            query["metadata.rep_name"] = {"$regex": rep_name, "$options": "i"}
        
        # Status filter
        if status:
            query["status"] = status
        
        # Phone number filter (partial match)
        if phone_number:
            query["phone_number"] = {"$regex": phone_number}
        
        # Date filters
        if from_date or to_date:
            date_filter = {}
            if from_date:
                date_filter["$gte"] = from_date
            if to_date:
                date_filter["$lte"] = to_date
            if date_filter:
                query["call_date"] = date_filter
        
        # Duration filters
        if min_duration is not None or max_duration is not None:
            duration_filter = {}
            if min_duration is not None:
                duration_filter["$gte"] = min_duration
            if max_duration is not None:
                duration_filter["$lte"] = max_duration
            if duration_filter:
                query["duration"] = duration_filter
        
        # Get total count
        total = await db.calls.count_documents(query)
        
        # Determine sort direction
        sort_dir = -1 if sort_order == "desc" else 1
        sort_field = sort_by if sort_by in ["call_date", "created_at", "duration"] else "call_date"
        
        # Fetch calls
        cursor = db.calls.find(query).sort(sort_field, sort_dir).skip(offset).limit(limit)
        calls = await cursor.to_list(length=limit)
        
        # Format response
        call_items = []
        for c in calls:
            c.pop("_id", None)
            call_items.append(CallListItem(
                call_id=c.get("call_id", ""),
                company_id=c.get("company_id", company_id),
                status=c.get("status", "unknown"),
                audio_url=c.get("audio_url"),
                phone_number=c.get("phone_number"),
                rep_role=c.get("rep_role"),
                duration=c.get("duration"),
                duration_ms=c.get("duration_ms"),
                call_date=c.get("call_date"),
                processed_at=c.get("processed_at"),
                created_at=c.get("created_at"),
                metadata=c.get("metadata")
            ))
        
        return CallsListResponse(
            company_id=company_id,
            total=total,
            limit=limit,
            offset=offset,
            calls=call_items
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list calls: {str(e)}")


@router.get("/calls/{call_id}/detail", response_model=CallDetailResponse)
async def get_call_detail(
    call_id: str,
    include_transcript: bool = Query(True, description="Include full transcript"),
    include_segments: bool = Query(False, description="Include diarized segments"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get full details for a specific call including transcript and segments.
    """
    try:
        call = await db.calls.find_one({"call_id": call_id})
        
        if not call:
            raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
        
        call.pop("_id", None)
        
        response_data = {
            "call_id": call.get("call_id", ""),
            "company_id": call.get("company_id", ""),
            "status": call.get("status", "unknown"),
            "audio_url": call.get("audio_url"),
            "phone_number": call.get("phone_number"),
            "rep_role": call.get("rep_role"),
            "duration": call.get("duration"),
            "duration_ms": call.get("duration_ms"),
            "call_date": call.get("call_date"),
            "processed_at": call.get("processed_at"),
            "created_at": call.get("created_at"),
            "metadata": call.get("metadata")
        }
        
        if include_transcript:
            response_data["transcript"] = call.get("transcript")
        
        if include_segments:
            response_data["segments"] = call.get("segments")
        
        return CallDetailResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get call detail: {str(e)}")
