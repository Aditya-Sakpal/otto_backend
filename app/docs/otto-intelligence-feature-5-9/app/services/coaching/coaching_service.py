"""
Coaching Service

Manages coaching sessions and impact measurement.

Based on manager decisions Q10-Q24:
- Q14: 10 calls total (5 baseline, 5 validation)
- Q15: Minimum 5 calls for baseline
- Q16: Proceed with low-confidence flag if insufficient data
- Q17: Exclude outliers (top/bottom 10%)
- Q19: 2 week follow-up period (default)
- Q20: Automatic impact measurement on follow-up end
- Q21: Extend 1 week if insufficient follow-up calls, then flag
- Q22: Meaningful improvement = positive change + improving trend
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from statistics import mean, stdev

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.coaching import (
    CoachingSession, CoachingBaseline, CoachingImpact,
    ImprovementMetric, CoachEffectiveness, SkillEffectiveness,
    CoachingROISummary
)


logger = logging.getLogger(__name__)


class CoachingService:
    """Manage coaching sessions and impact measurement"""
    
    # Configuration (per manager decisions)
    MIN_CALLS_FOR_BASELINE = 5      # Q15
    MIN_CALLS_FOR_VALIDATION = 5    # Q14 (10 total - 5 baseline - 5 validation)
    DEFAULT_FOLLOW_UP_DAYS = 14     # Q19
    EXTENSION_DAYS = 7              # Q21
    MAX_EXTENSIONS = 1              # Q21: Extend once, then flag
    OUTLIER_PERCENTILE = 0.10       # Q17: Remove top/bottom 10%
    IMPROVEMENT_THRESHOLD = 0.05    # Q22: 5% = meaningful improvement
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.coaching_sessions = db.coaching_sessions
        self.coach_effectiveness = db.coach_effectiveness
        self.call_summaries = db.call_summaries
        self.calls = db.calls
    
    async def create_session(
        self,
        company_id: str,
        rep_id: str,
        rep_name: str,
        coach_id: str,
        coach_name: str,
        focus_areas: List[str],
        targets: Dict[str, float],
        triggering_call_ids: List[str] = None,
        follow_up_days: int = None,
        notes: str = None
    ) -> CoachingSession:
        """
        Create new coaching session.
        
        Process:
        1. Auto-calculate baseline from last 5 calls
        2. Set follow-up end date
        3. Store session
        
        Args:
            company_id: Company identifier
            rep_id: Rep being coached
            rep_name: Rep name
            coach_id: Coach/manager ID
            coach_name: Coach name
            focus_areas: Skills to improve
            targets: Manager-defined targets (metric -> target score)
            triggering_call_ids: Calls that led to this coaching
            follow_up_days: Follow-up period (default 14)
            notes: Coach notes
            
        Returns:
            Created CoachingSession
        """
        session_id = f"coach_{uuid.uuid4().hex[:12]}"
        
        if follow_up_days is None:
            follow_up_days = self.DEFAULT_FOLLOW_UP_DAYS
        
        # Calculate baseline from last 5 calls
        baseline = await self.calculate_baseline(
            rep_id=rep_id,
            company_id=company_id,
            focus_areas=focus_areas,
            num_calls=self.MIN_CALLS_FOR_BASELINE,
            exclude_outliers=True
        )
        
        # Calculate follow-up end date
        coached_at = datetime.utcnow()
        follow_up_end = coached_at + timedelta(days=follow_up_days)
        
        # Create session
        session = CoachingSession(
            session_id=session_id,
            company_id=company_id,
            rep_id=rep_id,
            rep_name=rep_name,
            coach_id=coach_id,
            coach_name=coach_name,
            coached_at=coached_at,
            focus_areas=focus_areas,
            triggering_call_ids=triggering_call_ids or [],
            notes=notes,
            targets=targets,
            baseline=baseline,
            follow_up_period_days=follow_up_days,
            follow_up_end_date=follow_up_end,
            status="in_progress",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Store in database
        await self.coaching_sessions.insert_one(session.model_dump(by_alias=True))
        
        logger.info(f"Created coaching session {session_id} for rep {rep_id} by coach {coach_id}")
        
        return session
    
    async def calculate_baseline(
        self,
        rep_id: str,
        company_id: str,
        focus_areas: List[str],
        num_calls: int = 5,
        exclude_outliers: bool = True,
        before_date: datetime = None
    ) -> CoachingBaseline:
        """
        Calculate baseline scores (per Q14-Q17).
        
        Process:
        1. Get last N calls for rep
        2. Extract scores for focus areas
        3. Remove outliers (top/bottom 10%)
        4. Calculate averages
        5. Flag confidence level
        
        Args:
            rep_id: Representative ID
            company_id: Company ID
            focus_areas: Skills to measure
            num_calls: Number of calls to use
            exclude_outliers: Whether to remove outliers
            before_date: Only consider calls before this date
            
        Returns:
            CoachingBaseline with scores and confidence
        """
        if before_date is None:
            before_date = datetime.utcnow()
        
        # Query calls for this rep
        # First get calls to find call_ids
        query = {
            "company_id": company_id,
            "status": "completed",
            "call_date": {"$lt": before_date}
        }
        
        # Get call IDs for this rep (from metadata or separate collection)
        calls_cursor = self.calls.find(query).sort("call_date", -1).limit(num_calls * 2)
        calls = await calls_cursor.to_list(length=num_calls * 2)
        
        # Filter by rep - check metadata for rep_id or rep_name
        rep_call_ids = []
        for call in calls:
            metadata = call.get("metadata", {})
            call_rep_id = metadata.get("rep_id") or metadata.get("rep_name", "").lower().replace(" ", "_")
            if call_rep_id == rep_id or rep_id in str(metadata):
                rep_call_ids.append(call["call_id"])
                if len(rep_call_ids) >= num_calls:
                    break
        
        if not rep_call_ids:
            logger.warning(f"No calls found for rep {rep_id}")
            return CoachingBaseline(
                calculated_at=datetime.utcnow(),
                calls_analyzed=0,
                call_ids=[],
                scores={area: 0.5 for area in focus_areas},
                confidence="low",
                outliers_removed=0
            )
        
        # Get summaries for these calls
        summaries_cursor = self.call_summaries.find({"call_id": {"$in": rep_call_ids}})
        summaries = await summaries_cursor.to_list(length=num_calls)
        
        # Extract scores for each focus area
        scores_by_area: Dict[str, List[float]] = {area: [] for area in focus_areas}
        call_ids_used = []
        
        for summary in summaries:
            call_id = summary["call_id"]
            call_ids_used.append(call_id)
            
            # Extract relevant scores based on focus areas
            for area in focus_areas:
                score = self._extract_score_for_area(summary, area)
                if score is not None:
                    scores_by_area[area].append(score)
        
        # Remove outliers if requested
        outliers_removed = 0
        if exclude_outliers and len(call_ids_used) >= 5:
            for area in focus_areas:
                scores = scores_by_area[area]
                if len(scores) >= 5:
                    original_count = len(scores)
                    scores_by_area[area] = self._remove_outliers(scores)
                    outliers_removed += original_count - len(scores_by_area[area])
        
        # Calculate averages
        final_scores = {}
        for area in focus_areas:
            scores = scores_by_area[area]
            if scores:
                final_scores[area] = mean(scores)
            else:
                final_scores[area] = 0.5  # Default neutral
        
        # Determine confidence (per Q16)
        confidence = "high" if len(call_ids_used) >= self.MIN_CALLS_FOR_BASELINE else "low"
        
        return CoachingBaseline(
            calculated_at=datetime.utcnow(),
            calls_analyzed=len(call_ids_used),
            call_ids=call_ids_used,
            scores=final_scores,
            confidence=confidence,
            outliers_removed=outliers_removed
        )
    
    def _extract_score_for_area(self, summary: dict, area: str) -> Optional[float]:
        """Extract score for a specific focus area from call summary."""
        # Map focus areas to summary fields
        area_mappings = {
            # Compliance-related
            "compliance_score": lambda s: s.get("compliance", {}).get("sop_compliance", {}).get("score"),
            "sop_compliance": lambda s: s.get("compliance", {}).get("sop_compliance", {}).get("score"),
            
            # Qualification-related
            "needs_assessment": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("need"),
            "need_discovery": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("need"),
            "budget_qualification": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("budget"),
            "timeline_qualification": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("timeline"),
            "authority_qualification": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("authority"),
            "overall_qualification": lambda s: s.get("qualification", {}).get("overall_score"),
            
            # Objection handling
            "objection_handling": lambda s: self._calculate_objection_handling_score(s),
            
            # Booking
            "booking_rate": lambda s: 1.0 if s.get("qualification", {}).get("booking_status") == "booked" else 0.0,
            
            # Sentiment
            "customer_sentiment": lambda s: s.get("summary", {}).get("sentiment_score"),
            
            # Lead scoring
            "lead_score": lambda s: (s.get("lead_score", {}).get("total_score", 50) / 100) if s.get("lead_score") else None
        }
        
        # Normalize area name
        area_lower = area.lower().replace(" ", "_").replace("-", "_")
        
        # Try to find matching extractor
        for key, extractor in area_mappings.items():
            if key in area_lower or area_lower in key:
                try:
                    return extractor(summary)
                except:
                    pass
        
        # Fallback: try to find in compliance stages
        compliance = summary.get("compliance", {}).get("sop_compliance", {})
        stages = compliance.get("stages", {})
        if area_lower in str(stages).lower():
            followed = stages.get("followed", [])
            if area in followed or any(area_lower in f.lower() for f in followed):
                return 1.0
            missed = stages.get("missed", [])
            if area in missed or any(area_lower in m.lower() for m in missed):
                return 0.0
        
        return None
    
    def _calculate_objection_handling_score(self, summary: dict) -> Optional[float]:
        """Calculate objection handling score based on overcome rate."""
        objections = summary.get("objections", {}).get("objections", [])
        if not objections:
            return None  # No objections to handle
        
        overcome_count = sum(1 for obj in objections if obj.get("overcome", False))
        return overcome_count / len(objections)
    
    def _remove_outliers(self, scores: List[float]) -> List[float]:
        """Remove top and bottom 10% outliers (per Q17)."""
        if len(scores) < 5:
            return scores
        
        sorted_scores = sorted(scores)
        cutoff = int(len(sorted_scores) * self.OUTLIER_PERCENTILE)
        
        if cutoff == 0:
            cutoff = 1
        
        return sorted_scores[cutoff:-cutoff] if cutoff < len(sorted_scores) // 2 else sorted_scores
    
    async def measure_impact(
        self,
        session_id: str
    ) -> CoachingImpact:
        """
        Measure coaching impact (per Q20-Q22).
        
        Process:
        1. Get calls since coaching date
        2. Calculate current scores
        3. Compare to baseline
        4. Determine trend direction
        5. Check if targets met
        
        Args:
            session_id: Coaching session ID
            
        Returns:
            CoachingImpact with comparison results
        """
        # Get session
        session_doc = await self.coaching_sessions.find_one({"session_id": session_id})
        if not session_doc:
            raise ValueError(f"Session {session_id} not found")
        
        session = CoachingSession(**session_doc)
        
        # Get calls since coaching date
        query = {
            "company_id": session.company_id,
            "status": "completed",
            "call_date": {"$gt": session.coached_at}
        }
        
        calls_cursor = self.calls.find(query).sort("call_date", -1).limit(20)
        calls = await calls_cursor.to_list(length=20)
        
        # Filter by rep
        rep_call_ids = []
        for call in calls:
            metadata = call.get("metadata", {})
            call_rep_id = metadata.get("rep_id") or metadata.get("rep_name", "").lower().replace(" ", "_")
            if call_rep_id == session.rep_id or session.rep_id in str(metadata):
                rep_call_ids.append(call["call_id"])
        
        if len(rep_call_ids) < self.MIN_CALLS_FOR_VALIDATION:
            logger.warning(f"Only {len(rep_call_ids)} calls found for validation (need {self.MIN_CALLS_FOR_VALIDATION})")
        
        # Handle case when NO post-coaching calls exist
        # Don't compare against default values - return "awaiting_data" state
        if len(rep_call_ids) == 0:
            logger.info(f"No post-coaching calls found for session {session_id} - awaiting data")
            baseline_scores = session.baseline.scores if session.baseline else {}
            
            # Return baseline as current (no change) with awaiting_data status
            improvements = {}
            targets_met = {}
            for area in session.focus_areas:
                baseline = baseline_scores.get(area, 0)
                target = session.targets.get(area)
                
                improvements[area] = ImprovementMetric(
                    metric_name=area,
                    baseline_score=baseline,
                    current_score=None,  # No data yet
                    absolute_change=0,
                    percentage_change=0,
                    target=target,
                    target_met=False,
                    trend="awaiting_data"  # Clear indicator that we can't measure yet
                )
                targets_met[area] = False
            
            return CoachingImpact(
                measured_at=datetime.utcnow(),
                calls_analyzed=0,
                call_ids=[],
                scores={},  # Empty - no data
                improvements={k: v.model_dump() for k, v in improvements.items()},
                overall_improved=False,
                trend_direction="awaiting_data",  # Clear indicator
                targets_met=targets_met,
                confidence="none"  # No confidence without data
            )
        
        # Get summaries
        summaries_cursor = self.call_summaries.find({"call_id": {"$in": rep_call_ids}})
        summaries = await summaries_cursor.to_list(length=20)
        
        # Extract current scores
        scores_by_area: Dict[str, List[float]] = {area: [] for area in session.focus_areas}
        
        for summary in summaries:
            for area in session.focus_areas:
                score = self._extract_score_for_area(summary, area)
                if score is not None:
                    scores_by_area[area].append(score)
        
        # Calculate current averages - only use real data, don't default to 0.5
        current_scores = {}
        has_any_scores = False
        for area in session.focus_areas:
            scores = scores_by_area[area]
            if scores:
                current_scores[area] = mean(scores)
                has_any_scores = True
            else:
                current_scores[area] = None  # No data for this area
        
        # Calculate improvements
        baseline_scores = session.baseline.scores if session.baseline else {}
        improvements = {}
        targets_met = {}
        overall_improved = False
        total_change = 0
        areas_with_data = 0
        
        for area in session.focus_areas:
            baseline = baseline_scores.get(area, 0)
            current = current_scores.get(area)
            target = session.targets.get(area)
            
            # Only calculate change if we have current data
            if current is not None:
                absolute_change = current - baseline
                percentage_change = (absolute_change / baseline * 100) if baseline > 0 else 0
                areas_with_data += 1
                total_change += absolute_change
                
                # Determine trend
                if absolute_change >= self.IMPROVEMENT_THRESHOLD:
                    trend = "improving"
                    overall_improved = True
                elif absolute_change <= -self.IMPROVEMENT_THRESHOLD:
                    trend = "declining"
                else:
                    trend = "stable"
                
                # Check target
                target_met = current >= target if target else False
            else:
                # No data for this area
                absolute_change = 0
                percentage_change = 0
                trend = "awaiting_data"
                target_met = False
            
            targets_met[area] = target_met
            
            improvements[area] = ImprovementMetric(
                metric_name=area,
                baseline_score=baseline,
                current_score=current,
                absolute_change=absolute_change,
                percentage_change=percentage_change,
                target=target,
                target_met=target_met,
                trend=trend
            )
        
        # Overall trend - only calculate if we have data
        if areas_with_data > 0:
            avg_change = total_change / areas_with_data
            if avg_change >= self.IMPROVEMENT_THRESHOLD:
                trend_direction = "improving"
            elif avg_change <= -self.IMPROVEMENT_THRESHOLD:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "awaiting_data"
        
        # Confidence
        if len(rep_call_ids) >= self.MIN_CALLS_FOR_VALIDATION:
            confidence = "high"
        elif len(rep_call_ids) > 0:
            confidence = "low"
        else:
            confidence = "none"
        
        return CoachingImpact(
            measured_at=datetime.utcnow(),
            calls_analyzed=len(rep_call_ids),
            call_ids=rep_call_ids,
            scores={k: v for k, v in current_scores.items() if v is not None},
            improvements={k: v.model_dump() for k, v in improvements.items()},
            overall_improved=overall_improved,
            trend_direction=trend_direction,
            targets_met=targets_met,
            confidence=confidence
        )
    
    async def check_and_complete_session(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Check if session is ready for completion and complete it (per Q20-Q21).
        
        Called by daily background job.
        
        Logic:
        - If follow_up_end_date <= now AND status = "in_progress":
            - Measure impact
            - If insufficient calls AND not yet extended: extend by 7 days
            - If already extended: mark as "insufficient_data"
            - Otherwise: mark as "completed"
        """
        session_doc = await self.coaching_sessions.find_one({"session_id": session_id})
        if not session_doc:
            return {"error": "Session not found"}
        
        session = CoachingSession(**session_doc)
        
        if session.status != "in_progress":
            return {"status": session.status, "message": "Session not in progress"}
        
        # Measure impact
        impact = await self.measure_impact(session_id)
        
        # Determine next action
        if impact.calls_analyzed < self.MIN_CALLS_FOR_VALIDATION:
            # Insufficient calls
            if session.extended_count < self.MAX_EXTENSIONS:
                # Extend (per Q21)
                new_end_date = session.follow_up_end_date + timedelta(days=self.EXTENSION_DAYS)
                await self.coaching_sessions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "follow_up_end_date": new_end_date,
                            "extended_count": session.extended_count + 1,
                            "status": "extended",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                return {
                    "status": "extended",
                    "message": f"Extended by {self.EXTENSION_DAYS} days due to insufficient calls",
                    "new_end_date": new_end_date
                }
            else:
                # Already extended, flag as insufficient
                await self.coaching_sessions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "insufficient_data",
                            "impact": impact.model_dump(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                await self.refresh_coach_effectiveness_cache(session.coach_id, session.company_id)
                return {
                    "status": "insufficient_data",
                    "message": "Insufficient follow-up calls after extension",
                    "impact": impact.model_dump()
                }
        
        # Sufficient calls - complete session
        await self.coaching_sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "completed",
                    "impact": impact.model_dump(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        await self.refresh_coach_effectiveness_cache(session.coach_id, session.company_id)
        
        return {
            "status": "completed",
            "message": "Session completed with impact measurement",
            "impact": impact.model_dump()
        }
    
    async def get_coach_effectiveness(
        self,
        coach_id: str,
        company_id: str,
        timeframe_days: int = 90,
        use_cached: bool = False
    ) -> CoachEffectiveness:
        """
        Calculate coach effectiveness metrics (per Q23-Q24).
        
        Args:
            coach_id: Coach identifier
            company_id: Company identifier
            timeframe_days: Period to analyze
            use_cached: If True, return from coach_effectiveness collection when available (within last 8 days)
            
        Returns:
            CoachEffectiveness with aggregated metrics
        """
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=timeframe_days)
        
        # Optional: read from coach_effectiveness cache (populated by scheduler and by session completion)
        if use_cached:
            cached = await self.coach_effectiveness.find_one(
                {
                    "coach_id": coach_id,
                    "company_id": company_id,
                    "calculated_at": {"$gte": period_end - timedelta(days=8)}
                },
                sort=[("calculated_at", -1)]
            )
            if cached:
                cached.pop("_id", None)
                try:
                    return CoachEffectiveness.model_validate(cached)
                except Exception as e:
                    logger.warning(f"Invalid cached coach_effectiveness for {coach_id}: {e}, computing live")
        
        # Get completed sessions for this coach
        query = {
            "coach_id": coach_id,
            "company_id": company_id,
            "coached_at": {"$gte": period_start, "$lte": period_end},
            "status": {"$in": ["completed", "insufficient_data"]}
        }
        
        cursor = self.coaching_sessions.find(query)
        sessions = await cursor.to_list(length=1000)
        
        if not sessions:
            # Get coach name from any session
            any_session = await self.coaching_sessions.find_one({"coach_id": coach_id})
            coach_name = any_session.get("coach_name", "Unknown") if any_session else "Unknown"
            
            return CoachEffectiveness(
                coach_id=coach_id,
                coach_name=coach_name,
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                total_sessions=0,
                completed_sessions=0,
                reps_coached=0,
                reps_improved=0,
                improvement_rate=0.0,
                avg_improvement_percentage=0.0,
                skill_effectiveness={}
            )
        
        coach_name = sessions[0].get("coach_name", "Unknown")
        
        # Calculate metrics
        total_sessions = len(sessions)
        completed_sessions = sum(1 for s in sessions if s.get("status") == "completed")
        reps_coached = len(set(s["rep_id"] for s in sessions))
        
        # Count improved reps
        improved_count = 0
        total_improvement = 0
        skill_data: Dict[str, Dict] = {}
        
        for session in sessions:
            impact = session.get("impact", {})
            if impact.get("overall_improved"):
                improved_count += 1
            
            # Track per-skill effectiveness
            improvements = impact.get("improvements", {})
            for area, improvement in improvements.items():
                if area not in skill_data:
                    skill_data[area] = {"sessions": 0, "total_improvement": 0, "improved_count": 0}
                
                skill_data[area]["sessions"] += 1
                change = improvement.get("percentage_change", 0) if isinstance(improvement, dict) else 0
                skill_data[area]["total_improvement"] += change
                
                if change > self.IMPROVEMENT_THRESHOLD * 100:
                    skill_data[area]["improved_count"] += 1
            
            total_improvement += sum(
                imp.get("percentage_change", 0) if isinstance(imp, dict) else 0
                for imp in improvements.values()
            )
        
        # Calculate rates
        improvement_rate = improved_count / total_sessions if total_sessions > 0 else 0
        avg_improvement = total_improvement / (total_sessions * len(sessions[0].get("focus_areas", [1]))) if total_sessions > 0 else 0
        
        # Build skill effectiveness
        skill_effectiveness = {}
        best_skill = None
        best_skill_rate = 0
        worst_skill = None
        worst_skill_rate = 1.0
        
        for skill, data in skill_data.items():
            success_rate = data["improved_count"] / data["sessions"] if data["sessions"] > 0 else 0
            avg_imp = data["total_improvement"] / data["sessions"] if data["sessions"] > 0 else 0
            
            skill_effectiveness[skill] = SkillEffectiveness(
                skill_name=skill,
                sessions_count=data["sessions"],
                avg_improvement=avg_imp,
                success_rate=success_rate
            )
            
            if success_rate > best_skill_rate:
                best_skill_rate = success_rate
                best_skill = skill
            
            if success_rate < worst_skill_rate:
                worst_skill_rate = success_rate
                worst_skill = skill
        
        return CoachEffectiveness(
            coach_id=coach_id,
            coach_name=coach_name,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            total_sessions=total_sessions,
            completed_sessions=completed_sessions,
            reps_coached=reps_coached,
            reps_improved=improved_count,
            improvement_rate=improvement_rate,
            avg_improvement_percentage=avg_improvement,
            best_focus_area=best_skill,
            worst_focus_area=worst_skill,
            skill_effectiveness={k: v.model_dump() for k, v in skill_effectiveness.items()}
        )
    
    async def refresh_coach_effectiveness_cache(
        self,
        coach_id: str,
        company_id: str,
        timeframe_days: int = 90
    ) -> None:
        """
        Recompute and upsert coach effectiveness into coach_effectiveness collection.
        Call when a session is completed (via PATCH or daily job) so cached GET is up to date.
        """
        try:
            effectiveness = await self.get_coach_effectiveness(
                coach_id=coach_id,
                company_id=company_id,
                timeframe_days=timeframe_days,
                use_cached=False
            )
            doc = effectiveness.model_dump()
            doc["calculated_at"] = datetime.utcnow()
            doc["period_type"] = "weekly"
            await self.coach_effectiveness.update_one(
                {"coach_id": coach_id, "company_id": company_id},
                {"$set": doc},
                upsert=True
            )
            logger.info(f"Refreshed coach_effectiveness cache for coach_id={coach_id}")
        except Exception as e:
            logger.warning(f"Failed to refresh coach_effectiveness cache for {coach_id}: {e}")
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get coaching session by ID."""
        session = await self.coaching_sessions.find_one({"session_id": session_id})
        if session:
            session.pop("_id", None)
        return session
    
    async def list_sessions(
        self,
        company_id: str,
        rep_id: Optional[str] = None,
        coach_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List coaching sessions with filters."""
        query = {"company_id": company_id}
        
        if rep_id:
            query["rep_id"] = rep_id
        if coach_id:
            query["coach_id"] = coach_id
        if status:
            query["status"] = status
        
        total = await self.coaching_sessions.count_documents(query)
        
        cursor = self.coaching_sessions.find(query).sort("coached_at", -1).skip(offset).limit(limit)
        sessions = await cursor.to_list(length=limit)
        
        for s in sessions:
            s.pop("_id", None)
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "sessions": sessions
        }


# Singleton
_coaching_service: Optional[CoachingService] = None


def get_coaching_service(db: AsyncIOMotorDatabase) -> CoachingService:
    """Get CoachingService instance"""
    global _coaching_service
    if _coaching_service is None:
        _coaching_service = CoachingService(db)
    return _coaching_service
