"""
Call ORM model.
"""
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CallORM(Base):
    """Call ORM model."""

    __tablename__ = "calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    contact_card_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact_cards.id"), nullable=True, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String, nullable=False, index=True)
    call_type: Mapped[str | None] = mapped_column(String, nullable=True)
    missed_call: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), name="handled_by_user_id", nullable=True, index=True)
    handled_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    interaction_type: Mapped[str | None] = mapped_column(String, nullable=True, default="call")
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
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    answered_by_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_source: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    company = relationship("CompanyORM", back_populates="calls")
    contact_card = relationship("ContactCardORM", back_populates="calls")
    lead = relationship("LeadORM", back_populates="calls")
    analysis = relationship("CallAnalysisORM", back_populates="call", uselist=False)
    processing_jobs = relationship("CallProcessingJobORM", back_populates="call")

