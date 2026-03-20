"""Proxy session ORM model.

Maps a lead+rep pair to a proxy phone number for masked communications.
One active session per lead-rep pair at a time (enforced by partial unique index).
"""
from sqlalchemy import String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class ProxySessionORM(Base):
    """Proxy session — binds a proxy number to a lead-rep conversation."""

    __tablename__ = "proxy_sessions"

    __table_args__ = (
        Index(
            "idx_proxy_sessions_active_lead_rep",
            "lead_id",
            "rep_user_id",
            unique=True,
            postgresql_where="status = 'active'",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rep_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    proxy_number_id: Mapped[UUID] = mapped_column(
        ForeignKey("proxy_numbers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    homeowner_phone: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rep_phone: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )
    closed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.current_timestamp(),
    )

    # Relationships
    company = relationship("CompanyORM")
    lead = relationship("LeadORM")
    rep = relationship("UserORM")
    proxy_number = relationship("ProxyNumberORM", back_populates="sessions")
    communications = relationship(
        "MaskedCommunicationORM",
        back_populates="session",
        order_by="MaskedCommunicationORM.created_at",
    )
