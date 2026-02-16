"""
Objection Insights Service

Service for analyzing objections across calls.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.insight import ObjectionInsightData, BestResponse, SeverityBreakdown, SubObjectionBreakdown
from ...models.enums import TrendDirection, ObjectionCategory


class ObjectionInsightsService:
    """Service for objection analysis"""

    # Objection category mapping - derived from canonical ObjectionCategory enum
    OBJECTION_CATEGORIES = ObjectionCategory.get_category_mapping()
    
    async def generate_objection_insights(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        week_start: datetime,
        week_end: datetime
    ) -> List[ObjectionInsightData]:
        """
        Generate objection insights for all categories.
        
        Args:
            db: MongoDB database
            company_id: Company identifier
            week_start: Start of week
            week_end: End of week
            
        Returns:
            List of objection insights by category
        """
        # Get all call summaries for the week
        cursor = db.call_summaries.find({
            "company_id": company_id,
            "created_at": {
                "$gte": week_start,
                "$lte": week_end
            }
        })
        
        summaries = await cursor.to_list(length=None)
        
        if not summaries:
            return []
        
        # Collect all objections by category
        objections_by_category = {}
        
        for summary in summaries:
            objections = summary.get("objections", {}).get("objections", [])
            call_id = summary.get("call_id")
            
            for obj in objections:
                category_id = obj.get("category_id")
                if not category_id or category_id not in self.OBJECTION_CATEGORIES:
                    continue
                
                if category_id not in objections_by_category:
                    objections_by_category[category_id] = []
                
                objections_by_category[category_id].append({
                    "call_id": call_id,
                    "objection": obj,
                    "summary": summary
                })
        
        # Generate insights for each category
        insights = []
        
        for category_id, objections in objections_by_category.items():
            insight = await self._generate_category_insight(
                db,
                company_id,
                category_id,
                objections,
                week_start,
                week_end
            )
            insights.append(insight)
        
        # Sort by total count (most common first)
        insights.sort(key=lambda x: x.total_count, reverse=True)
        
        return insights
    
    async def _generate_category_insight(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        category_id: int,
        objections: List[Dict],
        week_start: datetime,
        week_end: datetime
    ) -> ObjectionInsightData:
        """Generate insight for a specific objection category"""
        category_text = self.OBJECTION_CATEGORIES[category_id]
        total_count = len(objections)
        
        # Count overcome
        overcome_count = sum(1 for obj in objections if obj["objection"].get("overcome", False))
        overcome_rate = overcome_count / total_count if total_count > 0 else 0.0
        
        # Severity breakdown
        severity_breakdown = SeverityBreakdown(
            low=sum(1 for obj in objections if obj["objection"].get("severity") == "low"),
            medium=sum(1 for obj in objections if obj["objection"].get("severity") == "medium"),
            high=sum(1 for obj in objections if obj["objection"].get("severity") == "high")
        )
        
        # Calculate trend
        previous_week_start = week_start - timedelta(days=7)
        previous_week_end = week_end - timedelta(days=7)
        
        previous_count = await self._get_previous_week_count(
            db, company_id, category_id, previous_week_start, previous_week_end
        )
        
        trend_pct = (total_count - previous_count) / previous_count if previous_count > 0 else 0.0
        trend_direction = self._calculate_trend_direction(trend_pct)
        
        # Find best responses
        best_responses = self._find_best_responses(objections)

        # Build sub-objection breakdown for "Other" category (category_id=9)
        # Uses Jaccard word similarity to group similar sub_objections together
        sub_objection_breakdown = []
        if category_id == 9:
            # Collect raw sub_objections with their stats
            raw_entries: List[Dict[str, Any]] = []
            for obj in objections:
                sub_obj = obj["objection"].get("sub_objection")
                if sub_obj:
                    raw_entries.append({
                        "label": sub_obj,
                        "overcome": obj["objection"].get("overcome", False)
                    })

            # Group similar sub_objections using Jaccard word similarity
            groups: List[Dict[str, Any]] = []  # [{label, count, overcome_count}]
            for entry in raw_entries:
                matched_group = None
                for group in groups:
                    if self._sub_objection_similarity(entry["label"], group["label"]) >= 0.5:
                        matched_group = group
                        break
                if matched_group:
                    matched_group["count"] += 1
                    if entry["overcome"]:
                        matched_group["overcome_count"] += 1
                else:
                    groups.append({
                        "label": entry["label"],
                        "count": 1,
                        "overcome_count": 1 if entry["overcome"] else 0
                    })

            for group in sorted(groups, key=lambda x: x["count"], reverse=True):
                sub_total = group["count"]
                sub_overcome = group["overcome_count"]
                sub_objection_breakdown.append(SubObjectionBreakdown(
                    sub_objection=group["label"],
                    count=sub_total,
                    overcome_count=sub_overcome,
                    overcome_rate=sub_overcome / sub_total if sub_total > 0 else 0.0
                ))

        # Generate insight and recommendation with headings
        insight_result = self._generate_insight_with_heading(
            category_text, total_count, overcome_rate, trend_direction, trend_pct
        )
        recommendation_result = self._generate_recommendation_with_heading(
            category_text, overcome_rate, severity_breakdown, best_responses
        )

        return ObjectionInsightData(
            category_id=category_id,
            category_text=category_text,
            total_count=total_count,
            overcome_count=overcome_count,
            overcome_rate=overcome_rate,
            severity_breakdown=severity_breakdown,
            trend_direction=trend_direction,
            trend_pct=trend_pct,
            best_responses=best_responses,
            sub_objection_breakdown=sub_objection_breakdown,
            insight_heading=insight_result["heading"],
            insight=insight_result["insight"],
            recommendation_heading=recommendation_result["heading"],
            recommendation=recommendation_result["recommendation"]
        )
    
    @staticmethod
    def _sub_objection_similarity(text1: str, text2: str) -> float:
        """Calculate Jaccard word-overlap similarity between two sub_objection labels."""
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union) if union else 0.0

    async def _get_previous_week_count(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        category_id: int,
        week_start: datetime,
        week_end: datetime
    ) -> int:
        """Get objection count from previous week"""
        # Check if insight exists
        insight = await db.weekly_insights.find_one({
            "insight_type": "objection",
            "company_id": company_id,
            "week_start": week_start,
            "data.category_id": category_id
        })
        
        if insight:
            return insight.get("data", {}).get("total_count", 0)
        
        # Calculate from raw data
        cursor = db.call_summaries.find({
            "company_id": company_id,
            "created_at": {"$gte": week_start, "$lte": week_end}
        })
        
        summaries = await cursor.to_list(length=None)
        count = 0
        
        for summary in summaries:
            objections = summary.get("objections", {}).get("objections", [])
            count += sum(1 for obj in objections if obj.get("category_id") == category_id)
        
        return count
    
    def _calculate_trend_direction(self, trend_pct: float) -> TrendDirection:
        """Calculate trend direction"""
        if abs(trend_pct) < 0.1:  # Less than 10% change
            return TrendDirection.STABLE
        elif trend_pct > 0:
            return TrendDirection.UP
        else:
            return TrendDirection.DOWN
    
    def _find_best_responses(self, objections: List[Dict]) -> List[BestResponse]:
        """Find best responses to objections"""
        # Filter overcome objections
        overcome_objections = [
            obj for obj in objections
            if obj["objection"].get("overcome", False)
            and obj["objection"].get("confidence_score", 0) > 0.7
        ]
        
        if not overcome_objections:
            return []
        
        # Sort by confidence
        overcome_objections.sort(
            key=lambda x: x["objection"].get("confidence_score", 0),
            reverse=True
        )
        
        # Extract best responses
        best_responses = []
        
        for obj_data in overcome_objections[:3]:  # Top 3
            obj = obj_data["objection"]
            summary = obj_data["summary"]
            call_id = obj_data["call_id"]
            
            # Get rep name from call metadata
            rep = summary.get("metadata", {}).get("rep_name", "Unknown")
            
            # Try to extract response from key points or action items
            response = "Successfully addressed objection"
            key_points = summary.get("summary", {}).get("key_points", [])
            if key_points:
                # Look for relevant key point
                for kp in key_points:
                    if any(word in kp.lower() for word in ["address", "resolve", "explain", "offer"]):
                        response = kp
                        break
            
            best_responses.append(BestResponse(
                rep=rep,
                call_id=call_id,
                objection=obj.get("objection_text", ""),
                response=response,
                outcome="overcome",
                confidence=obj.get("confidence_score", 0.8)
            ))
        
        return best_responses
    
    def _generate_insight_with_heading(
        self,
        category_text: str,
        total_count: int,
        overcome_rate: float,
        trend_direction: TrendDirection,
        trend_pct: float
    ) -> Dict[str, str]:
        """Generate insight with heading (3-5 words) and concise action items"""
        
        if trend_direction == TrendDirection.UP and trend_pct > 0.2:
            heading = f"{category_text} Objections Rising"
            insight = (
                f"{category_text} objections up {trend_pct:.0%} WoW ({total_count} this week). "
                "Action: Review pitch, address root cause proactively in calls."
            )
        elif trend_direction == TrendDirection.DOWN and trend_pct < -0.2:
            heading = f"{category_text} Objections Declining"
            insight = (
                f"{category_text} objections down {abs(trend_pct):.0%} WoW. "
                "Action: Document what's working, share tactics team-wide."
            )
        elif overcome_rate < 0.5:
            heading = f"Low {category_text} Success"
            insight = (
                f"Only {overcome_rate:.0%} overcome rate for {category_text}. "
                "Action: Create response scripts, role-play scenarios, get manager support."
            )
        elif overcome_rate >= 0.8:
            heading = f"{category_text} Well Handled"
            insight = (
                f"Strong {overcome_rate:.0%} overcome rate. "
                "Action: Extract best practices, train team on winning responses."
            )
        else:
            heading = f"{category_text} Overview"
            insight = (
                f"{total_count} objections, {overcome_rate:.0%} overcome rate. "
                "Action: Monitor trends, refine rebuttals continuously."
            )
        
        return {"heading": heading, "insight": insight}
    
    def _generate_recommendation_with_heading(
        self,
        category_text: str,
        overcome_rate: float,
        severity_breakdown: SeverityBreakdown,
        best_responses: List[BestResponse]
    ) -> Dict[str, str]:
        """Generate recommendation with heading (3-5 words) and concise action items"""
        
        high_severity_ratio = severity_breakdown.high / (
            severity_breakdown.low + severity_breakdown.medium + severity_breakdown.high
        ) if (severity_breakdown.low + severity_breakdown.medium + severity_breakdown.high) > 0 else 0
        
        if high_severity_ratio > 0.3:
            heading = "Address High-Severity Issues"
            recommendation = (
                f"{severity_breakdown.high} high-severity {category_text} objections. "
                "Action: Escalate to leadership, review product/pricing, update value prop."
            )
        elif overcome_rate < 0.5:
            heading = "Improve Response Training"
            recommendation = (
                f"Low overcome rate ({overcome_rate:.0%}) needs attention. "
                "Action: Build objection playbook, schedule training session, pair with top reps."
            )
        elif best_responses:
            top_rep = best_responses[0].rep
            heading = "Replicate Success"
            recommendation = (
                f"Learn from {top_rep}'s responses. "
                "Action: Share recordings, document techniques, incorporate in onboarding."
            )
        else:
            heading = "Monitor And Improve"
            recommendation = (
                f"Continue tracking {category_text} objections. "
                "Action: Collect more response data, A/B test rebuttals, track outcomes."
            )
        
        return {"heading": heading, "recommendation": recommendation}


# Singleton
_objection_insights_service: Optional[ObjectionInsightsService] = None


def get_objection_insights_service() -> ObjectionInsightsService:
    """Get singleton instance"""
    global _objection_insights_service
    if _objection_insights_service is None:
        _objection_insights_service = ObjectionInsightsService()
    return _objection_insights_service

