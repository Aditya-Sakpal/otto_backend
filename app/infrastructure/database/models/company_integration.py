"""
Company integration ORM model.
"""
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base

class CompanyIntegrationORM(Base):
    """Company integration ORM model."""

    __tablename__ = "company_integrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)

    # Optional integration fields
    location_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # CRM integration fields (all optional)
    crm_api_encrypted_key: Mapped[str | None] = mapped_column(String, nullable=True)
    crm_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    crm_company_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # VoIP integration fields (all optional)
    voip_api_encrypted_key: Mapped[str | None] = mapped_column(String, nullable=True)
    voip_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    voip_company_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Additional metadata
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    company = relationship("CompanyORM", back_populates="integrations")
