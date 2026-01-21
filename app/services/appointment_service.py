"""
Appointment service.

Provides business logic for managing appointments:
- CRUD operations
- Listing by company, lead, or assigned sales rep
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.appointment import Appointment
from app.domain.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
)
from app.infrastructure.repositories.appointment import AppointmentRepository

logger = get_logger(__name__)


class AppointmentService:
    """Service for appointment-related operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.appointment_repo = AppointmentRepository(session)

    async def get_by_id(self, appointment_id: UUID) -> Optional[Appointment]:
        """Get appointment by ID."""
        return await self.appointment_repo.get_by_id(appointment_id)

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company."""
        return await self.appointment_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """
        Get all appointments for a company assigned to a specific sales rep.

        Args:
            company_id: Company/tenant ID
            assigned_rep_id: Assigned sales rep user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
        """
        return await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_lead(
        self,
        lead_id: UUID,
    ) -> Optional[Appointment]:
        """Get appointment by associated lead ID."""
        return await self.appointment_repo.get_by_lead_id(lead_id)

    async def create(self, appointment: Appointment) -> Appointment:
        """Create a new appointment from a domain model."""
        try:
            return await self.appointment_repo.create(appointment)
        except Exception as e:
            logger.error(f"Error creating appointment: {e}")
            raise

    async def create_from_schema(
        self,
        data: AppointmentCreate,
    ) -> Appointment:
        """Create a new appointment from an API schema."""
        try:
            appointment = Appointment(
                **data.model_dump(),
            )
            return await self.appointment_repo.create(appointment)
        except Exception as e:
            logger.error(f"Error creating appointment from schema: {e}")
            raise

    async def update(
        self,
        appointment_id: UUID,
        data: AppointmentUpdate,
    ) -> Optional[Appointment]:
        """Update an existing appointment from an API schema."""
        try:
            existing = await self.appointment_repo.get_by_id(appointment_id)
            if not existing:
                return None

            update_dict = data.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                setattr(existing, key, value)
            existing.mark_updated()

            return await self.appointment_repo.update(appointment_id, existing)
        except Exception as e:
            logger.error(f"Error updating appointment: {e}")
            raise

    async def delete(self, appointment_id: UUID) -> bool:
        """Delete an appointment."""
        try:
            return await self.appointment_repo.delete(appointment_id)
        except Exception as e:
            logger.error(f"Error deleting appointment: {e}")
            raise

