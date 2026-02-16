"""
MongoDB Index Creation Script

Creates all necessary indexes for the new features:
- Feature 1: Lead Scoring
- Feature 2: SOP Versioning
- Feature 3: Coaching
- Feature 4: Agent Progression
- Feature 5: Phase Detection
"""

import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


async def create_indexes():
    """Create all MongoDB indexes."""
    
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    logger.info("Creating MongoDB indexes...")
    
    # =========================================================================
    # FEATURE 1: Lead Scoring Indexes
    # =========================================================================
    logger.info("Creating Lead Scoring indexes...")
    
    # Index for lead band queries
    await db.call_summaries.create_index(
        [("lead_score.lead_band", ASCENDING), ("company_id", ASCENDING)],
        name="lead_band_company_idx"
    )
    
    # Index for lead score range queries
    await db.call_summaries.create_index(
        [("lead_score.total_score", DESCENDING), ("company_id", ASCENDING)],
        name="lead_score_company_idx"
    )
    
    # Index for customer lead history
    await db.call_summaries.create_index(
        [("qualification.customer_phone", ASCENDING), ("created_at", DESCENDING)],
        name="customer_lead_history_idx"
    )
    
    logger.info("Lead Scoring indexes created")
    
    # =========================================================================
    # FEATURE 2: SOP Versioning Indexes
    # =========================================================================
    logger.info("Creating SOP Versioning indexes...")
    
    # Index for version history queries
    await db.sop_version_history.create_index(
        [("sop_id", ASCENDING), ("version", DESCENDING)],
        name="sop_version_idx"
    )
    
    # Index for active version lookup
    await db.sop_version_history.create_index(
        [("sop_id", ASCENDING), ("status", ASCENDING)],
        name="sop_active_version_idx"
    )
    
    # Index for scheduled activations
    await db.sop_version_history.create_index(
        [("status", ASCENDING), ("activation_date", ASCENDING)],
        name="scheduled_activation_idx"
    )
    
    # Index for file hash duplicate checking
    await db.sop_version_history.create_index(
        [("sop_id", ASCENDING), ("file_hash", ASCENDING)],
        name="sop_file_hash_idx"
    )
    
    # Index for reanalysis jobs
    await db.reanalysis_jobs.create_index(
        [("sop_id", ASCENDING), ("status", ASCENDING)],
        name="reanalysis_job_status_idx"
    )
    
    # Index for call reanalysis lookup
    await db.call_reanalysis.create_index(
        [("call_id", ASCENDING), ("sop_id", ASCENDING)],
        name="call_reanalysis_lookup_idx"
    )
    
    logger.info("SOP Versioning indexes created")
    
    # =========================================================================
    # FEATURE 3: Coaching Indexes
    # =========================================================================
    logger.info("Creating Coaching indexes...")
    
    # Index for sessions by rep
    await db.coaching_sessions.create_index(
        [("company_id", ASCENDING), ("rep_id", ASCENDING), ("coached_at", DESCENDING)],
        name="coaching_sessions_rep_idx"
    )
    
    # Index for sessions by coach
    await db.coaching_sessions.create_index(
        [("company_id", ASCENDING), ("coach_id", ASCENDING), ("coached_at", DESCENDING)],
        name="coaching_sessions_coach_idx"
    )
    
    # Index for follow-up checks
    await db.coaching_sessions.create_index(
        [("status", ASCENDING), ("follow_up_end_date", ASCENDING)],
        name="coaching_follow_up_idx"
    )
    
    # Index for impact queries
    await db.coaching_sessions.create_index(
        [("company_id", ASCENDING), ("status", ASCENDING), ("impact.overall_improved", ASCENDING)],
        name="coaching_impact_idx"
    )
    
    # Index for coach effectiveness aggregation
    await db.coach_effectiveness.create_index(
        [("coach_id", ASCENDING), ("period_type", ASCENDING), ("period_start", DESCENDING)],
        name="coach_effectiveness_period_idx"
    )
    
    logger.info("Coaching indexes created")
    
    # =========================================================================
    # FEATURE 4: Agent Progression Indexes
    # =========================================================================
    logger.info("Creating Agent Progression indexes...")
    
    # Index for rep call queries
    await db.calls.create_index(
        [("company_id", ASCENDING), ("metadata.rep_id", ASCENDING), ("call_date", DESCENDING)],
        name="rep_calls_idx"
    )
    
    # Index for weekly aggregation
    await db.calls.create_index(
        [("company_id", ASCENDING), ("status", ASCENDING), ("call_date", ASCENDING)],
        name="weekly_metrics_idx"
    )
    
    logger.info("Agent Progression indexes created")
    
    # =========================================================================
    # FEATURE 5: Phase Detection Indexes
    # =========================================================================
    logger.info("Creating Phase Detection indexes...")
    
    # Index for phase presence queries
    await db.call_phases.create_index(
        [("company_id", ASCENDING), ("processed_at", DESCENDING)],
        name="call_phases_company_idx"
    )
    
    # Index for missing phase queries
    await db.call_phases.create_index(
        [("company_id", ASCENDING), ("missing_phases", ASCENDING)],
        name="missing_phases_idx"
    )
    
    # Index for phase detection status
    await db.call_phases.create_index(
        [("call_id", ASCENDING)],
        name="call_phases_call_idx",
        unique=True
    )
    
    # Index for phase-specific searches
    for phase in ["greeting", "problem_discovery", "qualification", 
                  "objection_handling", "closing", "post_close"]:
        await db.call_phases.create_index(
            [("company_id", ASCENDING), (f"phases.{phase}.detected", ASCENDING)],
            name=f"phase_{phase}_idx"
        )
    
    logger.info("Phase Detection indexes created")
    
    # =========================================================================
    # Verify indexes
    # =========================================================================
    logger.info("\n=== INDEX VERIFICATION ===")
    
    collections = ["call_summaries", "sop_version_history", "reanalysis_jobs", 
                   "call_reanalysis", "coaching_sessions", "coach_effectiveness",
                   "calls", "call_phases"]
    
    for collection in collections:
        indexes = await db[collection].index_information()
        logger.info(f"\n{collection}: {len(indexes)} indexes")
        for name, info in indexes.items():
            logger.info(f"  - {name}: {info.get('key', '')}")
    
    logger.info("\n=== ALL INDEXES CREATED SUCCESSFULLY ===")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(create_indexes())
