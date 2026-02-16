"""
Agent Progression Models

MongoDB models for agent behavior progression tracking.

Based on manager decisions Q37-Q48:
- Q37: Weekly granularity only
- Q38: 5 calls minimum per period (team decision)
- Q39: Show low-confidence trend if insufficient calls
- Q41: ≥5% change = improving/declining
- Q43: ≥15% decline = alert threshold
- Q44: Flag anomalies only (no enforcement)
- Q45: No peer comparison by default
- Q46: Peer comparison on-demand only
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class WeeklyMetrics(BaseModel):
    """Metrics for a single week"""
    week_start: datetime
    week_end: datetime
    calls_analyzed: int = 0
    confidence: str = Field(default="low", description="high (5+ calls) or low (<5 calls)")
    metrics: Dict[str, float] = Field(default_factory=dict, description="metric_name -> average score")


class TrendResult(BaseModel):
    """Trend analysis result"""
    direction: str = Field(default="stable", description="improving, stable, declining, insufficient_data")
    magnitude: float = Field(0.0, description="Percentage change from start to end")
    start_value: float = 0.0
    end_value: float = 0.0
    data_points: int = 0


class Anomaly(BaseModel):
    """Week-over-week anomaly detection"""
    week_index: int
    week_start: datetime
    change_magnitude: float = Field(..., description="Percentage change from previous week")
    direction: str = Field(..., description="spike or drop")
    previous_value: float
    current_value: float


class MetricProgression(BaseModel):
    """Progression data for a single metric"""
    metric_name: str
    data_points: List[WeeklyMetrics] = Field(default_factory=list)
    trend: TrendResult
    anomalies: List[Anomaly] = Field(default_factory=list)
    current_value: float = 0.0
    period_change: float = Field(0.0, description="Total change over analysis period")
    period_change_percent: float = 0.0


class AgentProgression(BaseModel):
    """Complete progression data for an agent"""
    rep_id: str
    rep_name: str
    company_id: str
    timeframe_weeks: int
    period_start: datetime
    period_end: datetime
    total_calls: int = 0
    weeks_with_data: int = 0
    overall_confidence: str = Field(default="low", description="high if most weeks have 5+ calls")
    metrics: Dict[str, MetricProgression] = Field(default_factory=dict)
    
    # Summary
    improving_metrics: List[str] = Field(default_factory=list)
    declining_metrics: List[str] = Field(default_factory=list)
    stable_metrics: List[str] = Field(default_factory=list)


class PeerComparison(BaseModel):
    """
    On-demand peer comparison (per Q45-Q46).
    
    Compare rep's score to all reps in same company.
    """
    rep_id: str
    rep_name: str
    company_id: str
    metric: str
    
    # Rep's score
    rep_score: float
    rep_rank: int
    
    # Peer stats
    peer_count: int
    peer_average: float
    peer_median: float
    peer_min: float
    peer_max: float
    percentile: int = Field(..., ge=0, le=100, description="Rep's percentile among peers")
    
    # Context
    analysis_period_days: int
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentSummary(BaseModel):
    """Summary view of an agent for manager dashboard"""
    rep_id: str
    rep_name: str
    total_calls: int
    avg_compliance: float
    avg_booking_rate: float
    trend_direction: str
    weeks_active: int
    last_call_date: Optional[datetime] = None
    alerts: List[str] = Field(default_factory=list, description="Any alerts for this rep")
