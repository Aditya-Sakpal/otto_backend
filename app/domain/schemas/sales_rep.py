"""
Sales rep API schemas.

Request/response models for sales rep endpoints (e.g. pending leads).
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class PendingLeadCustomer(BaseModel):
    """Customer block in a pending lead result."""

    full_name: Optional[str] = Field(None, description="Contact full name")
    phone: Optional[str] = Field(None, description="Primary phone")
    address: Optional[str] = Field(None, description="Full address")


class PendingLeadSalesContext(BaseModel):
    """Sales context block in a pending lead result."""

    intent: Optional[str] = Field(None, description="Intent (e.g. Replacement)")
    primary_objection: Optional[str] = Field(None, description="Primary objection (e.g. Price/Insurance)")
    last_touched: Optional[datetime] = Field(None, description="Last touch timestamp")
    follow_up_count: int = Field(0, description="Number of follow-ups")


class PendingLeadAppointment(BaseModel):
    """Appointment block in a pending lead result."""

    assigned_rep: Optional[str] = Field(None, description="Assigned rep display name")
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled start time")
    recording_url: Optional[str] = Field(None, description="Call recording URL")
    transcript_id: Optional[str] = Field(None, description="Transcript/call thread ID")


class PendingLeadWorkflow(BaseModel):
    """Workflow block in a pending lead result."""

    tasks: List[str] = Field(default_factory=list, description="Task list (e.g. next_steps)")
    summary_notes: Optional[str] = Field(None, description="Summary notes from analysis")


class PendingLeadResultItem(BaseModel):
    """Single item in pending leads results."""

    id: UUID = Field(..., description="Lead ID")
    urgency_level: Optional[str] = Field(None, description="high, medium, low")
    customer: PendingLeadCustomer = Field(..., description="Customer info")
    sales_context: PendingLeadSalesContext = Field(..., description="Sales context")
    appointment: PendingLeadAppointment = Field(..., description="Appointment info")
    workflow: PendingLeadWorkflow = Field(..., description="Workflow tasks and notes")


class PendingLeadsResponse(BaseModel):
    """Response for GET /sales-rep/pending-leads."""

    total_count: int = Field(..., description="Total number of leads matching filters")
    count: int = Field(..., description="Number of items in this page")
    results: List[PendingLeadResultItem] = Field(default_factory=list, description="Lead items")


# ── Unified rep work queue ────────────────────────────────────────────────
# Composes three existing rep-scoped surfaces (Action Center tasks, unresolved
# appointments, pending leads) into one response. Reuses ActionCenter* and
# PendingLeadResultItem models — no new ranking/scoring.

from app.domain.schemas.tasks import (  # noqa: E402  (avoid circular import at top)
    ActionCenterItem,
    ActionCenterGroup,
    ActionCenterSummary,
)


class UnresolvedAppointmentItem(BaseModel):
    """A ran/past appointment whose outcome is still open (blocks closure)."""

    appointment_id: UUID
    lead_id: Optional[UUID] = None
    contact_card_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    scheduled_start: datetime
    outcome: Optional[str] = None
    analysis_status: Optional[str] = None
    location_address: Optional[str] = None


class WorkQueueSectionCounts(BaseModel):
    """Per-section item counts for the work queue."""

    tasks: int = 0
    unresolved_appointments: int = 0
    pending_leads: int = 0


class WorkQueueResponse(BaseModel):
    """Unified rep work queue: the rep's entire actionable workload in one call."""

    generated_at: datetime
    company_id: UUID
    owner_id: UUID
    next_action: Optional[ActionCenterItem] = None
    task_summary: ActionCenterSummary
    tasks: List[ActionCenterGroup] = Field(default_factory=list)
    unresolved_appointments: List[UnresolvedAppointmentItem] = Field(default_factory=list)
    pending_leads: List[PendingLeadResultItem] = Field(default_factory=list)
    section_counts: WorkQueueSectionCounts


# ── Missed-call recovery dashboard ────────────────────────────────────────
# Rep-scoped view over call_back PendingActions. Reuses SourceCallInfo (caller)
# and the Action Center countdown fields. No new tables/metrics.

from app.domain.schemas.tasks import SourceCallInfo  # noqa: E402


class MissedCallItem(BaseModel):
    """A single missed-call callback task with countdown."""

    pending_action_id: UUID
    call_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    raw_text: Optional[str] = None
    status: str
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None  # = pending_action.updated_at when completed
    minutes_until_due: Optional[int] = None  # negative = overdue
    urgency_tier: Optional[str] = None       # overdue|due_now|due_soon|later_today|upcoming
    overdue: bool = False
    source_call: Optional[SourceCallInfo] = None


class MissedCallRecoveryResponse(BaseModel):
    """Rep missed-call recovery dashboard."""

    generated_at: datetime
    company_id: UUID
    owner_id: UUID
    pending_callbacks: List[MissedCallItem] = Field(default_factory=list)
    completed_callbacks: List[MissedCallItem] = Field(default_factory=list)
    # Company-wide callbacks with no assigned owner (true missed calls) — surfaced
    # for triage so they are never invisible. Claimable by any rep/CSR.
    unassigned_callbacks: List[MissedCallItem] = Field(default_factory=list)
    pending_count: int = 0           # assigned-to-owner only (unchanged meaning)
    overdue_count: int = 0           # assigned-to-owner only (unchanged meaning)
    completed_today_count: int = 0
    unassigned_count: int = 0
    unassigned_overdue_count: int = 0
