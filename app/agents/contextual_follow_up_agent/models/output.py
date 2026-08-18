"""
Output models for follow-up actions.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from contextual_follow_up_agent.models.enums import QueueType, ActionType


class ObjectionResponse(BaseModel):
    """A single objection with suggested response."""

    objection: str
    suggested_response: str


class RepNudge(BaseModel):
    """Structured call agenda for a sales rep."""

    opening_line: str
    objections: list[ObjectionResponse]
    close_approach: str
    key_talking_points: list[str]


class FollowUpAction(BaseModel):
    """A proposed follow-up action for one lead."""

    lead_id: UUID
    lead_name: str
    company_id: UUID
    queue_type: QueueType
    action_type: ActionType
    scheduled_for: datetime
    cadence_override: bool
    override_reason: str | None = None
    message_draft: str  # SMS text or formatted nudge
    rep_nudge: RepNudge | None = None
    shunya_context_used: list[str]  # Which fields informed the message
    attempt_number: int
