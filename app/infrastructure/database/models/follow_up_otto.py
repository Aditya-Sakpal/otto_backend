"""
Follow-up Otto ORM model.

Stores GoMotto/contextual follow-up messages for the Follow Up tab:
sent and scheduled messages, AI reasoning, and engagement status.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class FollowUpOttoORM(Base):
    """
    One follow-up message (sent or scheduled) from the contextual follow-up agent.

    Used to populate the lead Follow Up tab: message body, sent/scheduled time,
    status, "Why GoMotto sent this" reasoning, and delivery/reply state.
    """

    __tablename__ = "follow_up_otto"

    # Identity
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Message
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'sms_to_lead' | 'nudge_sales_rep'

    # Rep nudge sections (only for action_type = nudge_sales_rep)
    opening_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    objections: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # [{"objection": "", "suggested_response": ""}, ...]
    key_talking_points: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # ["point1", "point2", ...]
    close_approach: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External IDs (Twilio SID, etc.)
    external_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    pending_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pending_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Timing
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # when it was/will be sent
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status: proposed | pending | scheduled | sent | failed | overdue | cancelled | paused | opted_out | dormant
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "Why GoMotto sent this" — list of reason bullets
    ai_reasoning: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # e.g. ["reason1", "reason2"]
    queue_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # qualified_unbooked | appointment_ran
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Recipient (for rep nudges)
    assigned_rep_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Audit
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
    lead = relationship("LeadORM")
    company = relationship("CompanyORM")
    assigned_rep = relationship("UserORM", foreign_keys=[assigned_rep_id])
    pending_action = relationship("PendingActionORM", foreign_keys=[pending_action_id])

    __table_args__ = (
        Index("idx_follow_up_otto_lead_status", "lead_id", "status"),
        Index("idx_follow_up_otto_company_lead", "company_id", "lead_id"),
        Index("idx_follow_up_otto_scheduled_status", "scheduled_at", "status"),
    )
