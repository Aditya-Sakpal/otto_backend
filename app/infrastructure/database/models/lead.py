"""
Lead ORM model.
"""
from sqlalchemy import String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class LeadORM(Base):
    """Lead ORM model."""

    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    contact_card_id: Mapped[UUID] = mapped_column(ForeignKey("contact_cards.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="new", index=True)
    deal_status: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_rep_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    deal_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    # Relationships
    company = relationship("CompanyORM", back_populates="leads")
    contact_card = relationship("ContactCardORM", back_populates="leads")
    calls = relationship("CallORM", back_populates="lead")

