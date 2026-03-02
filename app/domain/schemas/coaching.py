"""
Coaching dashboard response schemas.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# --- Team Overview ---


class TeamMemberSummary(BaseModel):
    """Summary of a single team member for the coaching overview."""
    user_id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    role: str
    compliance_pct: float = 0.0
    booking_rate_pct: float = 0.0
    total_calls: int = 0
    trend: str = "stable"  # "improving" | "stable" | "declining"
    issues_count: int = 0
    strengths_count: int = 0


class TeamStats(BaseModel):
    """Team-level aggregate stats."""
    team_avg_compliance: float = 0.0
    team_avg_booking_rate: float = 0.0
    open_issues: int = 0
    team_size: int = 0


class TeamOverviewResponse(BaseModel):
    """Full team overview response."""
    stats: TeamStats
    members: List[TeamMemberSummary]


# --- Issues Tab ---


class CoachingIssueResponse(BaseModel):
    """A coaching issue aggregated across calls."""
    issue: str
    severity: str = "medium"  # "high" | "medium" | "low"
    frequency: int = 1
    why_it_matters: Optional[str] = None
    how_to_fix: Optional[str] = None
    example_language: Optional[str] = None
    transcript_evidence: List[str] = Field(default_factory=list)
    related_sop_metric: Optional[str] = None
    call_ids: List[str] = Field(default_factory=list)


class RepIssuesResponse(BaseModel):
    """Issues response for a rep."""
    rep_id: UUID
    rep_name: str
    total_issues: int = 0
    issues: List[CoachingIssueResponse]


# --- Strengths Tab ---


class CoachingStrengthResponse(BaseModel):
    """A coaching strength aggregated across calls."""
    behavior: str
    frequency: int = 1
    why_effective: Optional[str] = None
    transcript_evidence: List[str] = Field(default_factory=list)
    related_sop_metric: Optional[str] = None
    call_ids: List[str] = Field(default_factory=list)


class RepStrengthsResponse(BaseModel):
    """Strengths response for a rep."""
    rep_id: UUID
    rep_name: str
    total_strengths: int = 0
    strengths: List[CoachingStrengthResponse]


# --- Progression Tab (Shunya proxy) ---


class RepProgressionResponse(BaseModel):
    """Progression response proxied from Shunya API."""
    rep_id: str
    rep_name: Optional[str] = None
    company_id: str
    timeframe_weeks: int = 8
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    total_calls: int = 0
    weeks_with_data: int = 0
    overall_confidence: str = "low"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    improving_metrics: List[str] = Field(default_factory=list)
    declining_metrics: List[str] = Field(default_factory=list)
    stable_metrics: List[str] = Field(default_factory=list)


# --- Peer Benchmark Tab ---


class PeerBenchmarkMetric(BaseModel):
    """Peer benchmark data for a single metric."""
    metric: str
    rank: int = 0
    percentile: int = 0
    rep_score: float = 0.0
    peer_average: float = 0.0
    top_score: float = 0.0
    gap_to_top: float = 0.0
    vs_avg: float = 0.0  # delta from average


class RepPeerBenchmarkResponse(BaseModel):
    """Peer benchmark response for a rep."""
    rep_id: str
    rep_name: Optional[str] = None
    company_id: str
    metrics: List[PeerBenchmarkMetric]


# --- Impact Tab ---


class CoachingSessionSummary(BaseModel):
    """Summary of a coaching session with impact data."""
    session_id: UUID
    coached_at: datetime
    focus_areas: List[str] = Field(default_factory=list)
    status: str = "in_progress"
    follow_up_days: int = 14
    follow_up_end_date: Optional[datetime] = None
    baseline_scores: Optional[Dict[str, float]] = None
    impact_scores: Optional[Dict[str, float]] = None
    overall_improved: Optional[bool] = None
    improvement_pct: Optional[float] = None
    targets_met: Optional[Dict[str, bool]] = None
    days_into_follow_up: Optional[int] = None


class RepImpactResponse(BaseModel):
    """Impact response for a rep."""
    rep_id: UUID
    rep_name: str
    sessions: List[CoachingSessionSummary]


# --- Objections Tab ---


class ObjectionCategory(BaseModel):
    """Objection category with overcome rates."""
    category: str
    total_count: int = 0
    overcome_count: int = 0
    rep_overcome_rate: float = 0.0
    team_avg_overcome_rate: float = 0.0
    delta_vs_team: float = 0.0


class RepObjectionsResponse(BaseModel):
    """Objections response for a rep."""
    rep_id: UUID
    rep_name: str
    total_objections: int = 0
    categories: List[ObjectionCategory]


# --- Smart Nudges Tab ---


class SmartNudge(BaseModel):
    """An AI-generated coaching nudge."""
    title: str
    message: str
    priority: str = "medium"  # "high" | "medium" | "low"
    timing: str = "immediate"  # "immediate" | "pre_call" | "weekly"
    source: str = "coaching_issues"  # "coaching_issues" | "objection_history" | "progression"
    related_data: Optional[Dict[str, Any]] = None


class RepSmartNudgesResponse(BaseModel):
    """Smart nudges response for a rep."""
    rep_id: UUID
    rep_name: str
    nudges: List[SmartNudge]


# --- Combined Dashboard Response ---


class CoachingDashboardResponse(BaseModel):
    """Single combined response for the entire coaching dashboard."""
    team: Optional[TeamOverviewResponse] = None
    issues: Optional[RepIssuesResponse] = None
    strengths: Optional[RepStrengthsResponse] = None
    progression: Optional[Dict[str, Any]] = None
    peer_benchmark: Optional[RepPeerBenchmarkResponse] = None
    impact: Optional[RepImpactResponse] = None
    objections: Optional[RepObjectionsResponse] = None
    nudges: Optional[RepSmartNudgesResponse] = None


# --- Coaching Session CRUD ---


class CreateCoachingSessionRequest(BaseModel):
    """Request to create a new coaching session."""
    company_id: UUID
    rep_user_id: UUID
    coach_user_id: UUID
    focus_areas: List[str]
    targets: Dict[str, float] = Field(default_factory=dict)
    follow_up_days: int = 14
    notes: Optional[str] = None


class CoachingSessionResponse(BaseModel):
    """Response for a coaching session."""
    id: UUID
    company_id: UUID
    rep_user_id: UUID
    coach_user_id: UUID
    focus_areas: List[str]
    targets: Optional[Dict[str, float]] = None
    baseline_scores: Optional[Dict[str, float]] = None
    status: str
    follow_up_days: int
    follow_up_end_date: Optional[datetime] = None
    impact_scores: Optional[Dict[str, float]] = None
    overall_improved: Optional[bool] = None
    improvement_pct: Optional[float] = None
    targets_met: Optional[Dict[str, bool]] = None
    notes: Optional[str] = None
    coached_at: datetime
    created_at: datetime


class CoachingSessionListResponse(BaseModel):
    """Response for listing coaching sessions."""
    total: int
    sessions: List[CoachingSessionResponse]
