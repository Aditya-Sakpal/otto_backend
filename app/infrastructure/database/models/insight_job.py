"""
Insight Generation Job ORM model.

Tracks Shunya insight generation jobs.
"""
from sqlalchemy import String, Text, ForeignKey, JSON, DateTime, Boolean, ARRAY, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, date
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class InsightJobORM(Base):
    """Insight generation job ORM model."""
    
    __tablename__ = "insight_jobs"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    shunya_job_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    
    # Job parameters
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    company_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    insight_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # Insight types: company, customer, objection, etc.
    
    # Job status
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", index=True)
    # Status values: queued, running, completed, failed
    
    # Options
    force_regenerate: Mapped[bool] = mapped_column(Boolean, default=False)
    include_inactive_customers: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Results
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
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
    company = relationship("CompanyORM")
