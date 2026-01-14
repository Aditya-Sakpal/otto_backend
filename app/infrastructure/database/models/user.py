"""
User ORM model.
"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base
from app.domain.enums import UserRole


class UserORM(Base):
    """User ORM model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Store as VARCHAR to avoid enum name/value mismatch issues
    # We'll handle enum conversion in the repository layer
    role: Mapped[str] = mapped_column(
        String(length=50),
        nullable=False,
        default=UserRole.SALES_REP.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    company = relationship("CompanyORM", back_populates="users")

