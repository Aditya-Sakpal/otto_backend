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
