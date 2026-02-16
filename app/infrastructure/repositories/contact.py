"""
Contact repository.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.contact import ContactCard
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class ContactRepository(BaseRepository[ContactCardORM, ContactCard]):
    """Repository for ContactCard entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ContactCardORM, ContactCard)

    async def find_or_create_by_phone(
        self,
        company_id: UUID,
        phone: str,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> ContactCard:
        """
        Find existing contact by phone or create new one.

        Args:
            company_id: Company ID
            phone: Primary phone number
            email: Optional email
            first_name: Optional first name
            last_name: Optional last name

        Returns:
            ContactCard domain model
        """
        try:
            # Try to find by primary phone
            result = await self.session.execute(
                select(ContactCardORM).where(
                    ContactCardORM.company_id == company_id,
                    ContactCardORM.primary_phone == phone
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update fields if provided
                updated = False
                if email and not existing.email:
                    existing.email = email
                    updated = True
                if first_name and not existing.first_name:
                    existing.first_name = first_name
                    updated = True
                if last_name and not existing.last_name:
                    existing.last_name = last_name
                    updated = True

                if updated:
                    await self.session.flush()
                    await self.session.refresh(existing)

                return self._to_domain(existing)

            # Create new contact
            contact = ContactCard(
                company_id=company_id,
                primary_phone=phone,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            return await self.create(contact)

        except Exception as e:
            logger.error(f"Error finding or creating contact by phone: {e}")
            raise e

    async def find_by_email(
        self,
        company_id: UUID,
        email: str,
    ) -> Optional[ContactCard]:
        """Find contact by email."""
        try:
            result = await self.session.execute(
                select(ContactCardORM).where(
                    ContactCardORM.company_id == company_id,
                    ContactCardORM.email == email
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error finding contact by email: {e}")
            raise e

    def _to_domain(self, orm_obj: ContactCardORM) -> ContactCard:
        """Convert ORM model to domain model."""
        return ContactCard.model_validate(orm_obj)

    def _to_orm(self, contact: ContactCard) -> ContactCardORM:
        """
        Convert domain model to ORM model, excluding fields
        that the DB manages or that shouldn't be in the constructor.
        """
        # Always exclude audit fields and the ID (if new)
        exclude_fields = {"created_at", "updated_at"}
        if not contact.id:
            exclude_fields.add("id")

        # model_dump(exclude=...) prevents 'created_at' from being passed to ContactCardORM(...)
        data = contact.model_dump(exclude=exclude_fields)
        return ContactCardORM(**data)
