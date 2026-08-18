"""
Coaching ORM models.

Tables for coaching dashboard: issues, strengths, objection details, and sessions.
"""
from sqlalchemy import String, Text, Float, Boolean, Integer, ForeignKey, JSON, DateTime, ARRAY, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CoachingIssueORM(Base):
    """Per-call coaching issue extracted from Shunya analysis."""

    __tablename__ = "coaching_issues"
    __table_args__ = (
        Index("ix_coaching_issues_user_company_created", "user_id", "company_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("call_analyses.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    how_to_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_sop_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class CoachingStrengthORM(Base):
    """Per-call coaching strength extracted from Shunya analysis."""

    __tablename__ = "coaching_strengths"
    __table_args__ = (
        Index("ix_coaching_strengths_user_company_created", "user_id", "company_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("call_analyses.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    behavior: Mapped[str] = mapped_column(Text, nullable=False)
    why_effective: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_sop_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class CallObjectionDetailORM(Base):
    """Per-call objection with overcome status for coaching aggregation."""

    __tablename__ = "call_objection_details"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("call_analyses.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_text: Mapped[str] = mapped_column(String(255), nullable=False)
    objection_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    overcome: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class CoachingSessionORM(Base):
    """Manager-created coaching session tracking."""

    __tablename__ = "coaching_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    rep_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    coach_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    focus_areas: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    targets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="in_progress")
    follow_up_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    follow_up_end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    impact_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_improved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    improvement_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    targets_met: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    coached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
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

    # Cycle tracking for 7-day auto-restarting coaching
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coaching_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    auto_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
