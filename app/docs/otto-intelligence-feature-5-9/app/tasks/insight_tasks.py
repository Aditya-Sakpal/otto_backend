"""
Insight Generation Background Tasks (No Celery)

Background tasks for generating weekly insights using FastAPI BackgroundTasks.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from ..config import get_settings
from ..core.database import get_database
from ..core.redis_client import get_redis_client
from ..services.insights.company_insights import get_company_insights_service
from ..services.insights.customer_insights import get_customer_insights_service
from ..services.insights.objection_insights import get_objection_insights_service
from ..models.enums import ProcessingStatus, InsightType

settings = get_settings()
logger = logging.getLogger(__name__)


async def update_insight_job_status(
    job_id: str,
    status: ProcessingStatus,
    progress_percent: int = 0,
    current_step: str = "",
    companies_processed: int = 0,
    companies_total: int = 0,
    insights_generated: Dict[str, int] = None
):
    """Update insight job status in Redis"""
    try:
        redis = await get_redis_client()
        cache_key = f"insight_job:{job_id}:status"
        
        status_data = {
            "job_id": job_id,
            "status": status.value,
            "progress": {
                "percent": progress_percent,
                "current_step": current_step,
                "companies_processed": companies_processed,
                "companies_total": companies_total,
                "insights_generated": insights_generated or {}
            },
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await redis.setex(cache_key, 604800, json.dumps(status_data))  # 7 days TTL
    except Exception as e:
        logger.error(f"Failed to update insight job status: {e}")


async def generate_weekly_insights_background(job_id: str, request_data: Dict[str, Any]):
    """
    Background task for generating weekly insights.
    
    Args:
        job_id: Unique job identifier
        request_data: Insight generation request data
    """
    webhook_url = request_data.get("webhook_url")
    
    try:
        logger.info(f"Starting insight generation (job: {job_id})")
        logger.info(f"Request data: {request_data}")
        
        # Parse request
        week_start = datetime.fromisoformat(request_data["week_start"])
        week_end = datetime.fromisoformat(request_data["week_end"])
        company_ids = request_data.get("company_ids", [])
        options = request_data.get("options", {})
        # insight_types can be at top level or in options (for backwards compatibility)
        insight_types = request_data.get("insight_types") or options.get("insight_types", ["company", "customer", "objection"])
        
        await update_insight_job_status(
            job_id, ProcessingStatus.PROCESSING, 10, "identifying_companies"
        )
        
        # Get database
        db = await get_database()
        
        # Identify active companies if not specified
        if not company_ids:
            company_ids = await db.calls.distinct("company_id", {
                "call_date": {"$gte": week_start, "$lte": week_end}
            })
        
        companies_total = len(company_ids)
        insights_generated = {"company": 0, "customer": 0, "objection": 0}
        
        logger.info(f"Processing {companies_total} companies: {company_ids}")
        logger.info(f"Insight types to generate: {insight_types}")
        
        await update_insight_job_status(
            job_id, ProcessingStatus.PROCESSING, 20, "generating_insights",
            0, companies_total, insights_generated
        )
        
        # Get services
        company_service = get_company_insights_service()
        customer_service = get_customer_insights_service()
        objection_service = get_objection_insights_service()
        
        # Generate insights for each company
        for idx, company_id in enumerate(company_ids):
            try:
                logger.info(f"Processing company {idx+1}/{companies_total}: {company_id}")
                
                # Company-level insights
                if "company" in insight_types:
                    company_insight_data = await company_service.generate_company_insight(
                        db=db,
                        company_id=company_id,
                        week_start=week_start,
                        week_end=week_end
                    )
                    
                    # Store in MongoDB
                    await db.weekly_insights.update_one(
                        {
                            "company_id": company_id,
                            "week_start": week_start,
                            "insight_type": InsightType.COMPANY.value
                        },
                        {
                            "$set": {
                                "company_id": company_id,
                                "week_start": week_start,
                                "week_end": week_end,
                                "insight_type": InsightType.COMPANY.value,
                                "data": company_insight_data.dict() if hasattr(company_insight_data, 'dict') else company_insight_data,
                                "generated_at": datetime.utcnow(),
                                "status": "completed",
                                "job_id": job_id,
                                "updated_at": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    
                    insights_generated["company"] += 1
                    logger.info(f"Generated company insight for {company_id}")
                
                # Customer-level insights
                if "customer" in insight_types:
                    customer_insights_list = await customer_service.generate_customer_insights(
                        db=db,
                        company_id=company_id,
                        week_start=week_start,
                        week_end=week_end
                    )
                    
                    for customer_insight in customer_insights_list:
                        # Handle both dict and Pydantic model
                        insight_data = customer_insight.dict() if hasattr(customer_insight, 'dict') else customer_insight
                        
                        await db.weekly_insights.update_one(
                            {
                                "company_id": company_id,
                                "customer_id": insight_data.get("customer_id"),
                                "week_start": week_start,
                                "insight_type": InsightType.CUSTOMER.value
                            },
                            {
                                "$set": {
                                    "company_id": company_id,
                                    "customer_id": insight_data.get("customer_id"),
                                    "phone_number": insight_data.get("phone_number"),
                                    "customer_name": insight_data.get("customer_name"),
                                    "week_start": week_start,
                                    "week_end": week_end,
                                    "insight_type": InsightType.CUSTOMER.value,
                                    "data": insight_data.get("data", insight_data),
                                    "generated_at": datetime.utcnow(),
                                    "status": "completed",
                                    "job_id": job_id,
                                    "updated_at": datetime.utcnow()
                                }
                            },
                            upsert=True
                        )
                    
                    insights_generated["customer"] += len(customer_insights_list)
                    logger.info(f"Generated {len(customer_insights_list)} customer insights for {company_id}")
                
                # Objection insights
                if "objection" in insight_types:
                    objection_insights_list = await objection_service.generate_objection_insights(
                        db=db,
                        company_id=company_id,
                        week_start=week_start,
                        week_end=week_end
                    )
                    
                    for objection_insight in objection_insights_list:
                        # Handle both dict and Pydantic model
                        insight_data = objection_insight.dict() if hasattr(objection_insight, 'dict') else objection_insight
                        
                        await db.weekly_insights.update_one(
                            {
                                "company_id": company_id,
                                "week_start": week_start,
                                "insight_type": InsightType.OBJECTION.value,
                                "data.category_id": insight_data.get("category_id")
                            },
                            {
                                "$set": {
                                    "company_id": company_id,
                                    "week_start": week_start,
                                    "week_end": week_end,
                                    "insight_type": InsightType.OBJECTION.value,
                                    "data": insight_data,
                                    "generated_at": datetime.utcnow(),
                                    "status": "completed",
                                    "job_id": job_id,
                                    "updated_at": datetime.utcnow()
                                }
                            },
                            upsert=True
                        )
                    
                    insights_generated["objection"] += len(objection_insights_list)
                    logger.info(f"Generated {len(objection_insights_list)} objection insights for {company_id}")
                
                # Update progress
                progress_percent = 20 + int(((idx + 1) / companies_total) * 80)
                await update_insight_job_status(
                    job_id, ProcessingStatus.PROCESSING, progress_percent,
                    f"processing_company_{idx+1}_of_{companies_total}",
                    idx + 1, companies_total, insights_generated
                )
                
            except Exception as e:
                logger.error(f"Failed to generate insights for company {company_id}: {e}")
                continue
        
        # Mark as completed
        await update_insight_job_status(
            job_id, ProcessingStatus.COMPLETED, 100, "completed",
            companies_total, companies_total, insights_generated
        )
        
        logger.info(f"Insight generation completed (job: {job_id})")
        
        # Send webhook notification if URL provided
        if webhook_url:
            from ..utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="completed",
                event_type="insight_generation",
                payload_data={
                    "week_start": request_data["week_start"],
                    "week_end": request_data["week_end"],
                    "insights_generated": insights_generated,
                    "companies_processed": companies_total,
                    "results": {
                        "company_insights_url": "/api/v1/insights/company/current",
                        "customer_insights_url": "/api/v1/insights/customers",
                        "objection_insights_url": "/api/v1/insights/objections"
                    }
                }
            )
        
        return {
            "job_id": job_id,
            "status": "completed",
            "insights_generated": insights_generated,
            "companies_processed": companies_total
        }
        
    except Exception as e:
        logger.error(f"Insight generation failed (job: {job_id}): {str(e)}")
        
        await update_insight_job_status(
            job_id, ProcessingStatus.FAILED, 0, "failed"
        )
        
        # Send webhook notification for failure if URL provided
        if webhook_url:
            from ..utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="failed",
                event_type="insight_generation",
                payload_data={
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__
                    }
                }
            )
        
        raise

