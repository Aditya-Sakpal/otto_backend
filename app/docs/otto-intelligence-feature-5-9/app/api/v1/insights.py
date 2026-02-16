"""
Insights API Endpoints

REST API for weekly insights generation and retrieval.
Includes BANT-based lead scoring endpoints (per Q25-Q36).
"""

import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Path
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from ...schemas.insight import (
    GenerateInsightsRequest,
    GenerateInsightsResponse,
    InsightJobStatusResponse,
    CompanyInsightResponse,
    CustomerInsightResponse,
    CustomersInsightsResponse,
    CustomerInsightListItem,
    ObjectionInsightResponse,
    InsightGenerationProgress,
    InsightGenerationResults
)
from ...models.enums import ProcessingStatus, InsightType, LeadBand
from ...models.insight import ObjectionInsightData
from ...core.database import get_database
from ...core.redis_client import get_redis_client
from ...tasks.insight_tasks import generate_weekly_insights_background
from ...utils.uuid_validator import validate_uuid
import json


router = APIRouter(prefix="/api/v1/insights", tags=["Insights"])


# ============================================================================
# LEAD SCORING RESPONSE MODELS
# ============================================================================

class LeadScoreItem(BaseModel):
    """Lead score for a single call/customer"""
    call_id: str
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    total_score: int
    lead_band: str
    confidence: str
    calculated_at: datetime
    call_date: Optional[datetime] = None


class LeadListResponse(BaseModel):
    """Response for lead list endpoint"""
    company_id: str
    total: int
    page: int
    limit: int
    filters: dict
    leads: List[LeadScoreItem]


class LeadBandCount(BaseModel):
    """Count of leads in a band"""
    band: str
    count: int
    percentage: float


class LeadDistributionResponse(BaseModel):
    """Response for lead distribution endpoint"""
    company_id: str
    timeframe_days: int
    total_leads: int
    distribution: List[LeadBandCount]
    avg_score: float
    score_percentiles: dict


class LeadScoreHistoryItem(BaseModel):
    """Historical lead score entry"""
    call_id: str
    total_score: int
    lead_band: str
    calculated_at: datetime
    score_change: Optional[int] = None


class LeadScoreHistoryResponse(BaseModel):
    """Response for lead score history endpoint"""
    customer_id: str
    customer_phone: Optional[str] = None
    company_id: str
    current_score: Optional[int] = None
    current_band: Optional[str] = None
    history: List[LeadScoreHistoryItem]
    trend: str  # "improving", "stable", "declining"


@router.post("/generate", response_model=GenerateInsightsResponse, status_code=202)
async def generate_insights(
    request: GenerateInsightsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Trigger weekly insights generation.
    
    Designed to be called by external cron jobs.
    Background processing happens asynchronously.
    """
    # Generate job ID as pure UUID
    job_id = str(uuid.uuid4())
    
    # Determine date range
    if request.week_start and request.week_end:
        week_start = request.week_start
        week_end = request.week_end
    else:
        # Default to last week
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday() + 7)
        week_end = week_start + timedelta(days=6)
    
    # Check for existing job
    if not request.options.force_regenerate:
        existing = await db.weekly_insights.find_one({
            "week_start": datetime.combine(week_start, datetime.min.time()),
            "status": {"$in": ["generating", "completed"]}
        })
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Insights for week {week_start} already exist or are being generated"
            )
    
    # Count companies
    company_count = len(request.company_ids) if request.company_ids else 0
    if company_count == 0:
        # Estimate from active calls
        company_count = len(await db.calls.distinct("company_id", {
            "call_date": {
                "$gte": datetime.combine(week_start, datetime.min.time()),
                "$lte": datetime.combine(week_end, datetime.max.time())
            }
        }))
    
    # Queue background task
    try:
        redis = await get_redis_client()
        
        # Store initial job status
        status_data = {
            "job_id": job_id,
            "status": "queued",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "company_count": company_count,
            "created_at": datetime.utcnow().isoformat()
        }
        
        await redis.setex(
            f"insight_job:{job_id}:status",
            86400,  # 24 hours
            json.dumps(status_data)
        )
        
        # Add background task
        # Convert InsightType enums to strings for the task
        insight_types_str = [it.value if hasattr(it, 'value') else str(it) for it in request.insight_types]
        
        background_tasks.add_task(
            generate_weekly_insights_background,
            job_id,
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "company_ids": request.company_ids,
                "insight_types": insight_types_str,
                "webhook_url": str(request.webhook_url) if request.webhook_url else None,
                "options": request.options.dict()
            }
        )
        
        return GenerateInsightsResponse(
            job_id=job_id,
            status="queued",
            message=f"Insight generation initiated for week {week_start} to {week_end}",
            week_start=week_start,
            week_end=week_end,
            company_count=company_count,
            insight_types=["company", "customer", "objection"],  # Default types
            estimated_completion_time=None,
            estimated_duration="5-10 minutes",  # Estimate based on company count
            status_url=f"/api/v1/insights/status/{job_id}",
            created_at=datetime.utcnow(),
            queued_at=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate insight generation: {str(e)}"
        )


@router.get("/status/{job_id}", response_model=InsightJobStatusResponse)
async def get_insight_status(job_id: str):
    """Get the status of an insight generation job."""
    # Validate job_id is UUID
    try:
        validate_uuid(job_id, "job_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        redis = await get_redis_client()
        cache_key = f"insight_job:{job_id}:status"
        
        cached_data = await redis.get(cache_key)
        if not cached_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        status_data = json.loads(cached_data)
        
        status = ProcessingStatus(status_data["status"])
        progress_data = status_data.get("progress", {})
        
        progress = InsightGenerationProgress(
            percent=progress_data.get("percent", 0),
            current_step=progress_data.get("current_step", ""),
            companies_processed=progress_data.get("companies_processed", 0),
            companies_total=progress_data.get("companies_total", 0),
            insights_generated=progress_data.get("insights_generated", {})
        )
        
        response = InsightJobStatusResponse(
            job_id=job_id,
            status=status,
            week_start=date.fromisoformat(status_data.get("week_start", "2026-01-01")),
            week_end=date.fromisoformat(status_data.get("week_end", "2026-01-07")),
            progress=progress
        )
        
        if status == ProcessingStatus.COMPLETED:
            response.results = InsightGenerationResults(
                company_insights_url="/api/v1/insights/company/current",
                customer_insights_url="/api/v1/insights/customers",
                objection_insights_url="/api/v1/insights/objections"
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/company/{company_id}/current", response_model=CompanyInsightResponse)
async def get_current_company_insight(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get the most recent company insight."""
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        insight = await db.weekly_insights.find_one(
            {"insight_type": "company", "company_id": company_id},
            sort=[("week_start", -1)]
        )
        
        if not insight:
            raise HTTPException(
                status_code=404,
                detail=f"No insights found for company {company_id}"
            )
        
        insight.pop("_id", None)
        return CompanyInsightResponse(**insight)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers", response_model=CustomersInsightsResponse)
async def get_customers_insights(
    company_id: str = Query(..., description="Company ID (UUID format)"),
    week_start: Optional[date] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get customer insights list."""
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        # Build query
        query = {"insight_type": "customer", "company_id": company_id}
        
        if week_start:
            query["week_start"] = datetime.combine(week_start, datetime.min.time())
        
        if status:
            query["data.current_status"] = status
        
        if priority:
            query["data.priority"] = priority
        
        # Get total count
        total = await db.weekly_insights.count_documents(query)
        
        # Get paginated results
        skip = (page - 1) * limit
        cursor = db.weekly_insights.find(query).skip(skip).limit(limit)
        insights = await cursor.to_list(length=limit)
        
        # Format response
        customers = [
            CustomerInsightListItem(
                customer_id=i["customer_id"],
                phone_number=i["phone_number"],
                customer_name=i.get("customer_name"),
                data=i["data"]
            )
            for i in insights
        ]
        
        return CustomersInsightsResponse(
            company_id=company_id,
            week_start=week_start or date.today(),
            total_customers=total,
            page=page,
            limit=limit,
            customers=customers
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/objections/{company_id}", response_model=ObjectionInsightResponse)
async def get_objection_insights(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    week_start: Optional[date] = None,
    category_id: Optional[int] = Query(None, ge=1, le=10),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get objection insights for a company."""
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        query = {"insight_type": "objection", "company_id": company_id}
        
        if week_start:
            query["week_start"] = datetime.combine(week_start, datetime.min.time())
        
        if category_id:
            query["data.category_id"] = category_id
        
        cursor = db.weekly_insights.find(query)
        insights = await cursor.to_list(length=None)
        
        if not insights:
            raise HTTPException(
                status_code=404,
                detail=f"No objection insights found"
            )
        
        # Convert to response format
        objections = [ObjectionInsightData(**i["data"]) for i in insights]
        
        return ObjectionInsightResponse(
            company_id=company_id,
            week_start=insights[0]["week_start"].date(),
            week_end=insights[0]["week_end"].date(),
            total_categories=len(objections),
            objections=objections,
            generated_at=insights[0]["generated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEAD SCORING ENDPOINTS (per Q25-Q36)
# ============================================================================

@router.get("/leads", response_model=LeadListResponse)
async def get_leads(
    company_id: str = Query(..., description="Company ID (UUID format)"),
    band: Optional[str] = Query(None, description="Filter by lead band: hot, warm, cold"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum lead score"),
    max_score: Optional[int] = Query(None, ge=0, le=100, description="Maximum lead score"),
    timeframe_days: int = Query(30, ge=1, le=365, description="Timeframe in days"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get leads with optional filtering by band and score.
    
    Returns leads from call_summaries where lead_score is present.
    Sorted by lead score descending (hottest first).
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        # Build query
        cutoff_date = datetime.utcnow() - timedelta(days=timeframe_days)
        
        query = {
            "company_id": company_id,
            "lead_score": {"$exists": True, "$ne": None},
            "created_at": {"$gte": cutoff_date}
        }
        
        # Filter by band
        if band:
            band_lower = band.lower()
            if band_lower not in ["hot", "warm", "cold"]:
                raise HTTPException(status_code=400, detail=f"Invalid band: {band}. Must be hot, warm, or cold")
            query["lead_score.lead_band"] = band_lower
        
        # Filter by score range
        if min_score is not None or max_score is not None:
            score_filter = {}
            if min_score is not None:
                score_filter["$gte"] = min_score
            if max_score is not None:
                score_filter["$lte"] = max_score
            query["lead_score.total_score"] = score_filter
        
        # Get total count
        total = await db.call_summaries.count_documents(query)
        
        # Get paginated results, sorted by score descending
        skip = (page - 1) * limit
        cursor = db.call_summaries.find(query).sort("lead_score.total_score", -1).skip(skip).limit(limit)
        summaries = await cursor.to_list(length=limit)
        
        # Build response
        leads = []
        for summary in summaries:
            lead_score = summary.get("lead_score", {})
            qualification = summary.get("qualification", {})
            
            # Get call info for date
            call_doc = await db.calls.find_one({"call_id": summary["call_id"]})
            call_date = call_doc.get("call_date") if call_doc else None
            
            leads.append(LeadScoreItem(
                call_id=summary["call_id"],
                customer_phone=call_doc.get("phone_number") if call_doc else None,
                customer_name=qualification.get("customer_name"),
                total_score=lead_score.get("total_score", 0),
                lead_band=lead_score.get("lead_band", "cold"),
                confidence=lead_score.get("confidence", "low"),
                calculated_at=lead_score.get("calculated_at", summary.get("created_at", datetime.utcnow())),
                call_date=call_date
            ))
        
        filters = {"band": band, "min_score": min_score, "max_score": max_score, "timeframe_days": timeframe_days}
        
        return LeadListResponse(
            company_id=company_id,
            total=total,
            page=page,
            limit=limit,
            filters={k: v for k, v in filters.items() if v is not None},
            leads=leads
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get leads: {str(e)}")


@router.get("/leads/distribution", response_model=LeadDistributionResponse)
async def get_lead_distribution(
    company_id: str = Query(..., description="Company ID (UUID format)"),
    timeframe_days: int = Query(30, ge=1, le=365, description="Timeframe in days"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get lead score distribution statistics.
    
    Returns counts per band and percentile breakdown.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=timeframe_days)
        
        # Aggregation pipeline to get distribution
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "lead_score": {"$exists": True, "$ne": None},
                    "created_at": {"$gte": cutoff_date}
                }
            },
            {
                "$group": {
                    "_id": "$lead_score.lead_band",
                    "count": {"$sum": 1},
                    "scores": {"$push": "$lead_score.total_score"}
                }
            }
        ]
        
        cursor = db.call_summaries.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        # Calculate totals and distribution
        total_leads = sum(r["count"] for r in results)
        all_scores = []
        
        distribution = []
        for r in results:
            band = r["_id"] or "cold"
            count = r["count"]
            percentage = (count / total_leads * 100) if total_leads > 0 else 0
            all_scores.extend(r["scores"])
            
            distribution.append(LeadBandCount(
                band=band,
                count=count,
                percentage=round(percentage, 1)
            ))
        
        # Sort by band priority (hot first)
        band_order = {"hot": 0, "warm": 1, "cold": 2}
        distribution.sort(key=lambda x: band_order.get(x.band, 3))
        
        # Calculate percentiles
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        sorted_scores = sorted(all_scores)
        
        percentiles = {}
        if sorted_scores:
            for p in [25, 50, 75, 90]:
                idx = int(len(sorted_scores) * p / 100)
                percentiles[f"p{p}"] = sorted_scores[min(idx, len(sorted_scores) - 1)]
        
        return LeadDistributionResponse(
            company_id=company_id,
            timeframe_days=timeframe_days,
            total_leads=total_leads,
            distribution=distribution,
            avg_score=round(avg_score, 1),
            score_percentiles=percentiles
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get distribution: {str(e)}")


@router.get("/leads/{customer_id}/history", response_model=LeadScoreHistoryResponse)
async def get_lead_score_history(
    customer_id: str = Path(..., description="Customer ID or phone number"),
    company_id: str = Query(..., description="Company ID (UUID format)"),
    limit: int = Query(20, ge=1, le=100, description="Max history entries"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get lead score changes over time for a customer.
    
    Supports dynamic recalculation tracking (per Q31).
    Customer can be identified by customer_id or phone number.
    """
    # Validate company_id is UUID
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        # First, find the customer by ID or phone
        customer_doc = await db.customers.find_one({
            "company_id": company_id,
            "$or": [
                {"customer_id": customer_id},
                {"phone": customer_id}
            ]
        })
        
        # Build query for call summaries
        if customer_doc:
            phone_number = customer_doc.get("phone")
            query = {
                "company_id": company_id,
                "lead_score": {"$exists": True, "$ne": None}
            }
            
            # Get calls for this customer
            calls = await db.calls.find({
                "company_id": company_id,
                "phone_number": phone_number
            }).to_list(length=1000)
            
            call_ids = [c["call_id"] for c in calls]
            query["call_id"] = {"$in": call_ids}
        else:
            # Try using customer_id as phone number directly
            calls = await db.calls.find({
                "company_id": company_id,
                "phone_number": customer_id
            }).to_list(length=1000)
            
            if not calls:
                raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
            
            call_ids = [c["call_id"] for c in calls]
            query = {
                "company_id": company_id,
                "lead_score": {"$exists": True, "$ne": None},
                "call_id": {"$in": call_ids}
            }
            phone_number = customer_id
        
        # Get summaries sorted by date
        cursor = db.call_summaries.find(query).sort("created_at", -1).limit(limit)
        summaries = await cursor.to_list(length=limit)
        
        if not summaries:
            raise HTTPException(status_code=404, detail=f"No lead scores found for customer {customer_id}")
        
        # Build history with score changes
        history = []
        previous_score = None
        
        # Reverse to calculate changes chronologically
        for summary in reversed(summaries):
            lead_score = summary.get("lead_score", {})
            current_score = lead_score.get("total_score", 0)
            
            score_change = None
            if previous_score is not None:
                score_change = current_score - previous_score
            
            history.append(LeadScoreHistoryItem(
                call_id=summary["call_id"],
                total_score=current_score,
                lead_band=lead_score.get("lead_band", "cold"),
                calculated_at=lead_score.get("calculated_at", summary.get("created_at", datetime.utcnow())),
                score_change=score_change
            ))
            
            previous_score = current_score
        
        # Reverse back to show most recent first
        history.reverse()
        
        # Calculate trend
        if len(history) >= 2:
            first_score = history[-1].total_score
            last_score = history[0].total_score
            change_pct = ((last_score - first_score) / first_score * 100) if first_score > 0 else 0
            
            if change_pct >= 5:
                trend = "improving"
            elif change_pct <= -5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        current_lead = history[0] if history else None
        
        return LeadScoreHistoryResponse(
            customer_id=customer_id,
            customer_phone=phone_number if 'phone_number' in dir() else None,
            company_id=company_id,
            current_score=current_lead.total_score if current_lead else None,
            current_band=current_lead.lead_band if current_lead else None,
            history=history,
            trend=trend
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


# ============================================================================
# AGENT PROGRESSION ENDPOINTS (per Q37-Q48)
# ============================================================================

from ...services.insights.progression_service import get_progression_service
from ...models.progression import WeeklyMetrics, TrendResult, MetricProgression


class ProgressionMetricResponse(BaseModel):
    """Response for a single metric's progression"""
    metric_name: str
    data_points: List[dict]
    trend_direction: str
    trend_magnitude: float
    anomalies: List[dict]
    current_value: float
    period_change_percent: float


class AgentProgressionResponse(BaseModel):
    """Response for agent progression"""
    rep_id: str
    rep_name: str
    company_id: str
    timeframe_weeks: int
    period_start: datetime
    period_end: datetime
    total_calls: int
    weeks_with_data: int
    overall_confidence: str
    metrics: dict
    improving_metrics: List[str]
    declining_metrics: List[str]
    stable_metrics: List[str]


class PeerComparisonResponse(BaseModel):
    """Response for peer comparison"""
    rep_id: str
    rep_name: str
    company_id: str
    metric: str
    rep_score: float
    rep_rank: int
    peer_count: int
    peer_average: float
    peer_median: float
    percentile: int
    analysis_period_days: int


class AgentSummaryResponse(BaseModel):
    """Response for agent summary"""
    rep_id: str
    rep_name: str
    total_calls: int
    avg_compliance: float
    avg_booking_rate: float
    trend_direction: str
    alerts: List[str]


class AgentsSummaryResponse(BaseModel):
    """Response for agents summary list"""
    company_id: str
    timeframe_weeks: int
    total_agents: int
    agents: List[AgentSummaryResponse]


@router.get("/agents/{rep_id}/progression", response_model=AgentProgressionResponse)
async def get_agent_progression(
    rep_id: str = Path(..., description="Representative ID"),
    company_id: str = Query(..., description="Company ID"),
    metrics: str = Query("compliance_score,booking_rate", description="Comma-separated metrics"),
    weeks: int = Query(8, ge=4, le=52, description="Number of weeks to analyze"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get agent behavior progression over time (per Q37-Q48).
    
    Tracks weekly metrics and detects:
    - Trends (improving/stable/declining - 5% threshold)
    - Anomalies (>20% sudden change)
    
    Returns low-confidence flag if insufficient calls per week.
    """
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        progression_service = get_progression_service(db)
        
        # Parse metrics
        metrics_list = [m.strip() for m in metrics.split(",")]
        
        progression = await progression_service.get_agent_progression(
            rep_id=rep_id,
            company_id=company_id,
            metrics=metrics_list,
            weeks=weeks
        )
        
        # Convert to response format
        metrics_response = {}
        for metric_name, metric_data in progression.metrics.items():
            metrics_response[metric_name] = {
                "metric_name": metric_data.metric_name,
                "data_points": [dp.model_dump(mode='json') for dp in metric_data.data_points],
                "trend": metric_data.trend.model_dump(),
                "anomalies": [a.model_dump(mode='json') for a in metric_data.anomalies],
                "current_value": metric_data.current_value,
                "period_change_percent": metric_data.period_change_percent
            }
        
        return AgentProgressionResponse(
            rep_id=progression.rep_id,
            rep_name=progression.rep_name,
            company_id=progression.company_id,
            timeframe_weeks=progression.timeframe_weeks,
            period_start=progression.period_start,
            period_end=progression.period_end,
            total_calls=progression.total_calls,
            weeks_with_data=progression.weeks_with_data,
            overall_confidence=progression.overall_confidence,
            metrics=metrics_response,
            improving_metrics=progression.improving_metrics,
            declining_metrics=progression.declining_metrics,
            stable_metrics=progression.stable_metrics
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get progression: {str(e)}")


@router.get("/agents/{rep_id}/peer-comparison", response_model=PeerComparisonResponse)
async def get_peer_comparison(
    rep_id: str = Path(..., description="Representative ID"),
    company_id: str = Query(..., description="Company ID"),
    metric: str = Query("compliance_score", description="Metric to compare"),
    days: int = Query(30, ge=7, le=90, description="Analysis period in days"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    On-demand peer comparison (per Q45-Q46).
    
    Compares rep's score to all peers in same company.
    Returns ranking, percentile, and distribution stats.
    
    Note: Per manager decision, this is NOT shown by default.
    """
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        progression_service = get_progression_service(db)
        
        comparison = await progression_service.get_peer_comparison(
            rep_id=rep_id,
            metric=metric,
            company_id=company_id,
            days=days
        )
        
        return PeerComparisonResponse(
            rep_id=comparison.rep_id,
            rep_name=comparison.rep_name,
            company_id=comparison.company_id,
            metric=comparison.metric,
            rep_score=comparison.rep_score,
            rep_rank=comparison.rep_rank,
            peer_count=comparison.peer_count,
            peer_average=comparison.peer_average,
            peer_median=comparison.peer_median,
            percentile=comparison.percentile,
            analysis_period_days=comparison.analysis_period_days
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get comparison: {str(e)}")


@router.get("/agents/summary", response_model=AgentsSummaryResponse)
async def get_agents_summary(
    company_id: str = Query(..., description="Company ID"),
    weeks: int = Query(4, ge=1, le=12, description="Analysis period in weeks"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get summary of all agents for manager dashboard.
    
    Returns high-level metrics for each agent:
    - Total calls
    - Average compliance
    - Booking rate
    - Overall trend
    - Any alerts
    """
    # Validate company_id
    try:
        validate_uuid(company_id, "company_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        progression_service = get_progression_service(db)
        
        summaries = await progression_service.get_agents_summary(
            company_id=company_id,
            weeks=weeks
        )
        
        return AgentsSummaryResponse(
            company_id=company_id,
            timeframe_weeks=weeks,
            total_agents=len(summaries),
            agents=[
                AgentSummaryResponse(
                    rep_id=s.rep_id,
                    rep_name=s.rep_name,
                    total_calls=s.total_calls,
                    avg_compliance=s.avg_compliance,
                    avg_booking_rate=s.avg_booking_rate,
                    trend_direction=s.trend_direction,
                    alerts=s.alerts
                )
                for s in summaries
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agents summary: {str(e)}")
