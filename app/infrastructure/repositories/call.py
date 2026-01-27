"""
Call repository.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.call import Call
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class CallRepository(BaseRepository[CallORM, Call]):
    """Repository for Call entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, CallORM, Call)
    
    async def get_by_phone_number(
        self,
        company_id: UUID,
        phone_number: str,
    ) -> Optional[Call]:
        """Get call by phone number."""
        try:
            result = await self.session.execute(
                select(CallORM).where(
                    CallORM.company_id == company_id,
                    CallORM.phone_number == phone_number,
                ).order_by(CallORM.created_at.desc())
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting call by phone number: {e}")
            raise e
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Call]:
        """Get all calls for a company."""
        try:
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting calls by company: {e}")
            raise e

