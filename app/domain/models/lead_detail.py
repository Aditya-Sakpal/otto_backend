"""
Lead detail domain model.

Comprehensive lead details for the lead details page.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel


class ContactInfo(BaseModel):
    """Contact information."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_phone: str
    email: Optional[str] = None


class AgentInfo(BaseModel):
    """Assigned agent information."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str


class OverallEngagement(BaseModel):
    """Overall engagement section."""
    summary: Optional[str] = Field(None, description="Aggregated summary from all call analyses")
    key_points: List[str] = Field(default_factory=list, description="Key points from call analyses")
    action_items: List[str] = Field(default_factory=list, description="Pending action items")
    appointment_status: Optional[str] = Field(None, description="Appointment status based on lead status")


class Conversation(BaseModel):
    """Conversation (call) with the lead."""
    id: UUID
    call_type: Optional[str] = None
    phone_number: str
    duration_seconds: Optional[int] = None
    missed_call: bool = False
    transcript: Optional[str] = None
    call_recording_url: Optional[str] = Field(None, description="Audio recording URL")
    handled_by_user_id: Optional[UUID] = None
    created_at: datetime
    
    # Analysis data (if available)
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    sop_compliance_score: Optional[float] = None
    qualification_status: Optional[str] = None
    booking_status: Optional[str] = None


class LeadDetail(BaseModel):
    """Detailed lead information for lead details page."""
    # Basic info
    id: UUID
    company_id: UUID
    status: str
    deal_status: Optional[str] = None
    pipeline_stage: Optional[str] = None
    deal_size: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Contact info
    contact: ContactInfo
    
    # Agent info
    agent: Optional[AgentInfo] = None
    
    # Overall engagement
    overall_engagement: OverallEngagement
    
    # Conversations (sorted by most recent first)
    conversations: List[Conversation] = Field(default_factory=list, description="All conversations with this lead, sorted by most recent first")
