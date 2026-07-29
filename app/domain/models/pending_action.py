"""
Pending action domain model.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import PendingActionStatus


class PendingAction(BaseModel):
    """
    Pending action model.
    
    Represents an action item extracted from call or appointment analysis.
    Actions can be linked to calls, appointments, leads, and assigned to users.
    """
    company_id: UUID = Field(..., description="Company/tenant ID")
    lead_id: Optional[UUID] = Field(None, description="Associated lead ID")
    call_id: Optional[UUID] = Field(None, description="Associated call ID (for telephony calls)")
    appointment_id: Optional[UUID] = Field(None, description="Associated appointment ID (for appointment recordings)")
    action_type: str = Field(..., description="Type of action (free-string from Shunya)")
    raw_text: Optional[str] = Field(None, description="Raw action text/description")
    status: PendingActionStatus = Field(default=PendingActionStatus.PENDING, description="Action status")
    due_at: Optional[datetime] = Field(None, description="When action is due (UTC)")
    priority: Optional[int] = Field(None, description="Priority level (higher = more urgent)")
    owner_id: Optional[UUID] = Field(None, description="Assigned user ID (CSR or Sales Rep)")
    assigned_by_id: Optional[UUID] = Field(None, description="User who assigned this action (e.g. executive)")
    source: str = Field(default="shunya", description="Source of action (shunya, manual, system)")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")
