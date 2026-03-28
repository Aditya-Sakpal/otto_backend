"""
ORM for masked_communications (proxy / Twilio comms log).

Includes intent columns used by the Intent-to-Action engine for inbound SMS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class MaskedCommunicationORM(Base):
    """One row in masked_communications (SMS, call metadata, etc.)."""

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

    comm_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    from_number: Mapped[str] = mapped_column(String(32), nullable=False)
    to_number: Mapped[str] = mapped_column(String(32), nullable=False)
    proxy_number: Mapped[str] = mapped_column(String(32), nullable=False)

    twilio_call_sid: Mapped[str | None] = mapped_column(String(64))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    call_status: Mapped[str | None] = mapped_column(String(32))
    recording_url: Mapped[str | None] = mapped_column(Text)
    recording_sid: Mapped[str | None] = mapped_column(String(64))
    audio_url: Mapped[str | None] = mapped_column(Text)
    call_id: Mapped[UUID | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    twilio_message_sid: Mapped[str | None] = mapped_column(String(64), index=True)
    message_body: Mapped[str | None] = mapped_column(Text)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_homeowner_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    intent_label: Mapped[str | None] = mapped_column(String(64))
    confidence_score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
