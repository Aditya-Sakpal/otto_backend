"""
Insights API routes.

Handles weekly AI insights generation and retrieval.
"""
from typing import Optional, List
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.core.logging import get_logger
from app.infrastructure.database.models.insight_job import InsightJobORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/insights", tags=["insights"])
logger = get_logger(__name__)


# Request/Response Models
class GenerateInsightsRequest(BaseModel):
    """Request to generate insights."""
    week_start: str = Field(..., description="Week start date (YYYY-MM-DD)")
    week_end: str = Field(..., description="Week end date (YYYY-MM-DD)")
    company_ids: List[str] = Field(..., description="List of company UUIDs")
    insight_types: List[str] = Field(..., description="List of insight types: company, customer, objection, etc.")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for completion notification")
    options: dict = Field(
        default_factory=dict,
        description="Options: force_regenerate, include_inactive_customers"
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_insights(
    request: GenerateInsightsRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.EXECUTIVE])),
):
    """
    Generate insights for specified companies and week range.
    
    Processing happens asynchronously. Returns a job_id for tracking.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        # Submit to Shunya
        result = await shoonya.generate_insights(
            week_start=request.week_start,
            week_end=request.week_end,
            company_ids=request.company_ids,
            insight_types=request.insight_types,
            webhook_url=request.webhook_url,
            options=request.options,
        )
        
        # Store job in database
        from datetime import datetime as dt
        job = InsightJobORM(
            company_id=UUID(request.company_ids[0]) if request.company_ids else None,
            shunya_job_id=result["job_id"],
            week_start=dt.strptime(request.week_start, "%Y-%m-%d").date(),
            week_end=dt.strptime(request.week_end, "%Y-%m-%d").date(),
            company_ids=request.company_ids,
            insight_types=request.insight_types,
            status=result.get("status", "queued"),
            force_regenerate=request.options.get("force_regenerate", False),
            include_inactive_customers=request.options.get("include_inactive_customers", False),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate insights: {str(e)}",
        )


@router.get("/status/{job_id}")
async def get_insight_job_status(
    job_id: str,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.EXECUTIVE])),
):
    """
    Get insight generation job status.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        # Get status from Shunya
        result = await shoonya.get_insight_job_status(job_id)
        
        # Update local job record
        job_query = select(InsightJobORM).where(
            InsightJobORM.shunya_job_id == job_id
        )
        job_result = await db.execute(job_query)
        job = job_result.scalar_one_or_none()
        
        if job:
            job.status = result.get("status", job.status)
            job.started_at = result.get("started_at")
            job.completed_at = result.get("completed_at")
            job.failed_at = result.get("failed_at")
            job.results = result.get("results")
            job.error = result.get("error")
            
            await db.commit()
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting insight job status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


@router.get("/company/{company_id}/current")
async def get_current_company_insight(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get current company insight.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        result = await shoonya.get_current_company_insight(company_id=str(company_id))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting company insight: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company insight: {str(e)}",
        )


@router.get("/customers")
async def get_customer_insights(
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    company_id: UUID = Query(..., description="Company UUID"),
    week_start: Optional[str] = Query(None, description="Week start date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Status filter"),
    priority: Optional[str] = Query(None, description="Priority filter"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
):
    """
    Get customer insights.
    
    Returns paginated customer insights with optional filters.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        result = await shoonya.get_customer_insights(
            company_id=str(company_id),
            week_start=week_start,
            status=status,
            priority=priority,
            page=page,
            limit=limit,
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customer insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get customer insights: {str(e)}",
        )


@router.get("/objections/{company_id}")
async def get_objection_insights(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get objection insights for a company.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        result = await shoonya.get_objection_insights(company_id=str(company_id))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting objection insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get objection insights: {str(e)}",
        )
