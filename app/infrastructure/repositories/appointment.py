"""
Appointment repository.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.appointment import Appointment
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class AppointmentRepository(BaseRepository[AppointmentORM, Appointment]):
    """Repository for Appointment entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, AppointmentORM, Appointment)
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company."""
        try:
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting appointments by company: {e}")
            raise e
    
    async def count_by_company(
        self,
        company_id: UUID,
    ) -> int:
        """Count appointments for a company."""
        try:
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting appointments: {e}")
            raise e
    
    async def count_by_outcome(
        self,
        company_id: UUID,
        outcome: str,
    ) -> int:
        """Count appointments by outcome."""
        try:
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.outcome == outcome,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting appointments by outcome: {e}")
            raise e

