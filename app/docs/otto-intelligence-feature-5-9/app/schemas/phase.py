"""
Phase Detection API Schemas

Pydantic schemas for conversation phase detection API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class PhaseResponse(BaseModel):
    """Response for a single phase"""
    phase: str
    detected: bool
    confidence: float
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    key_phrases: List[str]
    quality_score: Optional[float] = None


class CallPhasesResponse(BaseModel):
    """Response for call phases"""
    call_id: str
    company_id: str
    phases: Dict[str, dict]
    analytics: dict
    overall_flow_score: Optional[float] = None
    has_missing_phases: bool
    missing_phases: List[str]
    processed_at: datetime
    algorithm_version: str


class PhaseSearchResponse(BaseModel):
    """Response for phase search"""
    company_id: str
    phase: str
    total: int
    calls: List[dict]


class CompanyPhaseAnalyticsResponse(BaseModel):
    """Response for company phase analytics"""
    company_id: str
    period_start: datetime
    period_end: datetime
    total_calls: int
    avg_time_per_phase: Dict[str, float]
    detection_rates: Dict[str, float]
    commonly_missing: List[str]
    avg_quality_scores: Optional[Dict[str, float]] = None
    recommendations: Optional[List[str]] = None
