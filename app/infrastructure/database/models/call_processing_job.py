"""
Call Processing Job ORM model.

Tracks Shunya call processing jobs (transcription, analysis, summarization).
"""
from sqlalchemy import String, Text, Integer, Float, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CallProcessingJobORM(Base):
    """Call processing job ORM model."""
    
    __tablename__ = "call_processing_jobs"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    call_id: Mapped[UUID] = mapped_column(ForeignKey("calls.id"), nullable=False, index=True)
    shunya_job_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    
    # Job status
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", index=True)
    # Status values: queued, running, completed, failed
    
    # Progress tracking
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_step: Mapped[str | None] = mapped_column(String, nullable=True)
    steps_completed: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps_remaining: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps_failed: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_completion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Results URLs
    summary_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Job metadata (renamed from 'metadata' as it's reserved in SQLAlchemy)
    job_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Contains: chunks_generated, summaries_generated, vectors_indexed, transcript_words, transcript_duration
    
    # Error handling
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_available: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_attempt: Mapped[int] = mapped_column(Integer, default=0)
    original_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Options
    skip_rag_indexing: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_summary_generation: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String, default="normal")
    
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
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
    call = relationship("CallORM", back_populates="processing_jobs")
    company = relationship("CompanyORM")
