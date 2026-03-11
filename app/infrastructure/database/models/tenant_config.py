"""
Tenant Configuration ORM model.

Stores tenant configuration data locally, mirroring the Shunya tenant-config API.
"""
from datetime import datetime
from sqlalchemy import String, Text, JSON, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class TenantConfigORM(Base):
    """Tenant Configuration ORM model."""

    __tablename__ = "tenant_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), unique=True, index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)

    # Shunya config ID returned from the external API
    shunya_config_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Configuration data stored as JSON
    qualification_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    service_prioritization: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    custom_keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    qualification_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    business_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    service_area: Mapped[list | None] = mapped_column(JSON, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_services: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Metadata
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False
    )
