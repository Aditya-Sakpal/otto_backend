"""
Pending action ORM model.
"""
from sqlalchemy import String, Text, Integer, ForeignKey, JSON, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class PendingActionORM(Base):
    """Pending action ORM model."""
    
    __tablename__ = "pending_actions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    call_id: Mapped[UUID | None] = mapped_column(ForeignKey("calls.id"), nullable=True, index=True)
    appointment_id: Mapped[UUID | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    assigned_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="shunya")
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
    
    # Relationships (back_populates not set as other models may not have these relationships)
    company = relationship("CompanyORM")
    lead = relationship("LeadORM")
    call = relationship("CallORM")
    appointment = relationship("AppointmentORM")
    owner = relationship("UserORM", foreign_keys=[owner_id])
    assigned_by = relationship("UserORM", foreign_keys=[assigned_by_id])
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_pending_actions_company_status", "company_id", "status"),
        Index("idx_pending_actions_lead_status", "lead_id", "status"),
        Index("idx_pending_actions_owner_status", "owner_id", "status"),
        Index("idx_pending_actions_due_at", "due_at"),
        Index("idx_pending_actions_urgency", "due_at", "priority"),
    )
