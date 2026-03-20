"""Proxy number ORM model.

Represents a Twilio phone number in the proxy pool. Each company has its own
pool of numbers. Numbers cycle through: available → assigned → cooldown → available.
"""
from sqlalchemy import String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class ProxyNumberORM(Base):
    """Proxy number pool entry."""

    __tablename__ = "proxy_numbers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_number: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    twilio_sid: Mapped[str] = mapped_column(String, nullable=False)
    friendly_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_assigned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    capabilities_sms: Mapped[bool] = mapped_column(Boolean, default=True)
    capabilities_voice: Mapped[bool] = mapped_column(Boolean, default=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    last_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    # Relationships
    company = relationship("CompanyORM")
    sessions = relationship("ProxySessionORM", back_populates="proxy_number")
