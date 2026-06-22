"""Pydantic schemas for Retell voice-agent tool API."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RetellCallContext(BaseModel):
    """Subset of Retell call object attached to tool invocations."""

    call_id: Optional[str] = None
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    transcript: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    agent_id: Optional[str] = None


class RetellToolRequest(BaseModel):
    """Body Retell sends when args_at_root is false."""

    name: Optional[str] = None
    args: dict[str, Any] = Field(default_factory=dict)
    call: Optional[RetellCallContext] = None


class SearchLeadResponse(BaseModel):
    found: bool = False
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    history_text: Optional[str] = None


class CustomerHistoryResponse(BaseModel):
    has_history: bool = False
    history_text: Optional[str] = None


class CreateLeadResponse(BaseModel):
    lead_id: str
    contact_id: str
    created: bool = True


class CurrentDateResponse(BaseModel):
    datetime: str


class AvailableSlotsResponse(BaseModel):
    slots: list[str]


class CreateAppointmentResponse(BaseModel):
    appointment_id: str


class GenericStatusResponse(BaseModel):
    status: str
    detail: Optional[str] = None


class SurfaceNextActionsResponse(BaseModel):
    actions: list[dict[str, str]]


class SaveCallSummaryResponse(BaseModel):
    call_id: str


class GenerateFollowupResponse(BaseModel):
    status: str = "queued"
    follow_up_id: Optional[str] = None
