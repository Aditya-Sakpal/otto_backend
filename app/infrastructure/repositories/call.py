"""
Call repository.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, desc
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

    async def get_by_lead_id(self, lead_id: UUID) -> List[Call]:
        """Get all calls for a lead, ordered by most recent first."""
        try:
            query = (
                select(CallORM)
                .where(CallORM.lead_id == lead_id)
                .order_by(desc(CallORM.created_at))
            )
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting calls by lead: {e}")
            raise e

    async def get_by_st_call_id(self, company_id: UUID, st_call_id: str) -> Optional[Call]:
        """
        Find a call ingested from ServiceTitan Export by st_call_id in extra_metadata.

        Used for deduplication. Do not use get_all(limit=100): companies can have
        thousands of calls, so in-memory scans miss prior rows and ST re-sends create
        duplicate calls (same recording, same st_call_id).
        """
        if not st_call_id:
            return None
        try:
            result = await self.session.execute(
                select(CallORM)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.extra_metadata.op("->>")("st_call_id") == st_call_id,
                )
                .order_by(desc(CallORM.created_at))
                .limit(1)
            )
            orm_obj = result.scalar_one_or_none()
            return self._to_domain(orm_obj) if orm_obj else None
        except Exception as e:
            logger.error(f"Error getting call by st_call_id: {e}")
            raise e

