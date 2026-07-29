"""
Insights Models

MongoDB document models for weekly insights engine.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .enums import InsightType, ProcessingStatus, TrendDirection, PriorityLevel, SentimentTrend


# ============================================================================
# COMPANY INSIGHTS
# ============================================================================

class TopPerformer(BaseModel):
    """Top performing rep"""
    rep_id: str
    rep_name: str
    calls: int
    booked: int
    booking_rate: float = Field(..., ge=0.0, le=1.0)
    avg_compliance: float = Field(..., ge=0.0, le=1.0)


class NeedsCoaching(BaseModel):
    """Rep needing coaching"""
    rep_id: str
    rep_name: str
    calls: int
    booked: int
    booking_rate: float = Field(..., ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)


class WeekOverWeek(BaseModel):
    """Week-over-week comparison"""
    booking_rate_change: float
    calls_change: int
    compliance_change: float
    sentiment_change: float


class TrendData(BaseModel):
    """Trend indicators"""
    booking_rate: TrendDirection
    calls: TrendDirection
    compliance: TrendDirection
    sentiment: TrendDirection
    
    class Config:
        use_enum_values = True


class CompanyInsightData(BaseModel):
    """Company-level insight data"""
    total_calls: int
    total_booked: int
    booking_rate: float = Field(..., ge=0.0, le=1.0)
    avg_call_duration: float
    avg_compliance_score: float = Field(..., ge=0.0, le=1.0)
    avg_sentiment_score: float = Field(..., ge=0.0, le=1.0)
    avg_qualification_score: float = Field(..., ge=0.0, le=1.0)
    top_performers: List[TopPerformer] = Field(default_factory=list)
    needs_coaching: List[NeedsCoaching] = Field(default_factory=list)
    # Insight fields (3-5 word heading + concise insight with action items)
    insight_heading: Optional[str] = None
    insight: Optional[str] = None
    recommendation_heading: Optional[str] = None
    recommendation: Optional[str] = None
    # Legacy field (kept for backward compatibility)
    top_insight: Optional[str] = None
    trends: TrendData
    week_over_week: WeekOverWeek


# ============================================================================
# CUSTOMER INSIGHTS
# ============================================================================

class CustomerInsightData(BaseModel):
    """Customer-level insight data"""
    calls_this_week: int
    total_calls: int
    current_status: str
    status_changed: bool
    sentiment_trend: SentimentTrend
    engagement_score: float = Field(..., ge=0.0, le=1.0)
    pending_actions: int
    overdue_actions: int
    last_call_date: Optional[datetime] = None
    # Insight fields (3-5 word heading + concise insight with action items)
    insight_heading: Optional[str] = None
    insight: Optional[str] = None
    recommendation_heading: Optional[str] = None
    recommendation: Optional[str] = None
    # Legacy field (kept for backward compatibility)
    next_recommended_action: Optional[str] = None
    priority: PriorityLevel
    
    class Config:
        use_enum_values = True


# ============================================================================
# OBJECTION INSIGHTS
# ============================================================================

class BestResponse(BaseModel):
    """Best response to objection"""
    rep: str
    call_id: str
    objection: str
    response: str
    outcome: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class SeverityBreakdown(BaseModel):
    """Breakdown by severity"""
    low: int = 0
    medium: int = 0
    high: int = 0


class SubObjectionBreakdown(BaseModel):
    """Breakdown of sub-objection types within 'Other' category"""
    sub_objection: str
    count: int
    overcome_count: int
    overcome_rate: float = Field(..., ge=0.0, le=1.0)


class ObjectionInsightData(BaseModel):
    """Objection category insight data"""
    category_id: int
    category_text: str
    total_count: int
    overcome_count: int
    overcome_rate: float = Field(..., ge=0.0, le=1.0)
    severity_breakdown: SeverityBreakdown
    trend_direction: TrendDirection
    trend_pct: float
    best_responses: List[BestResponse] = Field(default_factory=list)
    sub_objection_breakdown: List[SubObjectionBreakdown] = Field(default_factory=list)
    # Insight fields (3-5 word heading + concise insight with action items)
    insight_heading: Optional[str] = None
    insight: Optional[str] = None
    recommendation_heading: Optional[str] = None
    recommendation: Optional[str] = None

    class Config:
        use_enum_values = True


# ============================================================================
# MAIN INSIGHT MODEL
# ============================================================================

class WeeklyInsight(BaseModel):
    """Weekly insight document"""
    insight_type: InsightType
    company_id: str
    customer_id: Optional[str] = None  # Only for customer insights
    phone_number: Optional[str] = None  # Only for customer insights
    customer_name: Optional[str] = None  # Only for customer insights
    week_start: datetime
    week_end: datetime
    data: Dict[str, Any]  # Union of CompanyInsightData, CustomerInsightData, ObjectionInsightData
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED)
    job_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


# ============================================================================
# JOB TRACKING
# ============================================================================

class InsightGenerationJob(BaseModel):
    """Job tracking for insight generation"""
    job_id: str
    week_start: datetime
    week_end: datetime
    company_ids: List[str] = Field(default_factory=list)
    insight_types: List[InsightType] = Field(default_factory=list)
    status: ProcessingStatus
    progress_percent: int = Field(0, ge=0, le=100)
    current_step: Optional[str] = None
    companies_processed: int = 0
    companies_total: int = 0
    insights_generated: Dict[str, int] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    webhook_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True

