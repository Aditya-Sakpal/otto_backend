"""
Smart Nudge ORM models.

Tables for AI-generated coaching nudges and per-user read tracking.
"""
from sqlalchemy import String, Text, Float, Boolean, Integer, ForeignKey, JSON, DateTime, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class SmartNudgeORM(Base):
    """AI-generated coaching nudge for managers about rep performance changes."""

    __tablename__ = "smart_nudges"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Who the nudge is about
    rep_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rep_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Nudge content
    nudge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Metric context
    metric_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_description: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Source references
    source_call_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(String), default=list)
    source_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coaching_sessions.id", ondelete="SET NULL"), nullable=True
    )
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Dedup fingerprint
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    # Lifecycle
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SmartNudgeReadORM(Base):
    """Per-user read/dismissed tracking for smart nudges."""

    __tablename__ = "smart_nudge_reads"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nudge_id: Mapped[UUID] = mapped_column(
        ForeignKey("smart_nudges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
