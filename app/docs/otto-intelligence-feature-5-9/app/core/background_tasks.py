"""
Background Task Manager (Replaces Celery)

Uses FastAPI BackgroundTasks + Redis for async job processing.
No need for Celery worker - tasks run in the FastAPI process.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from functools import wraps

from ..core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks using FastAPI BackgroundTasks + Redis for status tracking"""
    
    @staticmethod
    async def update_job_status(
        job_id: str,
        status: str,
        progress: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """Update job status in Redis"""
        try:
            redis = await get_redis_client()
            
            status_data = {
                "job_id": job_id,
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if progress:
                status_data["progress"] = progress
            if result:
                status_data["result"] = result
            if error:
                status_data["error"] = error
            
            await redis.setex(
                f"job:{job_id}:status",
                86400,  # 24 hours
                json.dumps(status_data)
            )
            
            logger.info(f"Job {job_id} status updated to {status}")
            
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
    
    @staticmethod
    async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status from Redis"""
        try:
            redis = await get_redis_client()
            cached_data = await redis.get(f"job:{job_id}:status")
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return None
    
    @staticmethod
    def background_task(task_name: str):
        """Decorator to wrap async functions as background tasks with error handling"""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(job_id: str, *args, **kwargs):
                try:
                    logger.info(f"Starting background task: {task_name} (job_id: {job_id})")
                    
                    # Update status to processing
                    await BackgroundTaskManager.update_job_status(
                        job_id=job_id,
                        status="processing",
                        progress={"percent": 0, "current_step": task_name}
                    )
                    
                    # Execute the actual task
                    result = await func(job_id, *args, **kwargs)
                    
                    # Update status to completed
                    await BackgroundTaskManager.update_job_status(
                        job_id=job_id,
                        status="completed",
                        progress={"percent": 100, "current_step": "done"},
                        result=result
                    )
                    
                    logger.info(f"Background task completed: {task_name} (job_id: {job_id})")
                    return result
                    
                except Exception as e:
                    logger.error(f"Background task failed: {task_name} (job_id: {job_id}): {str(e)}")
                    
                    # Update status to failed
                    await BackgroundTaskManager.update_job_status(
                        job_id=job_id,
                        status="failed",
                        error=str(e)
                    )
                    
                    raise
            
            return wrapper
        return decorator


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """Get singleton task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager

