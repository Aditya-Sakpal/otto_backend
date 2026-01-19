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
    location_id: Mapped[str] = mapped_column(String, nullable=False)
    crm_api_encrypted_key: Mapped[str] = mapped_column(String, nullable=False)
    crm_provider: Mapped[str] = mapped_column(String, nullable=False)
    crm_company_id: Mapped[str | None] = mapped_column(String, nullable=True)
    voip_api_encrypted_key: Mapped[str] = mapped_column(String, nullable=False)
    voip_provider: Mapped[str] = mapped_column(String, nullable=False)
    voip_company_id: Mapped[str | None] = mapped_column(String, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    company = relationship("CompanyORM", back_populates="integrations")
