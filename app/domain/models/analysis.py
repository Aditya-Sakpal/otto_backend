"""
Analysis domain models.

Represents AI analysis results for calls.
"""
from typing import Optional, List
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel
from app.domain.enums import ObjectionType, SOPStage, AnalysisStatus


class CallAnalysis(BaseModel):
    """
    Call analysis model.
    
    Stores AI analysis results for a call:
    - Objections detected
    - SOP compliance
    - Qualification status
    - Sentiment
    """
    call_id: UUID = Field(..., description="Associated call ID")
    company_id: UUID = Field(..., description="Company/tenant ID")
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING, description="Analysis status")
    
    # Qualification
    qualification_status: Optional[str] = Field(None, description="Qualification status")
    booking_status: Optional[str] = Field(None, description="Booking status")
    
    # Objections
    objections: List[ObjectionType] = Field(default_factory=list, description="Detected objections")
    objection_texts: List[str] = Field(default_factory=list, description="Objection details")
    
    # SOP Compliance
    sop_stages_completed: List[SOPStage] = Field(default_factory=list, description="Completed SOP stages")
    sop_stages_missed: List[SOPStage] = Field(default_factory=list, description="Missed SOP stages")
    sop_compliance_score: Optional[float] = Field(None, description="SOP compliance score (0-1)")
    
    # Sentiment
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (-1 to 1)")
    
    # Summary
    summary: Optional[str] = Field(None, description="Call summary")
    key_points: List[str] = Field(default_factory=list, description="Key points")
    
    # Raw analysis data
    raw_analysis: Optional[dict] = Field(None, description="Raw analysis data from AI")
    
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

