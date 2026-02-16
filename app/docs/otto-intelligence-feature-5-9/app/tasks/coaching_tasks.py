"""
Coaching Background Tasks

Background tasks for coaching impact measurement.

Based on manager decisions:
- Q20: Automatic impact measurement on follow-up end
- Q21: Extend 1 week if insufficient calls, then flag
"""

import logging
from datetime import datetime
from typing import Dict, Any

from app.core.database import get_database
from app.services.coaching import get_coaching_service


logger = logging.getLogger(__name__)


async def check_coaching_follow_ups():
    """
    Daily task to check and complete coaching sessions.
    
    Logic (per Q20-Q21):
    1. Find sessions where follow_up_end_date <= now AND status = "in_progress" OR "extended"
    2. For each session:
       - Measure impact
       - If insufficient calls:
         - If not yet extended: extend by 7 days, status = "extended"
         - If already extended: status = "insufficient_data"
       - Otherwise: status = "completed"
    """
    try:
        logger.info("Starting daily coaching follow-up check")
        
        db = await get_database()
        coaching_service = get_coaching_service(db)
        
        now = datetime.utcnow()
        
        # Find sessions ready for completion
        query = {
            "follow_up_end_date": {"$lte": now},
            "status": {"$in": ["in_progress", "extended"]}
        }
        
        cursor = db.coaching_sessions.find(query)
        sessions = await cursor.to_list(length=100)
        
        if not sessions:
            logger.info("No coaching sessions ready for completion")
            return
        
        logger.info(f"Found {len(sessions)} coaching sessions to process")
        
        completed = 0
        extended = 0
        insufficient = 0
        errors = 0
        
        for session in sessions:
            session_id = session["session_id"]
            
            try:
                result = await coaching_service.check_and_complete_session(session_id)
                
                status = result.get("status", "error")
                if status == "completed":
                    completed += 1
                    logger.info(f"Completed session {session_id}")
                elif status == "extended":
                    extended += 1
                    logger.info(f"Extended session {session_id}: {result.get('message')}")
                elif status == "insufficient_data":
                    insufficient += 1
                    logger.info(f"Session {session_id} marked insufficient: {result.get('message')}")
                else:
                    logger.warning(f"Session {session_id} returned status: {status}")
                    
            except Exception as e:
                logger.error(f"Error processing session {session_id}: {e}")
                errors += 1
        
        logger.info(
            f"Coaching follow-up check complete: "
            f"{completed} completed, {extended} extended, {insufficient} insufficient, {errors} errors"
        )
        
    except Exception as e:
        logger.error(f"Coaching follow-up check failed: {e}", exc_info=True)


async def calculate_weekly_coach_effectiveness():
    """
    Weekly task to calculate aggregated coach effectiveness metrics.
    
    For each coach with sessions in the last week:
    1. Calculate effectiveness metrics
    2. Store in coach_effectiveness collection
    """
    try:
        logger.info("Starting weekly coach effectiveness calculation")
        
        db = await get_database()
        coaching_service = get_coaching_service(db)
        
        from datetime import timedelta
        
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=7)
        
        # Get all coaches with sessions this week
        coaches = await db.coaching_sessions.distinct("coach_id", {
            "coached_at": {"$gte": period_start}
        })
        
        if not coaches:
            logger.info("No coaching sessions this week")
            return
        
        logger.info(f"Calculating effectiveness for {len(coaches)} coaches")
        
        calculated = 0
        errors = 0
        
        for coach_id in coaches:
            try:
                # Get company_id from a session
                session = await db.coaching_sessions.find_one({"coach_id": coach_id})
                if not session:
                    continue
                
                company_id = session["company_id"]
                
                # Calculate effectiveness (90 day window for better data)
                effectiveness = await coaching_service.get_coach_effectiveness(
                    coach_id=coach_id,
                    company_id=company_id,
                    timeframe_days=90
                )
                
                # Store in database
                effectiveness_doc = effectiveness.model_dump()
                effectiveness_doc["calculated_at"] = datetime.utcnow()
                effectiveness_doc["period_type"] = "weekly"
                
                await db.coach_effectiveness.update_one(
                    {"coach_id": coach_id, "company_id": company_id},
                    {"$set": effectiveness_doc},
                    upsert=True
                )
                
                calculated += 1
                logger.info(f"Calculated effectiveness for coach {coach_id}: {effectiveness.improvement_rate:.1%} improvement rate")
                
            except Exception as e:
                logger.error(f"Error calculating effectiveness for coach {coach_id}: {e}")
                errors += 1
        
        logger.info(f"Weekly effectiveness calculation complete: {calculated} calculated, {errors} errors")
        
    except Exception as e:
        logger.error(f"Weekly coach effectiveness calculation failed: {e}", exc_info=True)
