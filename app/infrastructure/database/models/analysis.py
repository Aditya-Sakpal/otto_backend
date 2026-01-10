"""
Call analysis ORM model.
"""
from sqlalchemy import String, Text, Float, ARRAY, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CallAnalysisORM(Base):
    """Call analysis ORM model."""
    
    __tablename__ = "call_analyses"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_id: Mapped[UUID] = mapped_column(ForeignKey("calls.id"), nullable=False, unique=True, index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    
    # Qualification
    qualification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_status: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Objections
    objections: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    objection_texts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    
    # SOP Compliance
    sop_stages_completed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sop_stages_missed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sop_compliance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Sentiment
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    
    # Raw analysis
    raw_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Pending actions (JSON strings stored as text array)
    pending_actions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.current_timestamp(),
    )
    
    # Relationships
    call = relationship("CallORM", back_populates="analysis")

