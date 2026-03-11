"""
Coaching dashboard response schemas.

Models for the combined coaching dashboard API, coaching session CRUD,
and all sub-section data structures (team overview, issues, strengths,
progression, peer benchmark, impact, objections, smart nudges).
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# --- Team Overview ---


class TeamMemberSummary(BaseModel):
    """Summary of a single team member for the coaching overview."""
    user_id: UUID = Field(..., description="User UUID of the team member")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="User role (e.g. sales_rep, csr, executive)")
    compliance_pct: float = Field(0.0, description="Average SOP compliance percentage (0-100)")
    booking_rate_pct: float = Field(0.0, description="Booking rate percentage (booked/qualified * 100)")
    total_calls: int = Field(0, description="Total calls handled in the date range")
    trend: str = Field("stable", description="Performance trend: 'improving', 'stable', or 'declining'. Based on first-half vs second-half compliance comparison")
    issues_count: int = Field(0, description="Number of coaching issues identified in the date range")
    strengths_count: int = Field(0, description="Number of coaching strengths identified in the date range")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "user_id": "3eed8382-6b30-44c9-82f6-6d70570e175e",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@company.com",
                "role": "csr",
                "compliance_pct": 78.5,
                "booking_rate_pct": 45.2,
                "total_calls": 42,
                "trend": "improving",
                "issues_count": 5,
                "strengths_count": 3,
            }]
        }
    }


class TeamStats(BaseModel):
    """Team-level aggregate stats shown at the top of the coaching page."""
    team_avg_compliance: float = Field(0.0, description="Average SOP compliance across all team members (0-100)")
    team_avg_booking_rate: float = Field(0.0, description="Average booking rate across all team members (0-100)")
    open_issues: int = Field(0, description="Total coaching issues across all team members in date range")
    team_size: int = Field(0, description="Number of active team members")


class TeamOverviewResponse(BaseModel):
    """Full team overview. Shows team-level stats and a per-member breakdown."""
    stats: TeamStats = Field(..., description="Aggregated team-level statistics")
    members: List[TeamMemberSummary] = Field(..., description="Per-member coaching summaries")


# --- Issues Tab ---


class CoachingIssueResponse(BaseModel):
    """A coaching issue aggregated across multiple calls. Issues with the same text are grouped together and counted."""
    issue: str = Field(..., description="Description of the coaching issue (e.g. 'Did not ask discovery questions')")
    severity: str = Field("medium", description="Issue severity: 'high', 'medium', or 'low'")
    frequency: int = Field(1, description="Number of calls where this issue was detected")
    why_it_matters: Optional[str] = Field(None, description="Explanation of why this issue impacts performance")
    how_to_fix: Optional[str] = Field(None, description="Actionable recommendation to fix this issue")
    example_language: Optional[str] = Field(None, description="Example script/language the rep should use instead")
    transcript_evidence: List[str] = Field(default_factory=list, description="Transcript excerpts showing the issue (max 5)")
    related_sop_metric: Optional[str] = Field(None, description="SOP metric this issue relates to (e.g. 'greeting', 'discovery', 'closing')")
    call_ids: List[str] = Field(default_factory=list, description="UUIDs of calls where this issue appeared (max 10)")


class RepIssuesResponse(BaseModel):
    """All coaching issues for a specific rep, grouped by issue type and sorted by frequency (most frequent first)."""
    rep_id: UUID = Field(..., description="User UUID of the rep")
    rep_name: str = Field(..., description="Full name of the rep")
    total_issues: int = Field(0, description="Number of distinct issue types found")
    issues: List[CoachingIssueResponse] = Field(..., description="Issues sorted by frequency descending")


# --- Strengths Tab ---


class CoachingStrengthResponse(BaseModel):
    """A coaching strength aggregated across multiple calls. Strengths with the same behavior are grouped."""
    behavior: str = Field(..., description="Description of the positive behavior (e.g. 'Strong rapport building')")
    frequency: int = Field(1, description="Number of calls where this strength was observed")
    why_effective: Optional[str] = Field(None, description="Explanation of why this behavior is effective")
    transcript_evidence: List[str] = Field(default_factory=list, description="Transcript excerpts showing the strength (max 5)")
    related_sop_metric: Optional[str] = Field(None, description="SOP metric this strength relates to")
    call_ids: List[str] = Field(default_factory=list, description="UUIDs of calls where this strength appeared (max 10)")


class RepStrengthsResponse(BaseModel):
    """All coaching strengths for a specific rep, grouped by behavior and sorted by frequency."""
    rep_id: UUID = Field(..., description="User UUID of the rep")
    rep_name: str = Field(..., description="Full name of the rep")
    total_strengths: int = Field(0, description="Number of distinct strength types found")
    strengths: List[CoachingStrengthResponse] = Field(..., description="Strengths sorted by frequency descending")


# --- Progression Tab (Shunya proxy) ---


class RepProgressionResponse(BaseModel):
    """
    Progression response proxied from Shunya API.

    Shows weekly metric trends over a configurable number of weeks.
    The `metrics` dict is keyed by metric name (e.g. 'compliance_score')
    and contains weekly data points with values, trend direction, and anomaly flags.
    """
    rep_id: str = Field(..., description="User UUID of the rep (string)")
    rep_name: Optional[str] = Field(None, description="Full name of the rep")
    company_id: str = Field(..., description="Company UUID (string)")
    timeframe_weeks: int = Field(8, description="Number of weeks analyzed")
    period_start: Optional[str] = Field(None, description="Start of the analysis period (ISO 8601)")
    period_end: Optional[str] = Field(None, description="End of the analysis period (ISO 8601)")
    total_calls: int = Field(0, description="Total calls in the period")
    weeks_with_data: int = Field(0, description="Number of weeks that had call data")
    overall_confidence: str = Field("low", description="Confidence level of the trend analysis: 'high', 'medium', or 'low'")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Per-metric weekly data. Keys: metric name. Values: {weekly_data: [{week, value, trend}], overall_trend, anomalies}")
    improving_metrics: List[str] = Field(default_factory=list, description="List of metric names that are trending upward")
    declining_metrics: List[str] = Field(default_factory=list, description="List of metric names that are trending downward")
    stable_metrics: List[str] = Field(default_factory=list, description="List of metric names with no significant change")


# --- Peer Benchmark Tab ---


class PeerBenchmarkMetric(BaseModel):
    """Peer benchmark comparison for a single metric. Shows how the rep compares to the team."""
    metric: str = Field(..., description="Metric name: 'compliance_score', 'booking_rate', 'objection_handling', 'rapport_score', or 'script_adherence'")
    rank: int = Field(0, description="Rep's rank within the team (1 = best)")
    percentile: int = Field(0, description="Rep's percentile within the team (0-100)")
    rep_score: float = Field(0.0, description="Rep's score for this metric (0-100)")
    peer_average: float = Field(0.0, description="Team average score for this metric (0-100)")
    top_score: float = Field(0.0, description="Highest score on the team for this metric (0-100)")
    gap_to_top: float = Field(0.0, description="Difference between rep's score and top score (positive = behind)")
    vs_avg: float = Field(0.0, description="Difference between rep's score and team average (positive = above avg, negative = below)")


class RepPeerBenchmarkResponse(BaseModel):
    """Peer benchmark comparison for a rep across 5 key metrics. Shows rep score vs team average and top performer."""
    rep_id: str = Field(..., description="User UUID of the rep (string)")
    rep_name: Optional[str] = Field(None, description="Full name of the rep")
    company_id: str = Field(..., description="Company UUID (string)")
    metrics: List[PeerBenchmarkMetric] = Field(..., description="Benchmark data for each of the 5 metrics")


# --- Impact Tab ---


class CoachingSessionSummary(BaseModel):
    """Summary of a coaching session with pre/post impact measurement."""
    session_id: UUID = Field(..., description="Coaching session UUID")
    coached_at: datetime = Field(..., description="When the coaching session took place (ISO 8601)")
    focus_areas: List[str] = Field(default_factory=list, description="Metrics/areas the session focused on (e.g. ['compliance_score', 'booking_rate'])")
    status: str = Field("in_progress", description="Session status: 'in_progress' or 'completed'")
    follow_up_days: int = Field(14, description="Follow-up period in days for measuring impact")
    follow_up_end_date: Optional[datetime] = Field(None, description="When the follow-up period ends (ISO 8601)")
    baseline_scores: Optional[Dict[str, float]] = Field(None, description="Scores before coaching. Keys: metric name, values: score (0-1 scale). e.g. {'compliance_score': 0.72, 'booking_rate': 0.4}")
    impact_scores: Optional[Dict[str, float]] = Field(None, description="Scores after coaching (measured during follow-up). Same format as baseline_scores")
    overall_improved: Optional[bool] = Field(None, description="Whether the rep improved overall after coaching (null if follow-up not complete)")
    improvement_pct: Optional[float] = Field(None, description="Overall improvement percentage (null if follow-up not complete)")
    targets_met: Optional[Dict[str, bool]] = Field(None, description="Which target metrics were met. Keys: metric name, values: true/false")
    days_into_follow_up: Optional[int] = Field(None, description="How many days into the follow-up period (null if no follow-up set)")


class RepImpactResponse(BaseModel):
    """All coaching sessions and their impact data for a specific rep. Shows baseline vs post-coaching scores."""
    rep_id: UUID = Field(..., description="User UUID of the rep")
    rep_name: str = Field(..., description="Full name of the rep")
    sessions: List[CoachingSessionSummary] = Field(..., description="Coaching sessions sorted by date descending")


# --- Objections Tab ---


class ObjectionCategory(BaseModel):
    """Objection handling stats for a single category. Compares rep's overcome rate to the team average."""
    category: str = Field(..., description="Objection category name (e.g. 'Price', 'Timing', 'Competitor', 'Trust')")
    total_count: int = Field(0, description="Total times this objection category appeared for the rep")
    overcome_count: int = Field(0, description="Number of times the rep successfully overcame this objection")
    rep_overcome_rate: float = Field(0.0, description="Rep's overcome rate for this category (0-100)")
    team_avg_overcome_rate: float = Field(0.0, description="Team average overcome rate for this category (0-100)")
    delta_vs_team: float = Field(0.0, description="Rep rate minus team rate. Positive = better than team, negative = worse")


class RepObjectionsResponse(BaseModel):
    """Objection handling overview for a specific rep. Grouped by category, sorted by frequency."""
    rep_id: UUID = Field(..., description="User UUID of the rep")
    rep_name: str = Field(..., description="Full name of the rep")
    total_objections: int = Field(0, description="Total objections encountered by the rep")
    categories: List[ObjectionCategory] = Field(..., description="Objection categories sorted by total_count descending")


# --- Smart Nudges Tab ---


class SmartNudge(BaseModel):
    """
    An AI-generated coaching nudge/recommendation.

    Nudges are generated from three sources:
    - coaching_issues: High-frequency or high-severity issues trigger immediate nudges
    - objection_history: Low overcome rates trigger pre-call preparation nudges
    - progression: Declining compliance trends trigger weekly review nudges
    """
    title: str = Field(..., description="Short title for the nudge (max 80 chars)")
    message: str = Field(..., description="Detailed coaching message with specific advice")
    priority: str = Field("medium", description="Priority: 'high', 'medium', or 'low'")
    timing: str = Field("immediate", description="When to deliver: 'immediate' (act now), 'pre_call' (before next call), or 'weekly' (weekly digest)")
    source: str = Field("coaching_issues", description="What generated this nudge: 'coaching_issues', 'objection_history', or 'progression'")
    related_data: Optional[Dict[str, Any]] = Field(None, description="Additional context data (e.g. issue frequency, overcome rate)")


class RepSmartNudgesResponse(BaseModel):
    """Smart nudges for a specific rep. Sorted by priority (high first)."""
    rep_id: UUID = Field(..., description="User UUID of the rep")
    rep_name: str = Field(..., description="Full name of the rep")
    nudges: List[SmartNudge] = Field(..., description="Coaching nudges sorted by priority descending")


# --- Combined Dashboard Response ---


class CoachingDashboardResponse(BaseModel):
    """
    Single combined response for the entire coaching dashboard.

    All 8 sections are fetched in parallel. If any individual section fails
    (e.g. Shunya API is unavailable for progression/peer_benchmark), that
    section returns null instead of failing the entire request.

    **Sections:**
    - **team**: Team overview with compliance/booking stats and per-member summaries
    - **issues**: Rep's coaching issues grouped by type, sorted by frequency
    - **strengths**: Rep's coaching strengths grouped by behavior, sorted by frequency
    - **progression**: Weekly metric trends from Shunya API (may be null if Shunya is down)
    - **peer_benchmark**: Rep vs team comparison on 5 metrics from Shunya API (may be null if Shunya is down)
    - **impact**: Coaching session history with baseline vs post-coaching scores
    - **objections**: Objection handling stats by category with overcome rates
    - **nudges**: AI-generated coaching recommendations based on issues, objections, and trends
    """
    team: Optional[TeamOverviewResponse] = Field(None, description="Team overview: aggregate stats and per-member summaries. Uses role_filter and search query params")
    issues: Optional[RepIssuesResponse] = Field(None, description="Rep's coaching issues grouped by type. Filtered by start_date/end_date")
    strengths: Optional[RepStrengthsResponse] = Field(None, description="Rep's coaching strengths grouped by behavior. Filtered by start_date/end_date")
    progression: Optional[Dict[str, Any]] = Field(None, description="Weekly metric progression from Shunya API. Uses 'weeks' query param. May be null if Shunya is unavailable")
    peer_benchmark: Optional[RepPeerBenchmarkResponse] = Field(None, description="Rep vs team benchmark on 5 metrics from Shunya API. Uses 'days' query param. May be null if Shunya is unavailable")
    impact: Optional[RepImpactResponse] = Field(None, description="Coaching session impact: baseline vs post-coaching scores")
    objections: Optional[RepObjectionsResponse] = Field(None, description="Objection handling stats by category with rep vs team overcome rates. Filtered by start_date/end_date")
    nudges: Optional[RepSmartNudgesResponse] = Field(None, description="AI-generated coaching nudges based on issues, objections, and compliance trends. Filtered by start_date/end_date")


# --- Split Dashboard Responses ---


class TeamDashboardResponse(BaseModel):
    """
    Team-level coaching overview response.

    Used when the user first lands on the coaching page to show a high-level
    team summary. Does not require a specific rep user_id.
    """
    team: Optional[TeamOverviewResponse] = Field(None, description="Team overview: aggregate stats and per-member summaries. Uses role_filter and search query params")


class IndividualDashboardResponse(BaseModel):
    """
    Individual rep coaching dashboard response.

    Contains all 7 rep-specific sections fetched in parallel. Used when a
    manager clicks on a specific team member to see their detailed coaching data.
    If any section fails (e.g. Shunya API is down), that section returns null
    while the rest still return data.

    **Sections:**
    - **issues**: Coaching issues grouped by type, sorted by frequency
    - **strengths**: Coaching strengths grouped by behavior, sorted by frequency
    - **progression**: Weekly metric trends from Shunya API
    - **peer_benchmark**: Rep vs team on 5 metrics from Shunya API
    - **impact**: Coaching sessions with baseline vs post-coaching scores
    - **objections**: Objection categories with rep overcome rate vs team average
    - **nudges**: AI-generated coaching recommendations
    """
    issues: Optional[RepIssuesResponse] = Field(None, description="Rep's coaching issues grouped by type. Filtered by start_date/end_date")
    strengths: Optional[RepStrengthsResponse] = Field(None, description="Rep's coaching strengths grouped by behavior. Filtered by start_date/end_date")
    progression: Optional[Dict[str, Any]] = Field(None, description="Weekly metric progression from Shunya API. Uses 'weeks' query param. May be null if Shunya is unavailable")
    peer_benchmark: Optional[RepPeerBenchmarkResponse] = Field(None, description="Rep vs team benchmark on 5 metrics from Shunya API. Uses 'days' query param. May be null if Shunya is unavailable")
    impact: Optional[RepImpactResponse] = Field(None, description="Coaching session impact: baseline vs post-coaching scores")
    objections: Optional[RepObjectionsResponse] = Field(None, description="Objection handling stats by category with rep vs team overcome rates. Filtered by start_date/end_date")
    nudges: Optional[RepSmartNudgesResponse] = Field(None, description="AI-generated coaching nudges based on issues, objections, and compliance trends. Filtered by start_date/end_date")


# --- Coaching Session CRUD ---


class CreateCoachingSessionRequest(BaseModel):
    """
    Request body to create a new coaching session.

    When a session is created, the system automatically computes baseline_scores
    from the rep's last 5 completed call analyses. The coaching cycle starts
    immediately and runs for follow_up_days (default 7). After each cycle,
    the system auto-restarts a new cycle with updated baselines.
    """
    company_id: UUID = Field(..., description="Company UUID")
    rep_user_id: UUID = Field(..., description="User UUID of the rep being coached")
    coach_user_id: UUID = Field(..., description="User UUID of the coach/manager")
    focus_areas: List[str] = Field(..., description="Metrics to focus on (e.g. ['compliance_score', 'booking_rate', 'objection_handling'])")
    targets: Dict[str, float] = Field(default_factory=dict, description="Target scores to achieve. Keys: metric name, values: target score (0-1 scale). e.g. {'compliance_score': 0.85}")
    follow_up_days: int = Field(7, description="Number of days per coaching cycle (default 7). System auto-restarts a new cycle after each period.")
    notes: Optional[str] = Field(None, description="Free-text coaching notes")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
                "rep_user_id": "3eed8382-6b30-44c9-82f6-6d70570e175e",
                "coach_user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "focus_areas": ["compliance_score", "booking_rate"],
                "targets": {"compliance_score": 0.85, "booking_rate": 0.5},
                "follow_up_days": 7,
                "notes": "Focus on discovery questions and closing technique",
            }]
        }
    }


class CoachingSessionResponse(BaseModel):
    """Response for a single coaching session with all details including auto-computed baseline."""
    id: UUID = Field(..., description="Coaching session UUID")
    company_id: UUID = Field(..., description="Company UUID")
    rep_user_id: UUID = Field(..., description="User UUID of the rep being coached")
    coach_user_id: UUID = Field(..., description="User UUID of the coach/manager")
    focus_areas: List[str] = Field(..., description="Metrics being focused on")
    targets: Optional[Dict[str, float]] = Field(None, description="Target scores. Keys: metric name, values: target (0-1 scale)")
    baseline_scores: Optional[Dict[str, float]] = Field(None, description="Auto-computed baseline from last 5 call analyses. Keys: metric name, values: average score")
    status: str = Field(..., description="Session status: 'in_progress' or 'completed'")
    follow_up_days: int = Field(..., description="Follow-up period length in days")
    follow_up_end_date: Optional[datetime] = Field(None, description="When the follow-up period ends (ISO 8601)")
    impact_scores: Optional[Dict[str, float]] = Field(None, description="Post-coaching scores measured during follow-up (null until computed)")
    overall_improved: Optional[bool] = Field(None, description="Whether overall improvement was detected (null until follow-up ends)")
    improvement_pct: Optional[float] = Field(None, description="Overall improvement percentage (null until follow-up ends)")
    targets_met: Optional[Dict[str, bool]] = Field(None, description="Which targets were met (null until follow-up ends)")
    notes: Optional[str] = Field(None, description="Coaching notes")
    coached_at: datetime = Field(..., description="When the coaching session took place (ISO 8601)")
    created_at: datetime = Field(..., description="Record creation timestamp (ISO 8601)")


class CoachingSessionListResponse(BaseModel):
    """Paginated list of coaching sessions."""
    total: int = Field(..., description="Total number of sessions matching the filters")
    sessions: List[CoachingSessionResponse] = Field(..., description="List of coaching sessions")
