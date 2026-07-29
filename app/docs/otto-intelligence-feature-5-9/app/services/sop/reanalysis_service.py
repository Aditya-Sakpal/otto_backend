"""
SOP Reanalysis Service

Handles call re-analysis with new SOP versions.

Per manager decisions:
- Q5: No automatic re-analysis (manual trigger only)
- Q6: Default lookback period is configurable (see settings.SOP_REANALYSIS_DEFAULT_LOOKBACK_DAYS)
- Q7: Re-analyze ALL calls in selected period (not just failures)
- Q8: Store both original + re-analyzed evaluations
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.sop import CallReanalysis, ReanalysisJob, SOPMetric
from app.services.sop.evaluation_service import EvaluationService
from app.config import get_settings


logger = logging.getLogger(__name__)


class SOPReanalysisService:
    """Handle call re-analysis with new SOP versions"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.calls = db.calls
        self.call_summaries = db.call_summaries
        self.call_reanalysis = db.call_reanalysis
        self.reanalysis_jobs = db.reanalysis_jobs
        self.sop_version_history = db.sop_version_history
        self.evaluation_service = EvaluationService()
        self.settings = get_settings()
    
    @property
    def DEFAULT_LOOKBACK_DAYS(self) -> int:
        """Get default lookback days from settings"""
        return self.settings.SOP_REANALYSIS_DEFAULT_LOOKBACK_DAYS
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.calls = db.calls
        self.call_summaries = db.call_summaries
        self.call_reanalysis = db.call_reanalysis
        self.reanalysis_jobs = db.reanalysis_jobs
        self.sop_version_history = db.sop_version_history
        self.evaluation_service = EvaluationService()
    
    async def trigger_reanalysis(
        self,
        sop_id: str,
        company_id: str,
        lookback_days: int = None,
        new_sop_version: int = None
    ) -> str:
        """
        Trigger re-analysis of calls with new SOP version (per Q5-Q8).
        
        Process:
        1. Query all calls in lookback period
        2. Create reanalysis job
        3. Return job_id for status tracking
        
        Note: Actual re-analysis happens in background task.
        
        Args:
            sop_id: SOP document ID
            company_id: Company identifier
            lookback_days: How many days back to analyze (default: from settings)
            new_sop_version: Version to use for re-analysis
            
        Returns:
            job_id for tracking progress
        """
        if lookback_days is None:
            lookback_days = self.DEFAULT_LOOKBACK_DAYS
        
        # Get the latest version if not specified
        if new_sop_version is None:
            version_doc = await self.sop_version_history.find_one(
                {"sop_id": sop_id, "status": "active"},
                sort=[("version", -1)]
            )
            if version_doc:
                new_sop_version = version_doc["version"]
            else:
                raise ValueError(f"No active version found for SOP {sop_id}")
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)
        
        # Count calls to reanalyze (per Q7: ALL calls, not just failures)
        call_count = await self.calls.count_documents({
            "company_id": company_id,
            "call_date": {"$gte": start_date, "$lte": end_date},
            "status": "completed"
        })
        
        if call_count == 0:
            raise ValueError(f"No calls found in lookback period ({lookback_days} days)")
        
        # Create job record
        job_id = str(uuid.uuid4())
        job = ReanalysisJob(
            job_id=job_id,
            sop_id=sop_id,
            company_id=company_id,
            new_sop_version=new_sop_version,
            lookback_days=lookback_days,
            status="queued",
            total_calls=call_count,
            processed_calls=0,
            failed_calls=0,
            created_at=datetime.utcnow()
        )
        
        await self.reanalysis_jobs.insert_one(job.model_dump(by_alias=True))
        
        logger.info(f"Created reanalysis job {job_id} for SOP {sop_id}: {call_count} calls to process")
        
        return job_id
    
    async def process_reanalysis_job(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """
        Process a reanalysis job (called by background task).
        
        For each call:
        1. Get original evaluation
        2. Re-evaluate with new SOP version
        3. Store both in call_reanalysis collection
        4. Update progress
        
        Args:
            job_id: Reanalysis job ID
            
        Returns:
            Job result summary
        """
        # Get job
        job_doc = await self.reanalysis_jobs.find_one({"job_id": job_id})
        if not job_doc:
            raise ValueError(f"Job {job_id} not found")
        
        sop_id = job_doc["sop_id"]
        company_id = job_doc["company_id"]
        new_sop_version = job_doc["new_sop_version"]
        lookback_days = job_doc["lookback_days"]
        
        # Update status to processing
        await self.reanalysis_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "processing",
                    "started_at": datetime.utcnow()
                }
            }
        )
        
        # Get new SOP metrics
        version_doc = await self.sop_version_history.find_one({
            "sop_id": sop_id,
            "version": new_sop_version
        })
        
        if not version_doc:
            await self._fail_job(job_id, f"Version {new_sop_version} not found for SOP {sop_id}")
            raise ValueError(f"Version not found")
        
        new_metrics = [SOPMetric(**m) for m in version_doc.get("metrics_snapshot", [])]
        new_version_history_id = version_doc["history_id"]
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)
        
        # Get calls to reanalyze
        cursor = self.calls.find({
            "company_id": company_id,
            "call_date": {"$gte": start_date, "$lte": end_date},
            "status": "completed"
        })
        
        calls = await cursor.to_list(length=10000)  # Reasonable limit
        
        # Process each call
        processed = 0
        failed = 0
        improved = 0
        declined = 0
        unchanged = 0
        skipped = 0  # Calls already evaluated with current version
        skipped_call_ids = []  # Track which calls were skipped
        score_changes = []
        old_scores = []  # Track original scores for averaging
        new_scores = []  # Track new scores for averaging
        metric_changes_agg = {}  # Track per-metric changes: {metric_id: {"changes": [], "name": ""}}
        
        for call in calls:
            call_id = call["call_id"]
            
            try:
                # Check if this call was already evaluated with the current SOP version
                summary_doc = await self.call_summaries.find_one({"call_id": call_id})
                
                if summary_doc:
                    # SOP version info is stored in compliance.sop_compliance (not sop_evaluation)
                    compliance = summary_doc.get("compliance", {})
                    sop_compliance = compliance.get("sop_compliance", {})
                    evaluated_version = sop_compliance.get("sop_version")
                    evaluated_history_id = sop_compliance.get("sop_version_history_id")
                    
                    # Skip if already evaluated against THIS SOP version
                    # Use sop_version_history_id as the definitive match (it's unique per SOP version)
                    if (evaluated_history_id == new_version_history_id or 
                        evaluated_version == new_sop_version):
                        logger.info(
                            f"Skipping call {call_id}: already evaluated with "
                            f"version={evaluated_version}, history_id={evaluated_history_id}"
                        )
                        skipped += 1
                        skipped_call_ids.append(call_id)
                        continue
                
                # Proceed with reanalysis
                result = await self.reanalyze_single_call(
                    call_id=call_id,
                    company_id=company_id,
                    new_sop_version=new_sop_version,
                    new_version_history_id=new_version_history_id,
                    new_metrics=new_metrics
                )
                
                processed += 1
                score_changes.append(result.score_delta)
                old_scores.append(result.original_overall_score)
                new_scores.append(result.new_overall_score)
                
                # Track per-metric changes for aggregation
                # Get metric scores from the stored reanalysis result
                reanalysis_doc = await self.call_reanalysis.find_one({
                    "reanalysis_id": result.reanalysis_id
                })
                if reanalysis_doc:
                    new_compliance = reanalysis_doc.get("new_compliance", {})
                    original_compliance = reanalysis_doc.get("original_compliance", {})
                    
                    # Get original metric scores - old format doesn't have per-metric scores,
                    # so we'll use 0 as baseline for metric-level tracking
                    original_metric_scores = {}
                    
                    # Aggregate per-metric changes
                    for metric_score in new_compliance.get("metric_scores", []):
                        metric_id = metric_score.get("metric_id")
                        metric_name = metric_score.get("metric_name", metric_id)
                        new_m_score = metric_score.get("score")
                        if new_m_score is None:
                            continue
                        
                        old_m_score = original_metric_scores.get(metric_id, 0)
                        change = new_m_score - old_m_score
                        
                        if metric_id not in metric_changes_agg:
                            metric_changes_agg[metric_id] = {
                                "name": metric_name,
                                "changes": [],
                                "old_scores": [],
                                "new_scores": []
                            }
                        metric_changes_agg[metric_id]["changes"].append(change)
                        metric_changes_agg[metric_id]["old_scores"].append(old_m_score)
                        metric_changes_agg[metric_id]["new_scores"].append(new_m_score)
                
                if result.score_delta > 0.02:  # 2% improvement threshold
                    improved += 1
                elif result.score_delta < -0.02:
                    declined += 1
                else:
                    unchanged += 1
                
                # Update progress
                if processed % 10 == 0:
                    await self.reanalysis_jobs.update_one(
                        {"job_id": job_id},
                        {
                            "$set": {
                                "processed_calls": processed,
                                "failed_calls": failed,
                                "skipped_calls": skipped
                            }
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Failed to reanalyze call {call_id}: {e}")
                failed += 1
        
        # Calculate summary statistics
        avg_score_change = sum(score_changes) / len(score_changes) if score_changes else 0
        avg_old_score = sum(old_scores) / len(old_scores) if old_scores else 0
        avg_new_score = sum(new_scores) / len(new_scores) if new_scores else 0
        
        # Calculate per-metric changes summary
        metric_changes = {}
        for metric_id, data in metric_changes_agg.items():
            if data["changes"]:
                avg_change = sum(data["changes"]) / len(data["changes"])
                direction = "improved" if avg_change > 0.02 else ("declined" if avg_change < -0.02 else "stable")
                metric_changes[data["name"]] = {
                    "metric_id": metric_id,
                    "avg_change": round(avg_change * 100, 1),  # Convert to percentage
                    "direction": direction,
                    "avg_old_score": round(sum(data["old_scores"]) / len(data["old_scores"]), 2) if data["old_scores"] else 0,
                    "avg_new_score": round(sum(data["new_scores"]) / len(data["new_scores"]), 2) if data["new_scores"] else 0
                }
        
        # Build results summary
        results_summary = {
            "calls_improved": improved,
            "calls_declined": declined,
            "calls_unchanged": unchanged,
            "avg_score_change": round(avg_score_change * 100, 1),  # Convert to percentage
            "avg_old_score": round(avg_old_score, 2),
            "avg_new_score": round(avg_new_score, 2)
        }
        
        # Update job as completed
        await self.reanalysis_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "processed_calls": processed,
                    "failed_calls": failed,
                    "skipped_calls": skipped,
                    "skipped_call_ids": skipped_call_ids[:100],  # Store up to 100 IDs
                    "skipped_reason": "already_evaluated_with_current_version" if skipped > 0 else None,
                    "avg_score_change": avg_score_change,
                    "avg_old_score": avg_old_score,
                    "avg_new_score": avg_new_score,
                    "calls_improved": improved,
                    "calls_declined": declined,
                    "calls_unchanged": unchanged,
                    "results_summary": results_summary,
                    "metric_changes": metric_changes
                }
            }
        )
        
        logger.info(
            f"Reanalysis job {job_id} completed: {processed} processed, "
            f"{skipped} skipped (already evaluated), "
            f"{improved} improved, {declined} declined, {unchanged} unchanged, "
            f"avg change: {avg_score_change:.2%}, old: {avg_old_score:.2f}, new: {avg_new_score:.2f}"
        )
        
        return {
            "job_id": job_id,
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "improved": improved,
            "declined": declined,
            "unchanged": unchanged,
            "avg_score_change": avg_score_change,
            "avg_old_score": avg_old_score,
            "avg_new_score": avg_new_score,
            "results_summary": results_summary,
            "metric_changes": metric_changes
        }
    
    async def reanalyze_single_call(
        self,
        call_id: str,
        company_id: str,
        new_sop_version: int,
        new_version_history_id: str,
        new_metrics: List[SOPMetric]
    ) -> CallReanalysis:
        """
        Re-analyze a single call with new SOP version.
        
        Per Q8: Store both original and new evaluations.
        
        Args:
            call_id: Call to reanalyze
            company_id: Company identifier
            new_sop_version: New SOP version number
            new_version_history_id: New version history ID
            new_metrics: New SOP metrics to evaluate against
            
        Returns:
            CallReanalysis record with comparison
        """
        # Get call and original summary
        call_doc = await self.calls.find_one({"call_id": call_id})
        if not call_doc:
            raise ValueError(f"Call {call_id} not found")
        
        summary_doc = await self.call_summaries.find_one({"call_id": call_id})
        if not summary_doc:
            raise ValueError(f"Summary for call {call_id} not found")
        
        transcript = call_doc.get("transcript", "")
        
        # Get original evaluation - SOP compliance is stored in compliance.sop_compliance
        original_compliance = summary_doc.get("compliance", {})
        sop_compliance = original_compliance.get("sop_compliance", {})
        
        # Handle None values explicitly - .get() default only applies if key is missing, not if value is None
        original_score = sop_compliance.get("score")
        if original_score is None:
            original_score = 0.5  # Default fallback
        original_sop_version = sop_compliance.get("sop_version", 1)
        original_version_history_id = sop_compliance.get("sop_version_history_id", "")
        
        # Re-evaluate with new metrics
        try:
            new_evaluation = await self.evaluation_service.evaluate_call_against_sop(
                transcript_chunk=transcript,  # Fixed: was 'transcript'
                sop_metrics=new_metrics,      # Fixed: was 'metrics'
                previous_evaluations=None     # Fixed: was 'previous_evaluation', also Fresh evaluation
            )
            
            # Calculate overall_compliance from metric_scores if not present
            # (evaluate_call_against_sop returns metric_scores, not overall_compliance)
            metric_scores = new_evaluation.get("metric_scores", [])
            
            if metric_scores:
                # Calculate weighted average from metric scores
                total_weighted = 0.0
                total_weight = 0.0
                
                for score_entry in metric_scores:
                    if score_entry.get("applicable", True):
                        # Handle None values explicitly
                        score = score_entry.get("score")
                        if score is None:
                            score = 0.0
                        # Find the metric weight
                        metric_id = score_entry.get("metric_id")
                        weight = 1.0  # Default weight
                        for m in new_metrics:
                            if m.metric_id == metric_id:
                                weight = m.weight if m.weight is not None else 1.0
                                break
                        
                        total_weighted += score * weight
                        total_weight += weight
                
                if total_weight > 0:
                    new_score = total_weighted / total_weight
                else:
                    new_score = 0.5  # No applicable metrics
                    logger.warning(f"No applicable metrics for call {call_id}, using default score 0.5")
            else:
                # No metric scores returned - evaluation likely failed
                new_score = original_score  # Keep original to avoid false "decline"
                logger.warning(f"Empty metric_scores for call {call_id}, keeping original score {original_score}")
            
            new_compliance = new_evaluation
            new_compliance["overall_compliance"] = new_score  # Add calculated score
            
        except Exception as e:
            logger.error(f"Re-evaluation failed for call {call_id}: {e}")
            # Re-raise so the outer try-catch can handle it properly
            raise
        
        # Calculate delta and changes
        score_delta = new_score - original_score
        
        # Compare metric scores - note: original compliance may not have metric_scores for old calls
        original_metrics = {}  # Old format doesn't store per-metric scores
        new_metrics_scores = {m.get("metric_id"): m for m in new_evaluation.get("metric_scores", [])}
        
        improved_metrics = []
        declined_metrics = []
        metrics_changed = []
        
        for metric_id in new_metrics_scores.keys():
            # Handle None values - .get() default only applies if key is missing
            new_score_m = new_metrics_scores[metric_id].get("score")
            if new_score_m is None:
                new_score_m = 0.0
            old_score_m = original_metrics.get(metric_id, {}).get("score")
            if old_score_m is None:
                old_score_m = 0.0
            
            if new_score_m > old_score_m + 0.05:
                improved_metrics.append(metric_id)
                metrics_changed.append(metric_id)
            elif new_score_m < old_score_m - 0.05:
                declined_metrics.append(metric_id)
                metrics_changed.append(metric_id)
        
        # Create reanalysis record
        reanalysis_id = f"reanalysis_{uuid.uuid4().hex[:12]}"
        reanalysis = CallReanalysis(
            reanalysis_id=reanalysis_id,
            call_id=call_id,
            company_id=company_id,
            original_sop_version=original_sop_version,
            original_sop_version_history_id=original_version_history_id,
            original_compliance=original_compliance,
            original_overall_score=original_score,
            original_evaluated_at=summary_doc.get("created_at", datetime.utcnow()),
            new_sop_version=new_sop_version,
            new_sop_version_history_id=new_version_history_id,
            new_compliance=new_compliance,
            new_overall_score=new_score,
            reanalyzed_at=datetime.utcnow(),
            score_delta=score_delta,
            metrics_changed=metrics_changed,
            improved_metrics=improved_metrics,
            declined_metrics=declined_metrics
        )
        
        # Store in database (per Q8: store both)
        await self.call_reanalysis.insert_one(reanalysis.model_dump(by_alias=True))
        
        return reanalysis
    
    async def get_reanalysis_results(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """
        Get results of re-analysis job.
        
        Args:
            job_id: Reanalysis job ID
            
        Returns:
            Job status and results
        """
        job_doc = await self.reanalysis_jobs.find_one({"job_id": job_id})
        
        if not job_doc:
            raise ValueError(f"Job {job_id} not found")
        
        job_doc.pop("_id", None)
        
        # If completed, get summary of reanalysis records
        if job_doc.get("status") == "completed":
            # Get distribution of score changes
            pipeline = [
                {
                    "$match": {
                        "company_id": job_doc["company_id"],
                        "new_sop_version": job_doc["new_sop_version"]
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": 1},
                        "avg_delta": {"$avg": "$score_delta"},
                        "max_improvement": {"$max": "$score_delta"},
                        "max_decline": {"$min": "$score_delta"}
                    }
                }
            ]
            
            cursor = self.call_reanalysis.aggregate(pipeline)
            summary = await cursor.to_list(length=1)
            
            if summary:
                job_doc["detailed_results"] = summary[0]
        
        return job_doc
    
    async def get_call_reanalysis_history(
        self,
        call_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all re-analysis records for a specific call.
        
        Useful for seeing how a call's evaluation changed across SOP versions.
        
        Args:
            call_id: Call identifier
            
        Returns:
            List of reanalysis records sorted by date
        """
        cursor = self.call_reanalysis.find(
            {"call_id": call_id}
        ).sort("reanalyzed_at", -1)
        
        records = await cursor.to_list(length=100)
        
        for r in records:
            r.pop("_id", None)
        
        return records
    
    async def _fail_job(self, job_id: str, error: str) -> None:
        """Mark job as failed with error message."""
        await self.reanalysis_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "completed_at": datetime.utcnow(),
                    "error": error
                }
            }
        )


# Singleton
_reanalysis_service: Optional[SOPReanalysisService] = None


def get_reanalysis_service(db: AsyncIOMotorDatabase) -> SOPReanalysisService:
    """Get SOPReanalysisService instance"""
    global _reanalysis_service
    if _reanalysis_service is None:
        _reanalysis_service = SOPReanalysisService(db)
    return _reanalysis_service
