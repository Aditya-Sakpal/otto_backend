"""
Coaching Models

MongoDB models for closed-loop coaching impact measurement.

Based on manager decisions Q10-Q24:
- Q12: Support multiple skills per session
- Q14: 10 calls total (5 baseline, 5 validation)
- Q15: Minimum 5 calls for baseline
- Q16: Proceed with low-confidence flag if insufficient data
- Q17: Exclude outliers
- Q18: Manager-defined targets
- Q19: 2 week follow-up period (default)
- Q20: Automatic impact measurement on follow-up end
- Q22: Track positive change + improving trend
- Q23: Compare coach effectiveness
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CoachingBaseline(BaseModel):
    """
    Pre-coaching baseline scores.
    
    Per Q14-Q15: Use 5 calls minimum for baseline.
    Per Q17: Remove statistical outliers.
    """
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    calls_analyzed: int = Field(0, description="Number of calls used for baseline")
    call_ids: List[str] = Field(default_factory=list, description="IDs of calls used")
    scores: Dict[str, float] = Field(default_factory=dict, description="Metric -> score mapping")
    confidence: str = Field(default="low", description="high (5+ calls) or low (<5 calls)")
    outliers_removed: int = Field(0, description="Number of outlier calls excluded")


class ImprovementMetric(BaseModel):
    """Per-metric improvement details"""
    metric_name: str
    baseline_score: float
    current_score: Optional[float] = None  # None when no post-coaching data exists
    absolute_change: float = 0
    percentage_change: float = 0
    target: Optional[float] = None
    target_met: bool = False
    trend: str = Field(default="stable", description="improving, stable, declining, awaiting_data")


class CoachingImpact(BaseModel):
    """
    Post-coaching impact measurement.
    
    Per Q20: Auto-calculated on follow-up end.
    Per Q22: Track positive change + improving trend.
    """
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    calls_analyzed: int = Field(0, description="Number of follow-up calls analyzed")
    call_ids: List[str] = Field(default_factory=list, description="IDs of follow-up calls")
    scores: Dict[str, float] = Field(default_factory=dict, description="Metric -> current score (empty if no data)")
    
    # Per-metric improvements
    improvements: Dict[str, Any] = Field(default_factory=dict)  # Changed to Any to allow dict representation
    
    # Overall assessment
    overall_improved: bool = Field(False, description="Did rep improve overall?")
    trend_direction: str = Field(default="stable", description="improving, stable, declining, awaiting_data")
    targets_met: Dict[str, bool] = Field(default_factory=dict, description="Which targets were met")
    
    confidence: str = Field(default="low", description="high (5+ calls), low (<5 calls), none (0 calls)")


class CoachingSession(BaseModel):
    """
    Track individual coaching sessions.
    
    Per Q12: Support multiple focus areas per session.
    Per Q18: Manager-defined targets.
    Per Q19: Default 2 week follow-up period.
    """
    session_id: str = Field(..., description="Unique session identifier")
    company_id: str
    
    # Participants
    rep_id: str = Field(..., description="Representative being coached")
    rep_name: str
    coach_id: str = Field(..., description="Coach/manager ID")
    coach_name: str
    
    # Session details
    coached_at: datetime = Field(default_factory=datetime.utcnow)
    focus_areas: List[str] = Field(default_factory=list, description="Skills to improve")
    triggering_call_ids: List[str] = Field(default_factory=list, description="Calls that led to coaching")
    notes: Optional[str] = Field(None, description="Coach notes")
    
    # Manager-defined targets (per Q18)
    targets: Dict[str, float] = Field(default_factory=dict, description="metric -> target score")
    
    # Baseline data (auto-calculated from last 5 calls before coaching)
    baseline: Optional[CoachingBaseline] = None
    
    # Follow-up tracking (per Q19: default 2 weeks)
    follow_up_period_days: int = Field(14, description="Follow-up period in days")
    follow_up_end_date: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(days=14))
    extended_count: int = Field(0, description="Number of times follow-up was extended")
    
    # Status
    status: str = Field(default="in_progress", description="in_progress, completed, extended, insufficient_data")
    
    # Impact measurement (populated automatically per Q20)
    impact: Optional[CoachingImpact] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class SkillEffectiveness(BaseModel):
    """Effectiveness for a specific skill"""
    skill_name: str
    sessions_count: int = 0
    avg_improvement: float = 0.0
    success_rate: float = 0.0  # % of reps who improved


class CoachEffectiveness(BaseModel):
    """
    Aggregated coach performance metrics.
    
    Per Q23: Track per-coach metrics.
    Per Q24: Track improvement % + success rate.
    """
    coach_id: str
    coach_name: str
    company_id: str
    
    # Aggregated metrics (calculated weekly)
    period_start: datetime
    period_end: datetime
    
    # Overall metrics
    total_sessions: int = 0
    completed_sessions: int = 0
    reps_coached: int = 0
    reps_improved: int = 0
    improvement_rate: float = 0.0  # % of sessions that resulted in improvement
    
    avg_improvement_percentage: float = 0.0
    best_focus_area: Optional[str] = None  # Which skill they're best at coaching
    worst_focus_area: Optional[str] = None
    
    # Per-skill effectiveness
    skill_effectiveness: Dict[str, SkillEffectiveness] = Field(default_factory=dict)
    
    calculated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class CoachingROISummary(BaseModel):
    """Company-wide coaching ROI metrics"""
    company_id: str
    period_start: datetime
    period_end: datetime
    
    # Summary metrics
    total_sessions: int = 0
    total_coaches: int = 0
    total_reps_coached: int = 0
    
    # Impact metrics
    avg_improvement_rate: float = 0.0
    overall_success_rate: float = 0.0
    
    # Top metrics
    most_effective_focus_areas: List[str] = Field(default_factory=list)
    top_coaches: List[str] = Field(default_factory=list)
    
    # Trends
    sessions_trend: str = Field(default="stable", description="increasing, stable, decreasing")
    effectiveness_trend: str = Field(default="stable")
    
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
