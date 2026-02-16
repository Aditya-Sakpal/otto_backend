"""
Customer Insights Service

Service for generating per-customer analytics and insights.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.insight import CustomerInsightData
from ...models.enums import PriorityLevel, SentimentTrend


class CustomerInsightsService:
    """Service for customer-level insights"""
    
    async def generate_customer_insights(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        week_start: datetime,
        week_end: datetime
    ) -> List[Dict[str, Any]]:
        """
        Generate insights for all customers with activity this week.
        
        Args:
            db: MongoDB database
            company_id: Company identifier
            week_start: Start of week
            week_end: End of week
            
        Returns:
            List of customer insight dictionaries
        """
        # Get all calls for the week with customer info
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
            # Group by phone number
            {
                "$group": {
                    "_id": "$phone_number",
                    "calls_this_week": {"$sum": 1},
                    "last_call_date": {"$max": "$call_date"},
                    "call_ids": {"$push": "$call_id"}
                }
            }
        ]
        
        cursor = db.calls.aggregate(pipeline)
        customer_groups = await cursor.to_list(length=None)
        
        insights = []
        
        for group in customer_groups:
            phone_number = group["_id"]
            calls_this_week = group["calls_this_week"]
            last_call_date = group["last_call_date"]
            call_ids = group["call_ids"]
            
            # Get customer info
            customer = await db.customers.find_one({
                "company_id": company_id,
                "phone": phone_number
            })
            
            customer_id = str(customer["_id"]) if customer else phone_number
            customer_name = customer.get("name") if customer else None
            total_calls = customer.get("total_calls", calls_this_week) if customer else calls_this_week
            
            # Get call summaries
            summaries_cursor = db.call_summaries.find({
                "call_id": {"$in": call_ids}
            })
            summaries = await summaries_cursor.to_list(length=None)
            
            # Analyze status
            current_status = "cold"
            status_changed = False
            
            if summaries:
                latest_summary = summaries[-1]
                current_status = latest_summary.get("qualification", {}).get("qualification_status", "cold")
                
                # Check if status changed
                if len(summaries) > 1:
                    previous_status = summaries[-2].get("qualification", {}).get("qualification_status", "cold")
                    status_changed = current_status != previous_status
            
            # Calculate sentiment trend
            sentiment_trend = await self._calculate_sentiment_trend(summaries)
            
            # Calculate engagement score
            engagement_score = self._calculate_engagement_score(
                calls_this_week, total_calls, summaries
            )
            
            # Count pending actions
            pending_actions = 0
            overdue_actions = 0
            
            for summary in summaries:
                actions = summary.get("summary", {}).get("pending_actions", [])
                pending_actions += len(actions)
                # TODO: Check if actions are overdue based on due_at
            
            # Generate insight with heading and action items
            insight_result = self._generate_insight_with_heading(
                current_status, status_changed, sentiment_trend, 
                calls_this_week, engagement_score
            )
            
            # Generate recommendation with heading and action items
            recommendation_result = self._generate_recommendation_with_heading(
                current_status, calls_this_week, pending_actions, sentiment_trend
            )
            
            # Calculate priority
            priority = self._calculate_priority(
                current_status, calls_this_week, sentiment_trend, pending_actions
            )
            
            # Create insight data
            insight_data = CustomerInsightData(
                calls_this_week=calls_this_week,
                total_calls=total_calls,
                current_status=current_status,
                status_changed=status_changed,
                sentiment_trend=sentiment_trend,
                engagement_score=engagement_score,
                pending_actions=pending_actions,
                overdue_actions=overdue_actions,
                last_call_date=last_call_date,
                insight_heading=insight_result["heading"],
                insight=insight_result["insight"],
                recommendation_heading=recommendation_result["heading"],
                recommendation=recommendation_result["recommendation"],
                next_recommended_action=recommendation_result["recommendation"],  # Legacy field
                priority=priority
            )
            
            insights.append({
                "customer_id": customer_id,
                "phone_number": phone_number,
                "customer_name": customer_name,
                "data": insight_data.dict()
            })
        
        return insights
    
    async def _calculate_sentiment_trend(self, summaries: List[Dict]) -> SentimentTrend:
        """Calculate sentiment trend from call summaries"""
        if len(summaries) < 2:
            return SentimentTrend.STABLE
        
        sentiments = [
            s.get("summary", {}).get("sentiment_score", 0.5)
            for s in summaries
        ]
        
        # Compare recent vs older
        recent_avg = sum(sentiments[-2:]) / 2 if len(sentiments) >= 2 else sentiments[-1]
        older_avg = sum(sentiments[:-2]) / len(sentiments[:-2]) if len(sentiments) > 2 else sentiments[0]
        
        diff = recent_avg - older_avg
        
        if abs(diff) < 0.1:
            return SentimentTrend.STABLE
        elif diff > 0:
            return SentimentTrend.IMPROVING
        else:
            return SentimentTrend.DECLINING
    
    def _calculate_engagement_score(
        self,
        calls_this_week: int,
        total_calls: int,
        summaries: List[Dict]
    ) -> float:
        """Calculate customer engagement score (0-1)"""
        score = 0.0
        
        # Frequency score (0-0.4)
        if calls_this_week >= 3:
            score += 0.4
        elif calls_this_week >= 2:
            score += 0.3
        elif calls_this_week >= 1:
            score += 0.2
        
        # History score (0-0.3)
        if total_calls >= 10:
            score += 0.3
        elif total_calls >= 5:
            score += 0.2
        elif total_calls >= 3:
            score += 0.1
        
        # Sentiment score (0-0.3)
        if summaries:
            avg_sentiment = sum(
                s.get("summary", {}).get("sentiment_score", 0.5)
                for s in summaries
            ) / len(summaries)
            score += avg_sentiment * 0.3
        
        return min(score, 1.0)
    
    def _generate_insight_with_heading(
        self,
        status: str,
        status_changed: bool,
        sentiment_trend: SentimentTrend,
        calls_this_week: int,
        engagement_score: float
    ) -> Dict[str, str]:
        """Generate insight with heading (3-5 words) and concise action items"""
        
        if status_changed and status == "hot":
            heading = "Customer Now Hot"
            insight = (
                "Status upgraded to hot this week. "
                "Action: Prioritize follow-up, prepare closing materials, schedule demo."
            )
        elif status_changed and status == "cold":
            heading = "Customer Went Cold"
            insight = (
                "Customer disengaged this week. "
                "Action: Review last interactions, send re-engagement email, offer value."
            )
        elif sentiment_trend == SentimentTrend.DECLINING:
            heading = "Sentiment Declining"
            insight = (
                "Customer sentiment trending negative. "
                "Action: Address concerns promptly, schedule call to discuss issues."
            )
        elif sentiment_trend == SentimentTrend.IMPROVING:
            heading = "Sentiment Improving"
            insight = (
                "Customer engagement trending positive. "
                "Action: Capitalize on momentum, propose next steps, upsell opportunities."
            )
        elif engagement_score >= 0.7:
            heading = "High Engagement"
            insight = (
                f"Strong engagement score ({engagement_score:.0%}). "
                "Action: Maintain contact frequency, identify decision timeline."
            )
        elif calls_this_week >= 3:
            heading = "Active This Week"
            insight = (
                f"{calls_this_week} calls this week shows high interest. "
                "Action: Move to next sales stage, confirm buying signals."
            )
        else:
            heading = "Steady Progress"
            insight = (
                "Customer on track. "
                "Action: Continue nurturing, share relevant content, monitor signals."
            )
        
        return {"heading": heading, "insight": insight}
    
    def _generate_recommendation_with_heading(
        self,
        status: str,
        calls_this_week: int,
        pending_actions: int,
        sentiment_trend: SentimentTrend
    ) -> Dict[str, str]:
        """Generate recommendation with heading (3-5 words) and concise action items"""
        
        if pending_actions > 0:
            heading = "Complete Pending Actions"
            recommendation = (
                f"{pending_actions} action(s) pending. "
                "Action: Review and complete tasks, update CRM, follow up on commitments."
            )
        elif sentiment_trend == SentimentTrend.DECLINING:
            heading = "Address Customer Concerns"
            recommendation = (
                "Sentiment is declining. "
                "Action: Call to understand issues, offer solutions, rebuild trust."
            )
        elif status == "hot":
            heading = "Close The Deal"
            recommendation = (
                "Customer ready to convert. "
                "Action: Send proposal, schedule closing call, prepare contract."
            )
        elif status == "warm":
            if calls_this_week >= 2:
                heading = "Schedule Appointment"
                recommendation = (
                    "High engagement detected. "
                    "Action: Book demo or meeting, send calendar invite, confirm decision makers."
                )
            else:
                heading = "Maintain Interest"
                recommendation = (
                    "Customer warming up. "
                    "Action: Follow up this week, share case study, ask qualifying questions."
                )
        elif status == "cold":
            heading = "Re-engage Customer"
            recommendation = (
                "Customer needs attention. "
                "Action: Send value-focused outreach, offer free consultation, nurture campaign."
            )
        else:
            heading = "Evaluate Fit"
            recommendation = (
                "Qualification unclear. "
                "Action: Run BANT assessment, verify budget and timeline, confirm decision maker."
            )
        
        return {"heading": heading, "recommendation": recommendation}
    
    def _calculate_priority(
        self,
        status: str,
        calls_this_week: int,
        sentiment_trend: SentimentTrend,
        pending_actions: int
    ) -> PriorityLevel:
        """Calculate customer priority level"""
        score = 0
        
        # Status score
        if status == "hot":
            score += 3
        elif status == "warm":
            score += 2
        elif status == "cold":
            score += 1
        
        # Activity score
        if calls_this_week >= 3:
            score += 2
        elif calls_this_week >= 2:
            score += 1
        
        # Sentiment score
        if sentiment_trend == SentimentTrend.DECLINING:
            score += 2
        elif sentiment_trend == SentimentTrend.IMPROVING:
            score += 1
        
        # Pending actions
        if pending_actions > 2:
            score += 2
        elif pending_actions > 0:
            score += 1
        
        # Determine priority
        if score >= 6:
            return PriorityLevel.HIGH
        elif score >= 3:
            return PriorityLevel.MEDIUM
        else:
            return PriorityLevel.LOW


# Singleton
_customer_insights_service: Optional[CustomerInsightsService] = None


def get_customer_insights_service() -> CustomerInsightsService:
    """Get singleton instance"""
    global _customer_insights_service
    if _customer_insights_service is None:
        _customer_insights_service = CustomerInsightsService()
    return _customer_insights_service

