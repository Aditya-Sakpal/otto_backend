"""
Pydantic models for assembled lead context.

These models carry the data through the pipeline:
scan → assemble → timing → cadence → message generation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LeadProfile(BaseModel):
    """Core lead information from PG."""

    lead_id: UUID
    company_id: UUID
    company_name: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    property_snapshot: dict | None = None
    pipeline_stage: str
    lead_status: str
    assigned_rep_id: UUID | None = None
    queue_entered_at: datetime  # created_at for Q1, scheduled_start for Q2
    appointment_id: UUID | None = None  # Only for Queue 2

    @property
    def contact_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else "Homeowner"


class AnalysisContext(BaseModel):
    """Shunya analysis data from call_analyses / appointments tables."""

    summary: str | None = None
    key_points: list[str] | None = None
    action_items: list[str] | None = None
    next_steps: list[str] | None = None
    pending_actions: list[dict] | None = None  # JSON from call_analyses
    objections: list[str] | None = None  # Category strings
    objection_texts: list[str] | None = None  # Actual customer statements
    objections_total_count: int = 0
    sentiment_score: float | None = None
    qualification_status: str | None = None
    booking_status: str | None = None
    service_requested: str | None = None
    property_details: dict | None = None
    follow_up_required: bool | None = None
    follow_up_reason: str | None = None
    bant_need: float | None = None
    bant_budget: float | None = None
    bant_timeline: float | None = None
    bant_authority: float | None = None
    overall_score: float | None = None

    @property
    def has_meaningful_context(self) -> bool:
        """Check if there's enough Shunya data to generate a contextual message."""
        return bool(self.summary) or bool(self.objection_texts)

    @property
    def lead_score(self) -> int:
        """Compute a 0-100 lead score from BANT components."""
        scores = [s for s in [self.bant_need, self.bant_budget,
                               self.bant_timeline, self.bant_authority] if s is not None]
        if not scores:
            return 0
        return int((sum(scores) / len(scores)) * 100)

    @property
    def primary_objection(self) -> str | None:
        """Get the first objection text, if any."""
        if self.objection_texts:
            return self.objection_texts[0]
        return None


class FollowUpHistoryEntry(BaseModel):
    """A single previous follow-up attempt."""

    attempt_number: int
    action_type: str
    scheduled_at: str
    sent_at: str | None = None
    message_content: str
    status: str


class FollowUpHistory(BaseModel):
    """Previous follow-up attempts for a lead in a specific queue."""

    entries: list[FollowUpHistoryEntry] = []

    @property
    def total_attempts(self) -> int:
        return len(self.entries)

    @property
    def last_message(self) -> str | None:
        if self.entries:
            return self.entries[-1].message_content
        return None

    @property
    def last_attempt_at(self) -> str | None:
        if self.entries:
            return self.entries[-1].scheduled_at
        return None

    @property
    def has_response(self) -> bool:
        """Check if any attempt got a response (status != sent/failed)."""
        return any(e.status not in ("sent", "failed", "proposed", "pending")
                   for e in self.entries)


class AssembledContext(BaseModel):
    """Full context for a single lead ready for processing."""

    lead: LeadProfile
    analysis: AnalysisContext | None = None
    history: FollowUpHistory
    queue_type: str  # QueueType value
    attempt_number: int  # Next attempt (1, 2, or 3)
    days_since_event: int  # Days since queue_entered_at
