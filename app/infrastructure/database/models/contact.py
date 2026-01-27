"""
Contact ORM model.
"""
from sqlalchemy import String, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class ContactCardORM(Base):
    """Contact card ORM model."""
    
    __tablename__ = "contact_cards"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    primary_phone: Mapped[str] = mapped_column(String, nullable=False, index=True)
    secondary_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String, nullable=True)
    property_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    leads = relationship("LeadORM", back_populates="contact_card")
    calls = relationship("CallORM", back_populates="contact_card")

