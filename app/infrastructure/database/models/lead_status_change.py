"""
Lead status change ORM model (audit log).
"""
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class LeadStatusChangeORM(Base):
    """Audit log for lead status/deal_status changes (e.g. admin manually qualified/unqualified)."""

    __tablename__ = "lead_status_changes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_status: Mapped[str] = mapped_column(String(100), nullable=False)
    old_deal_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_deal_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    lead = relationship("LeadORM", backref="status_changes")
    company = relationship("CompanyORM")
    changed_by = relationship("UserORM")
