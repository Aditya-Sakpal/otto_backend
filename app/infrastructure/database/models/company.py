"""
Company ORM model.
"""
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CompanyORM(Base):
    """Company ORM model."""

    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    csr_sop_doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_sop_doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    users = relationship("UserORM", back_populates="company")
    calls = relationship("CallORM", back_populates="company")
    leads = relationship("LeadORM", back_populates="company")
    invitations = relationship("InvitationORM", back_populates="company")
    integrations = relationship("CompanyIntegrationORM", back_populates="company")
