"""
Webhook Notification Utility

Shared utility for sending webhook notifications across different services.
"""

import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


async def send_webhook_notification(
    webhook_url: str,
    job_id: str,
    status: str,
    event_type: str,  # "call_processing", "insight_generation", "sop_processing"
    payload_data: Dict[str, Any]
):
    """
    Send webhook notification to the provided URL.
    
    Args:
        webhook_url: The webhook URL to POST to
        job_id: Job identifier
        status: Processing status (completed/failed)
        event_type: Type of event (call_processing, insight_generation, sop_processing)
        payload_data: Additional data specific to the event type
    """
    try:
        # Build base payload
        payload = {
            "job_id": job_id,
            "status": status,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **payload_data  # Merge event-specific data
        }
        
        # Send webhook with timeout and retry
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Otto-Intelligence-Webhook/1.0"
                }
            )
            
            if 200 <= response.status_code < 300:
                logger.info(f"Webhook notification sent successfully to {webhook_url} for job {job_id} ({event_type})")
            else:
                # Log response body for debugging
                try:
                    response_body = response.json()
                    logger.warning(f"Webhook notification failed with status {response.status_code} for job {job_id} ({event_type}). Response: {response_body}")
                except Exception:
                    response_text = response.text[:500]  # First 500 chars
                    logger.warning(f"Webhook notification failed with status {response.status_code} for job {job_id} ({event_type}). Response: {response_text}")
    
    except httpx.TimeoutException:
        logger.error(f"Webhook notification timeout for job {job_id} ({event_type}): {webhook_url}")
    except httpx.RequestError as e:
        logger.error(f"Webhook notification network error for job {job_id} ({event_type}): {str(e)}")
    except Exception as e:
        # Don't fail the entire job if webhook fails
        logger.error(f"Failed to send webhook notification for job {job_id} ({event_type}): {str(e)}")

