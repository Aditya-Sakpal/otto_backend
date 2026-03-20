"""Masked communication ORM model.

Stores individual call or SMS records within a proxy session.
Each record represents one direction of one communication event.
"""
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class MaskedCommunicationORM(Base):
    """Individual call or SMS log entry within a proxy session."""

    __tablename__ = "masked_communications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("proxy_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comm_type: Mapped[str] = mapped_column(String, nullable=False)  # call | sms
    direction: Mapped[str] = mapped_column(
        String, nullable=False
    )  # rep_to_homeowner | homeowner_to_rep
    from_number: Mapped[str] = mapped_column(String, nullable=False)
    to_number: Mapped[str] = mapped_column(String, nullable=False)
    proxy_number: Mapped[str] = mapped_column(String, nullable=False)

    # Call-specific
    twilio_call_sid: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_status: Mapped[str | None] = mapped_column(String, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_sid: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # SMS-specific
    twilio_message_sid: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Intelligence layer
    is_homeowner_reply: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    # Relationships
    session = relationship("ProxySessionORM", back_populates="communications")
    call = relationship("CallORM")
