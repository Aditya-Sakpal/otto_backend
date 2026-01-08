"""
Lead domain model.

Represents a sales opportunity.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import LeadStatus, DealStatus


class Lead(BaseModel):
    """
    Lead model.
    
    Represents a sales opportunity that can progress through stages.
    """
    company_id: UUID = Field(..., description="Company/tenant ID")
    contact_card_id: UUID = Field(..., description="Associated contact")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Lead status")
    deal_status: Optional[DealStatus] = Field(None, description="Deal status (operational)")
    assigned_rep_id: Optional[UUID] = Field(None, description="Assigned sales rep")
    deal_size: Optional[float] = Field(None, description="Deal size in dollars")
    closed_at: Optional[datetime] = Field(None, description="When deal was closed")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")
    created_at: Optional[datetime] = Field(None, description="When lead was created")
    updated_at: Optional[datetime] = Field(None, description="When lead was last updated")

