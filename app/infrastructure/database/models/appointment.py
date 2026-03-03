"""
Appointment ORM model.
"""
from sqlalchemy import String, Text, DateTime, Float, ForeignKey, JSON, ARRAY, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class AppointmentORM(Base):
    """Appointment ORM model."""

    __tablename__ = "appointments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    contact_card_id: Mapped[UUID] = mapped_column(ForeignKey("contact_cards.id"), nullable=False, index=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_rep_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    interaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("calls.id"), nullable=True, index=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    objections: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    objection_texts: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    objections_total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_status: Mapped[str | None] = mapped_column(String, nullable=True)
    handled_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
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

