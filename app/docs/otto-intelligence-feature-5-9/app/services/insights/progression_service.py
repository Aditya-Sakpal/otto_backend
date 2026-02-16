"""
Progression Service

Track agent behavior progression over time.

Based on manager decisions Q37-Q48:
- Q37: Weekly granularity only
- Q38: 5 calls minimum per period
- Q39: Show low-confidence trend if insufficient calls
- Q41: ≥5% change = improving/declining
- Q43: ≥15% decline = alert threshold (not in v1.0 per Q47)
- Q44: Flag anomalies only (>20% sudden change)
- Q46: Peer comparison on-demand only
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from statistics import mean, median

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.progression import (
    WeeklyMetrics, TrendResult, Anomaly, MetricProgression,
    AgentProgression, PeerComparison, AgentSummary
)


logger = logging.getLogger(__name__)


class ProgressionService:
    """Track agent behavior progression over time"""
    
    # Configuration (per manager decisions)
    MIN_CALLS_FOR_CONFIDENCE = 5      # Q38
    IMPROVING_THRESHOLD = 0.05        # Q41: 5% improvement
    DECLINING_THRESHOLD = -0.05       # Q41: 5% decline
    ANOMALY_THRESHOLD = 0.20          # Q44: 20% sudden change
    ALERT_THRESHOLD = -0.15           # Q43: 15% decline (deferred per Q47)
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.calls = db.calls
        self.call_summaries = db.call_summaries
    
    async def get_agent_progression(
        self,
        rep_id: str,
        company_id: str,
        metrics: List[str],
        weeks: int = 8
    ) -> AgentProgression:
        """
        Get agent progression data for specified metrics over N weeks.
        
        Args:
            rep_id: Representative identifier
            company_id: Company identifier
            metrics: List of metrics to track (e.g., ["compliance_score", "booking_rate"])
            weeks: Number of weeks to analyze (default 8)
            
        Returns:
            AgentProgression with weekly data, trends, and anomalies
        """
        # Get rep name from any call
        sample_call = await self.calls.find_one({
            "company_id": company_id,
            "metadata.rep_id": rep_id
        })
        rep_name = sample_call.get("metadata", {}).get("rep_name", rep_id) if sample_call else rep_id
        
        # Calculate date range
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(weeks=weeks)
        
        # Calculate metrics for each week
        weekly_data: Dict[str, List[WeeklyMetrics]] = {metric: [] for metric in metrics}
        total_calls = 0
        weeks_with_data = 0
        
        for week_num in range(weeks):
            week_start = period_start + timedelta(weeks=week_num)
            week_end = week_start + timedelta(days=7)
            
            week_metrics = await self.calculate_weekly_metrics(
                rep_id=rep_id,
                company_id=company_id,
                week_start=week_start,
                week_end=week_end,
                metrics=metrics
            )
            
            if week_metrics.calls_analyzed > 0:
                weeks_with_data += 1
                total_calls += week_metrics.calls_analyzed
            
            for metric in metrics:
                weekly_data[metric].append(WeeklyMetrics(
                    week_start=week_start,
                    week_end=week_end,
                    calls_analyzed=week_metrics.calls_analyzed,
                    confidence=week_metrics.confidence,
                    metrics={metric: week_metrics.metrics.get(metric, 0.0)}
                ))
        
        # Calculate trends and anomalies for each metric
        metrics_progression: Dict[str, MetricProgression] = {}
        improving_metrics = []
        declining_metrics = []
        stable_metrics = []
        
        for metric in metrics:
            data_points = weekly_data[metric]
            values = [dp.metrics.get(metric, 0.0) for dp in data_points if dp.calls_analyzed > 0]
            
            # Calculate trend
            trend = self.detect_trend(values)
            
            # Detect anomalies
            anomalies = self.detect_anomalies(
                data_points,
                metric
            )
            
            # Current value and period change
            current_value = values[-1] if values else 0.0
            period_change = values[-1] - values[0] if len(values) >= 2 else 0.0
            period_change_percent = (period_change / values[0] * 100) if values and values[0] > 0 else 0.0
            
            metrics_progression[metric] = MetricProgression(
                metric_name=metric,
                data_points=data_points,
                trend=trend,
                anomalies=anomalies,
                current_value=current_value,
                period_change=period_change,
                period_change_percent=period_change_percent
            )
            
            # Categorize metric
            if trend.direction == "improving":
                improving_metrics.append(metric)
            elif trend.direction == "declining":
                declining_metrics.append(metric)
            else:
                stable_metrics.append(metric)
        
        # Overall confidence
        high_confidence_weeks = sum(
            1 for w in weekly_data[metrics[0]] if w.confidence == "high"
        )
        overall_confidence = "high" if high_confidence_weeks >= weeks // 2 else "low"
        
        return AgentProgression(
            rep_id=rep_id,
            rep_name=rep_name,
            company_id=company_id,
            timeframe_weeks=weeks,
            period_start=period_start,
            period_end=period_end,
            total_calls=total_calls,
            weeks_with_data=weeks_with_data,
            overall_confidence=overall_confidence,
            metrics=metrics_progression,
            improving_metrics=improving_metrics,
            declining_metrics=declining_metrics,
            stable_metrics=stable_metrics
        )
    
    async def calculate_weekly_metrics(
        self,
        rep_id: str,
        company_id: str,
        week_start: datetime,
        week_end: datetime,
        metrics: List[str]
    ) -> WeeklyMetrics:
        """
        Calculate metrics for a single week (per Q37: weekly granularity).
        
        Args:
            rep_id: Representative ID
            company_id: Company ID
            week_start: Start of week
            week_end: End of week
            metrics: List of metrics to calculate
            
        Returns:
            WeeklyMetrics with averages and confidence
        """
        # Query calls for this rep in this week
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "call_date": {"$gte": week_start, "$lt": week_end},
                    "status": "completed",
                    "$or": [
                        {"metadata.rep_id": rep_id},
                        {"metadata.rep_name": {"$regex": rep_id, "$options": "i"}}
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "call_summaries",
                    "localField": "call_id",
                    "foreignField": "call_id",
                    "as": "summary"
                }
            },
            {"$unwind": {"path": "$summary", "preserveNullAndEmptyArrays": True}}
        ]
        
        cursor = self.calls.aggregate(pipeline)
        calls = await cursor.to_list(length=100)
        
        if not calls:
            return WeeklyMetrics(
                week_start=week_start,
                week_end=week_end,
                calls_analyzed=0,
                confidence="low",
                metrics={metric: 0.0 for metric in metrics}
            )
        
        # Extract scores for each metric
        metric_values: Dict[str, List[float]] = {metric: [] for metric in metrics}
        
        for call in calls:
            summary = call.get("summary", {})
            
            for metric in metrics:
                value = self._extract_metric_value(summary, metric)
                if value is not None:
                    metric_values[metric].append(value)
        
        # Calculate averages
        metric_averages = {}
        for metric in metrics:
            values = metric_values[metric]
            metric_averages[metric] = mean(values) if values else 0.0
        
        # Determine confidence (per Q38: 5 calls minimum)
        confidence = "high" if len(calls) >= self.MIN_CALLS_FOR_CONFIDENCE else "low"
        
        return WeeklyMetrics(
            week_start=week_start,
            week_end=week_end,
            calls_analyzed=len(calls),
            confidence=confidence,
            metrics=metric_averages
        )
    
    def _extract_metric_value(self, summary: dict, metric: str) -> Optional[float]:
        """Extract value for a specific metric from call summary."""
        metric_lower = metric.lower().replace(" ", "_").replace("-", "_")
        
        # Metric mappings
        mappings = {
            "compliance_score": lambda s: s.get("compliance", {}).get("sop_compliance", {}).get("score"),
            "sop_compliance": lambda s: s.get("compliance", {}).get("sop_compliance", {}).get("score"),
            "booking_rate": lambda s: 1.0 if s.get("qualification", {}).get("booking_status") == "booked" else 0.0,
            "qualification_score": lambda s: s.get("qualification", {}).get("overall_score"),
            "sentiment_score": lambda s: s.get("summary", {}).get("sentiment_score"),
            "lead_score": lambda s: (s.get("lead_score", {}).get("total_score", 50) / 100) if s.get("lead_score") else None,
            "objection_handling": lambda s: self._calc_objection_rate(s),
            "need_score": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("need"),
            "budget_score": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("budget"),
            "timeline_score": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("timeline"),
            "authority_score": lambda s: s.get("qualification", {}).get("bant_scores", {}).get("authority"),
        }
        
        for key, extractor in mappings.items():
            if key in metric_lower or metric_lower in key:
                try:
                    return extractor(summary)
                except:
                    pass
        
        return None
    
    def _calc_objection_rate(self, summary: dict) -> Optional[float]:
        """Calculate objection handling rate."""
        objections = summary.get("objections", {}).get("objections", [])
        if not objections:
            return None
        overcome = sum(1 for o in objections if o.get("overcome", False))
        return overcome / len(objections)
    
    def detect_trend(
        self,
        data_points: List[float]
    ) -> TrendResult:
        """
        Detect if metric is improving, stable, or declining (per Q41).
        
        Uses simple comparison:
        - If latest > first + 5%: improving
        - If latest < first - 5%: declining
        - Otherwise: stable
        """
        if len(data_points) < 2:
            return TrendResult(
                direction="insufficient_data",
                magnitude=0.0,
                data_points=len(data_points)
            )
        
        first = data_points[0]
        last = data_points[-1]
        
        if first == 0:
            magnitude = 1.0 if last > 0 else 0.0
        else:
            magnitude = (last - first) / first
        
        if magnitude >= self.IMPROVING_THRESHOLD:
            direction = "improving"
        elif magnitude <= self.DECLINING_THRESHOLD:
            direction = "declining"
        else:
            direction = "stable"
        
        return TrendResult(
            direction=direction,
            magnitude=magnitude,
            start_value=first,
            end_value=last,
            data_points=len(data_points)
        )
    
    def detect_anomalies(
        self,
        data_points: List[WeeklyMetrics],
        metric: str
    ) -> List[Anomaly]:
        """
        Detect week-over-week anomalies (per Q44: >20% sudden change).
        
        Flag only, no enforcement.
        """
        anomalies = []
        
        for i in range(1, len(data_points)):
            prev = data_points[i-1]
            curr = data_points[i]
            
            # Skip if either week has no data
            if prev.calls_analyzed == 0 or curr.calls_analyzed == 0:
                continue
            
            prev_value = prev.metrics.get(metric, 0)
            curr_value = curr.metrics.get(metric, 0)
            
            if prev_value == 0:
                continue
            
            change = (curr_value - prev_value) / prev_value
            
            if abs(change) >= self.ANOMALY_THRESHOLD:
                anomalies.append(Anomaly(
                    week_index=i,
                    week_start=curr.week_start,
                    change_magnitude=change,
                    direction="spike" if change > 0 else "drop",
                    previous_value=prev_value,
                    current_value=curr_value
                ))
        
        return anomalies
    
    async def get_peer_comparison(
        self,
        rep_id: str,
        metric: str,
        company_id: str,
        days: int = 30
    ) -> PeerComparison:
        """
        On-demand peer comparison (per Q45-Q46).
        
        Compare rep's score to all reps in same company.
        
        Args:
            rep_id: Representative to compare
            metric: Metric to compare
            company_id: Company identifier
            days: Analysis period
            
        Returns:
            PeerComparison with ranking and percentile
        """
        # Get rep name
        sample_call = await self.calls.find_one({
            "company_id": company_id,
            "metadata.rep_id": rep_id
        })
        rep_name = sample_call.get("metadata", {}).get("rep_name", rep_id) if sample_call else rep_id
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all reps' scores
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "call_date": {"$gte": cutoff_date},
                    "status": "completed"
                }
            },
            {
                "$lookup": {
                    "from": "call_summaries",
                    "localField": "call_id",
                    "foreignField": "call_id",
                    "as": "summary"
                }
            },
            {"$unwind": {"path": "$summary", "preserveNullAndEmptyArrays": True}},
            {
                "$group": {
                    "_id": "$metadata.rep_id",
                    "rep_name": {"$first": "$metadata.rep_name"},
                    "summaries": {"$push": "$summary"}
                }
            }
        ]
        
        cursor = self.calls.aggregate(pipeline)
        reps_data = await cursor.to_list(length=1000)
        
        # Calculate average score for each rep
        rep_scores = []
        target_rep_score = None
        
        for rep_data in reps_data:
            current_rep_id = rep_data["_id"]
            summaries = rep_data.get("summaries", [])
            
            # Extract metric values
            values = []
            for summary in summaries:
                if summary:
                    value = self._extract_metric_value(summary, metric)
                    if value is not None:
                        values.append(value)
            
            if values:
                avg_score = mean(values)
                rep_scores.append({
                    "rep_id": current_rep_id,
                    "score": avg_score
                })
                
                if current_rep_id == rep_id:
                    target_rep_score = avg_score
        
        if not rep_scores or target_rep_score is None:
            # Rep not found, return default
            return PeerComparison(
                rep_id=rep_id,
                rep_name=rep_name,
                company_id=company_id,
                metric=metric,
                rep_score=0.0,
                rep_rank=0,
                peer_count=len(rep_scores),
                peer_average=0.0,
                peer_median=0.0,
                peer_min=0.0,
                peer_max=0.0,
                percentile=0,
                analysis_period_days=days
            )
        
        # Sort by score descending
        sorted_scores = sorted(rep_scores, key=lambda x: x["score"], reverse=True)
        all_scores = [r["score"] for r in sorted_scores]
        
        # Find rep's rank
        rep_rank = next(
            (i + 1 for i, r in enumerate(sorted_scores) if r["rep_id"] == rep_id),
            len(sorted_scores)
        )
        
        # Calculate percentile (higher is better)
        percentile = int(100 * (len(sorted_scores) - rep_rank + 1) / len(sorted_scores))
        
        return PeerComparison(
            rep_id=rep_id,
            rep_name=rep_name,
            company_id=company_id,
            metric=metric,
            rep_score=target_rep_score,
            rep_rank=rep_rank,
            peer_count=len(sorted_scores),
            peer_average=mean(all_scores),
            peer_median=median(all_scores),
            peer_min=min(all_scores),
            peer_max=max(all_scores),
            percentile=percentile,
            analysis_period_days=days
        )
    
    async def get_agents_summary(
        self,
        company_id: str,
        weeks: int = 4
    ) -> List[AgentSummary]:
        """
        Get summary of all agents for manager view.
        
        Args:
            company_id: Company identifier
            weeks: Analysis period
            
        Returns:
            List of AgentSummary sorted by performance
        """
        cutoff_date = datetime.utcnow() - timedelta(weeks=weeks)
        
        # Get all reps with calls in period
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "call_date": {"$gte": cutoff_date},
                    "status": "completed"
                }
            },
            {
                "$lookup": {
                    "from": "call_summaries",
                    "localField": "call_id",
                    "foreignField": "call_id",
                    "as": "summary"
                }
            },
            {"$unwind": {"path": "$summary", "preserveNullAndEmptyArrays": True}},
            {
                "$group": {
                    "_id": "$metadata.rep_id",
                    "rep_name": {"$first": "$metadata.rep_name"},
                    "total_calls": {"$sum": 1},
                    "last_call_date": {"$max": "$call_date"},
                    "summaries": {"$push": "$summary"}
                }
            }
        ]
        
        cursor = self.calls.aggregate(pipeline)
        reps_data = await cursor.to_list(length=1000)
        
        summaries = []
        
        for rep_data in reps_data:
            rep_id = rep_data["_id"]
            rep_name = rep_data.get("rep_name", rep_id)
            
            # Calculate metrics
            compliance_scores = []
            bookings = 0
            
            for summary in rep_data.get("summaries", []):
                if not summary:
                    continue
                
                # Compliance
                compliance = summary.get("compliance", {}).get("sop_compliance", {}).get("score")
                if compliance is not None:
                    compliance_scores.append(compliance)
                
                # Booking
                if summary.get("qualification", {}).get("booking_status") == "booked":
                    bookings += 1
            
            total_calls = rep_data["total_calls"]
            avg_compliance = mean(compliance_scores) if compliance_scores else 0.0
            booking_rate = bookings / total_calls if total_calls > 0 else 0.0
            
            # Simple trend (would need historical data for proper calculation)
            trend_direction = "stable"
            
            # Alerts (basic implementation)
            alerts = []
            if avg_compliance < 0.6:
                alerts.append("Low compliance score")
            if booking_rate < 0.3:
                alerts.append("Low booking rate")
            
            summaries.append(AgentSummary(
                rep_id=rep_id,
                rep_name=rep_name,
                total_calls=total_calls,
                avg_compliance=avg_compliance,
                avg_booking_rate=booking_rate,
                trend_direction=trend_direction,
                weeks_active=weeks,
                last_call_date=rep_data.get("last_call_date"),
                alerts=alerts
            ))
        
        # Sort by booking rate descending
        summaries.sort(key=lambda x: x.avg_booking_rate, reverse=True)
        
        return summaries


# Singleton
_progression_service: Optional[ProgressionService] = None


def get_progression_service(db: AsyncIOMotorDatabase) -> ProgressionService:
    """Get ProgressionService instance"""
    global _progression_service
    if _progression_service is None:
        _progression_service = ProgressionService(db)
    return _progression_service
