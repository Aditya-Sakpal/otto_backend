"""
Conversation Phase Models

MongoDB models for semantic conversation phase detection.

Based on manager decisions Q49-Q60:
- Q49: 6 core phases (greeting, problem_discovery, qualification, objection_handling, closing, post_close)
- Q50: LLM-based semantic detection
- Q51: Overlap between phases allowed
- Q52: Either actual timestamps OR word-count estimation
- Q56: Flag missing phases, don't enforce
- Q57: Track time distribution across phases

Enhanced in v1.1:
- Added segment_mapped timestamp estimation method using diarized segments

Enhanced in v1.2:
- Hybrid alignment: LLM segments (accurate speakers) + API segments (accurate timestamps)
- New estimation methods: hybrid_aligned, api_segments_direct
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .enums import ConversationPhase


class PhaseTimestamp(BaseModel):
    """Timestamp information for a phase"""
    start_ms: int = Field(..., description="Start time in milliseconds")
    end_ms: int = Field(..., description="End time in milliseconds")
    duration_ms: int = Field(..., description="Duration in milliseconds")
    estimation_method: str = Field(
        default="word_count",
        description="Timestamp estimation method: "
                    "'hybrid_aligned' (best - LLM speakers + API timestamps), "
                    "'api_segments_direct' (good - uses API segments directly), "
                    "'segment_mapped' (legacy - uses provided segments), "
                    "'word_count' (fallback - linear interpolation), "
                    "'actual' (from transcription service)"
    )


class PhaseTranscriptSegment(BaseModel):
    """Transcript segment belonging to a phase"""
    start_word_index: int
    end_word_index: int
    speaker: Optional[str] = None
    text: str


class ConversationPhaseResult(BaseModel):
    """
    Detection result for a single phase.
    
    Per Q51: A phase can appear multiple times (overlap allowed).
    """
    phase: ConversationPhase
    detected: bool = Field(False, description="Was this phase detected in the call?")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Detection confidence 0-1")
    
    # Timestamp info (per Q52)
    timestamps: Optional[PhaseTimestamp] = None
    
    # Transcript segments belonging to this phase
    segments: List[PhaseTranscriptSegment] = Field(default_factory=list)
    
    # Key indicators that triggered detection
    key_phrases: List[str] = Field(default_factory=list, description="Phrases that indicated this phase")
    
    # Quality assessment
    quality_score: Optional[float] = Field(None, description="How well rep executed this phase (0-1)")
    quality_notes: Optional[str] = Field(None, description="Notes on phase execution quality")


class PhaseAnalytics(BaseModel):
    """
    Analytics for phase distribution (per Q57).
    """
    total_duration_ms: int = Field(0, description="Total call duration")
    
    # Time distribution per phase
    time_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Phase -> duration in ms"
    )
    
    # Percentage distribution
    percentage_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="Phase -> percentage of call"
    )
    
    # Phase metrics
    phases_detected: int = Field(0, description="Number of unique phases detected")
    phases_missing: List[str] = Field(default_factory=list, description="Phases not detected")
    
    # Phase ordering
    phase_sequence: List[str] = Field(
        default_factory=list,
        description="Chronological order of phases"
    )
    
    # Dominant phase
    dominant_phase: Optional[str] = Field(None, description="Phase with most time")
    
    # Insights
    insights: List[str] = Field(default_factory=list, description="Analytical observations")


class CallPhases(BaseModel):
    """
    Complete phase detection results for a call.
    
    Stored in MongoDB with call data.
    """
    call_id: str
    company_id: str
    
    # Detection results for each phase
    phases: Dict[str, ConversationPhaseResult] = Field(
        default_factory=dict,
        description="Phase name -> detection result"
    )
    
    # Analytics
    analytics: PhaseAnalytics
    
    # Quality assessment
    overall_flow_score: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description="How well the call flowed through phases"
    )
    
    # Missing phases flag (per Q56)
    has_missing_phases: bool = Field(False, description="Are any expected phases missing?")
    missing_phases: List[str] = Field(default_factory=list)
    
    # Processing metadata
    detection_method: str = Field(default="llm", description="llm or rule_based")
    model_used: Optional[str] = Field(None, description="LLM model used for detection")
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Version tracking
    algorithm_version: str = Field(default="1.2", description="Phase detection algorithm version (1.2 = hybrid alignment)")

    class Config:
        populate_by_name = True


class PhaseSearchQuery(BaseModel):
    """Query parameters for searching calls by phase"""
    company_id: str
    phase: Optional[ConversationPhase] = Field(None, description="Filter by specific phase")
    phase_detected: Optional[bool] = Field(None, description="Filter by phase presence")
    missing_phase: Optional[ConversationPhase] = Field(None, description="Find calls missing this phase")
    min_phase_duration_ms: Optional[int] = Field(None, description="Minimum phase duration")
    max_phase_duration_ms: Optional[int] = Field(None, description="Maximum phase duration")
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class CompanyPhaseDistribution(BaseModel):
    """Aggregated phase distribution across company"""
    company_id: str
    period_start: datetime
    period_end: datetime
    total_calls: int
    
    # Average time per phase
    avg_time_per_phase: Dict[str, float] = Field(
        default_factory=dict,
        description="Phase -> average duration in ms"
    )
    
    # Phase detection rates
    detection_rates: Dict[str, float] = Field(
        default_factory=dict,
        description="Phase -> % of calls with this phase"
    )
    
    # Most commonly missing phases
    commonly_missing: List[str] = Field(default_factory=list)
    
    # Best performing phase execution
    avg_quality_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Phase -> average quality score"
    )
