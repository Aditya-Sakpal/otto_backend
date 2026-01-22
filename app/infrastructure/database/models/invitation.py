"""
Invitation ORM model.
"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base
from app.domain.enums import InvitationStatus, UserRole


class InvitationORM(Base):
    """Invitation ORM model."""

    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    inviter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserRole.CSR.value,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=InvitationStatus.PENDING.value,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("CompanyORM", back_populates="invitations")
    inviter = relationship("UserORM", foreign_keys=[inviter_id])

    # Indexes for common queries
    __table_args__ = (
        Index("idx_invitations_email_status", "email", "status"),
        Index("idx_invitations_token_status", "token", "status"),
    )
