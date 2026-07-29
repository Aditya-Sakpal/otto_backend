"""
Company Insights Service

Service for generating company-wide analytics and insights.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.insight import (
    CompanyInsightData,
    TopPerformer,
    NeedsCoaching,
    WeekOverWeek,
    TrendData
)
from ...models.enums import TrendDirection


class CompanyInsightsService:
    """Service for company-level insights"""
    
    async def generate_company_insight(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        week_start: datetime,
        week_end: datetime
    ) -> CompanyInsightData:
        """
        Generate company-wide insights for a given week.
        
        Args:
            db: MongoDB database
            company_id: Company identifier
            week_start: Start of week
            week_end: End of week
            
        Returns:
            CompanyInsightData with metrics
        """
        # Get all calls for the week
        pipeline = [
            # Match calls in date range
            {
                "$match": {
                    "company_id": company_id,
                    "call_date": {
                        "$gte": week_start,
                        "$lte": week_end
                    },
                    "status": "completed"
                }
            },
            # Lookup summaries
            {
                "$lookup": {
                    "from": "call_summaries",
                    "localField": "call_id",
                    "foreignField": "call_id",
                    "as": "summary"
                }
            },
            # Unwind summary
            {
                "$unwind": {
                    "path": "$summary",
                    "preserveNullAndEmptyArrays": True
                }
            }
        ]
        
        cursor = db.calls.aggregate(pipeline)
        calls = await cursor.to_list(length=None)
        
        if not calls:
            # Return empty insights
            return self._create_empty_insight()
        
        # Calculate metrics
        total_calls = len(calls)
        total_booked = sum(
            1 for c in calls
            if c.get("summary", {}).get("qualification", {}).get("booking_status") == "booked"
        )
        booking_rate = total_booked / total_calls if total_calls > 0 else 0.0
        
        # Average metrics
        avg_duration = sum(c.get("duration", 0) for c in calls) / total_calls if total_calls > 0 else 0.0
        
        avg_compliance = sum(
            c.get("summary", {}).get("compliance", {}).get("sop_compliance", {}).get("score", 0)
            for c in calls
        ) / total_calls if total_calls > 0 else 0.0
        
        avg_sentiment = sum(
            c.get("summary", {}).get("summary", {}).get("sentiment_score", 0)
            for c in calls
        ) / total_calls if total_calls > 0 else 0.0
        
        avg_qualification = sum(
            c.get("summary", {}).get("qualification", {}).get("overall_score", 0)
            for c in calls
        ) / total_calls if total_calls > 0 else 0.0
        
        # Top performers
        top_performers = await self._calculate_top_performers(calls)
        needs_coaching = await self._calculate_needs_coaching(calls)
        
        # Week-over-week comparison
        previous_week_start = week_start - timedelta(days=7)
        previous_week_end = week_end - timedelta(days=7)
        previous_metrics = await self._get_previous_week_metrics(
            db, company_id, previous_week_start, previous_week_end
        )
        
        week_over_week = WeekOverWeek(
            booking_rate_change=booking_rate - previous_metrics.get("booking_rate", 0),
            calls_change=total_calls - previous_metrics.get("total_calls", 0),
            compliance_change=avg_compliance - previous_metrics.get("avg_compliance", 0),
            sentiment_change=avg_sentiment - previous_metrics.get("avg_sentiment", 0)
        )
        
        # Trends
        trends = TrendData(
            booking_rate=self._calculate_trend(week_over_week.booking_rate_change),
            calls=self._calculate_trend(week_over_week.calls_change),
            compliance=self._calculate_trend(week_over_week.compliance_change),
            sentiment=self._calculate_trend(week_over_week.sentiment_change)
        )
        
        # Generate insights with headings and action items
        insight_data = self._generate_insight_with_heading(week_over_week, trends, calls)
        recommendation_data = self._generate_recommendation_with_heading(needs_coaching, calls)
        
        return CompanyInsightData(
            total_calls=total_calls,
            total_booked=total_booked,
            booking_rate=booking_rate,
            avg_call_duration=avg_duration,
            avg_compliance_score=avg_compliance,
            avg_sentiment_score=avg_sentiment,
            avg_qualification_score=avg_qualification,
            top_performers=top_performers,
            needs_coaching=needs_coaching,
            insight_heading=insight_data["heading"],
            insight=insight_data["insight"],
            recommendation_heading=recommendation_data["heading"],
            recommendation=recommendation_data["recommendation"],
            top_insight=insight_data["insight"],  # Legacy field
            trends=trends,
            week_over_week=week_over_week
        )
    
    async def _calculate_top_performers(self, calls: List[Dict]) -> List[TopPerformer]:
        """Calculate top performing reps"""
        # Group by rep
        rep_stats = {}
        
        for call in calls:
            rep_name = call.get("metadata", {}).get("rep_name", "Unknown")
            if rep_name not in rep_stats:
                rep_stats[rep_name] = {
                    "calls": 0,
                    "booked": 0,
                    "compliance_sum": 0.0
                }
            
            rep_stats[rep_name]["calls"] += 1
            
            if call.get("summary", {}).get("qualification", {}).get("booking_status") == "booked":
                rep_stats[rep_name]["booked"] += 1
            
            compliance = call.get("summary", {}).get("compliance", {}).get("sop_compliance", {}).get("score", 0)
            rep_stats[rep_name]["compliance_sum"] += compliance
        
        # Calculate rates and sort
        performers = []
        for rep_name, stats in rep_stats.items():
            booking_rate = stats["booked"] / stats["calls"] if stats["calls"] > 0 else 0.0
            avg_compliance = stats["compliance_sum"] / stats["calls"] if stats["calls"] > 0 else 0.0
            
            performers.append(TopPerformer(
                rep_id=rep_name.lower().replace(" ", "_"),
                rep_name=rep_name,
                calls=stats["calls"],
                booked=stats["booked"],
                booking_rate=booking_rate,
                avg_compliance=avg_compliance
            ))
        
        # Sort by booking rate and return top 5
        performers.sort(key=lambda x: x.booking_rate, reverse=True)
        return performers[:5]
    
    async def _calculate_needs_coaching(self, calls: List[Dict]) -> List[NeedsCoaching]:
        """Calculate reps needing coaching"""
        # Group by rep
        rep_stats = {}
        
        for call in calls:
            rep_name = call.get("metadata", {}).get("rep_name", "Unknown")
            if rep_name not in rep_stats:
                rep_stats[rep_name] = {
                    "calls": 0,
                    "booked": 0,
                    "issues": set()
                }
            
            rep_stats[rep_name]["calls"] += 1
            
            if call.get("summary", {}).get("qualification", {}).get("booking_status") == "booked":
                rep_stats[rep_name]["booked"] += 1
            
            # Check for issues
            compliance = call.get("summary", {}).get("compliance", {}).get("sop_compliance", {})
            if compliance.get("score", 1.0) < 0.7:
                rep_stats[rep_name]["issues"].add("Low compliance score")
            
            if compliance.get("issues"):
                for issue in compliance.get("issues", []):
                    rep_stats[rep_name]["issues"].add(issue)
        
        # Find reps with low performance
        needs_coaching = []
        for rep_name, stats in rep_stats.items():
            booking_rate = stats["booked"] / stats["calls"] if stats["calls"] > 0 else 0.0
            
            if booking_rate < 0.5 or len(stats["issues"]) > 0:
                needs_coaching.append(NeedsCoaching(
                    rep_id=rep_name.lower().replace(" ", "_"),
                    rep_name=rep_name,
                    calls=stats["calls"],
                    booked=stats["booked"],
                    booking_rate=booking_rate,
                    issues=list(stats["issues"])
                ))
        
        # Sort by booking rate (lowest first)
        needs_coaching.sort(key=lambda x: x.booking_rate)
        return needs_coaching[:5]
    
    async def _get_previous_week_metrics(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        week_start: datetime,
        week_end: datetime
    ) -> Dict[str, Any]:
        """Get metrics from previous week"""
        # Check if insights already exist
        insight = await db.weekly_insights.find_one({
            "insight_type": "company",
            "company_id": company_id,
            "week_start": week_start
        })
        
        if insight:
            data = insight.get("data", {})
            return {
                "booking_rate": data.get("booking_rate", 0),
                "total_calls": data.get("total_calls", 0),
                "avg_compliance": data.get("avg_compliance_score", 0),
                "avg_sentiment": data.get("avg_sentiment_score", 0)
            }
        
        # Calculate from raw data
        cursor = db.calls.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "call_date": {"$gte": week_start, "$lte": week_end},
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
            {"$unwind": {"path": "$summary", "preserveNullAndEmptyArrays": True}}
        ])
        
        calls = await cursor.to_list(length=None)
        
        if not calls:
            return {
                "booking_rate": 0,
                "total_calls": 0,
                "avg_compliance": 0,
                "avg_sentiment": 0
            }
        
        total_calls = len(calls)
        total_booked = sum(
            1 for c in calls
            if c.get("summary", {}).get("qualification", {}).get("booking_status") == "booked"
        )
        
        return {
            "booking_rate": total_booked / total_calls if total_calls > 0 else 0,
            "total_calls": total_calls,
            "avg_compliance": sum(
                c.get("summary", {}).get("compliance", {}).get("sop_compliance", {}).get("score", 0)
                for c in calls
            ) / total_calls if total_calls > 0 else 0,
            "avg_sentiment": sum(
                c.get("summary", {}).get("summary", {}).get("sentiment_score", 0)
                for c in calls
            ) / total_calls if total_calls > 0 else 0
        }
    
    def _calculate_trend(self, change: float) -> TrendDirection:
        """Calculate trend direction from change"""
        if abs(change) < 0.02:  # Less than 2% change
            return TrendDirection.STABLE
        elif change > 0:
            return TrendDirection.UP
        else:
            return TrendDirection.DOWN
    
    def _generate_insight_with_heading(
        self, wow: WeekOverWeek, trends: TrendData, calls: List[Dict]
    ) -> Dict[str, str]:
        """Generate insight with heading (3-5 words) and concise action items"""
        
        # Determine primary insight based on metrics
        if wow.booking_rate_change > 0.05:
            heading = "Booking Rate Up"
            insight = (
                f"Bookings increased {wow.booking_rate_change:.1%} WoW. "
                "Action: Identify winning tactics from top performers and replicate across team."
            )
        elif wow.booking_rate_change < -0.05:
            heading = "Booking Rate Declined"
            insight = (
                f"Bookings dropped {abs(wow.booking_rate_change):.1%} WoW. "
                "Action: Review lost opportunities, audit call scripts, schedule team debrief."
            )
        elif wow.compliance_change > 0.05:
            heading = "Compliance Improving"
            insight = (
                "SOP compliance trending up. "
                "Action: Recognize compliant reps, document best practices for training."
            )
        elif wow.compliance_change < -0.05:
            heading = "Compliance Slipping"
            insight = (
                "SOP adherence declining. "
                "Action: Reinforce SOP training, conduct spot-check call reviews."
            )
        elif wow.calls_change > 10:
            heading = "Call Volume Surge"
            insight = (
                f"{wow.calls_change} more calls this week. "
                "Action: Monitor quality metrics, ensure adequate staffing."
            )
        elif wow.calls_change < -10:
            heading = "Call Volume Drop"
            insight = (
                f"{abs(wow.calls_change)} fewer calls this week. "
                "Action: Investigate lead sources, review outreach strategies."
            )
        else:
            heading = "Performance Stable"
            insight = (
                "Metrics holding steady. "
                "Action: Set stretch goals, A/B test new approaches to drive growth."
            )
        
        return {"heading": heading, "insight": insight}
    
    def _generate_recommendation_with_heading(
        self, needs_coaching: List[NeedsCoaching], calls: List[Dict]
    ) -> Dict[str, str]:
        """Generate recommendation with heading (3-5 words) and concise action items"""
        
        if needs_coaching:
            rep_names = [nc.rep_name for nc in needs_coaching[:2]]
            issues = []
            for nc in needs_coaching[:2]:
                issues.extend(nc.issues[:2])
            
            heading = "Coaching Needed"
            recommendation = (
                f"Focus on: {', '.join(rep_names)}. "
                f"Issues: {', '.join(issues[:3]) if issues else 'Low booking rate'}. "
                "Action: Schedule 1-on-1 coaching, shadow top performers."
            )
            return {"heading": heading, "recommendation": recommendation}
        
        # Check objections
        objection_counts = {}
        for call in calls:
            objections = call.get("summary", {}).get("objections", {}).get("objections", [])
            for obj in objections:
                cat = obj.get("category_text", "Unknown")
                objection_counts[cat] = objection_counts.get(cat, 0) + 1
        
        if objection_counts:
            top_objection = max(objection_counts.items(), key=lambda x: x[1])
            heading = "Objection Handling Focus"
            recommendation = (
                f"Top objection: {top_objection[0]} ({top_objection[1]} occurrences). "
                "Action: Create response playbook, role-play exercises in team meetings."
            )
            return {"heading": heading, "recommendation": recommendation}
        
        heading = "Maintain Momentum"
        recommendation = (
            "Team performing well. "
            "Action: Set new targets, introduce incentive programs, celebrate wins."
        )
        return {"heading": heading, "recommendation": recommendation}
    
    def _create_empty_insight(self) -> CompanyInsightData:
        """Create empty insight for weeks with no data"""
        return CompanyInsightData(
            total_calls=0,
            total_booked=0,
            booking_rate=0.0,
            avg_call_duration=0.0,
            avg_compliance_score=0.0,
            avg_sentiment_score=0.0,
            avg_qualification_score=0.0,
            top_performers=[],
            needs_coaching=[],
            insight_heading="No Activity",
            insight="No calls recorded this week. Action: Review lead pipeline, verify integration status.",
            recommendation_heading="Generate Activity",
            recommendation="No data to analyze. Action: Ensure calls are being logged, check system integrations.",
            top_insight="No calls this week",  # Legacy field
            trends=TrendData(
                booking_rate=TrendDirection.STABLE,
                calls=TrendDirection.STABLE,
                compliance=TrendDirection.STABLE,
                sentiment=TrendDirection.STABLE
            ),
            week_over_week=WeekOverWeek(
                booking_rate_change=0.0,
                calls_change=0,
                compliance_change=0.0,
                sentiment_change=0.0
            )
        )


# Singleton
_company_insights_service: Optional[CompanyInsightsService] = None


def get_company_insights_service() -> CompanyInsightsService:
    """Get singleton instance"""
    global _company_insights_service
    if _company_insights_service is None:
        _company_insights_service = CompanyInsightsService()
    return _company_insights_service

