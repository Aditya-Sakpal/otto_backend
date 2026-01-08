"""
Lead repository.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class LeadRepository(BaseRepository[LeadORM, Lead]):
    """Repository for Lead entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, LeadORM, Lead)
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get all leads for a company."""
        try:
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting leads by company: {e}")
            raise e
    
    async def get_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads by multiple status values."""
        try:
            result = await self.session.execute(
                select(LeadORM).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status.in_(statuses),
                ).offset(skip).limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by statuses: {e}")
            raise e
    
    async def get_unbooked(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get unbooked leads (qualified_unbooked status)."""
        try:
            return await self.get_by_statuses(
                company_id=company_id,
                statuses=["qualified_unbooked"],
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting unbooked leads: {e}")
            raise e
    
    async def get_by_priority(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads sorted by priority (hot > warm > new > others)."""
        try:
            # Priority order: hot > warm > new > others
            priority_order = {
                "hot": 1,
                "warm": 2,
                "new": 3,
            }
            
            result = await self.session.execute(
                select(LeadORM).where(
                    LeadORM.company_id == company_id,
                ).order_by(
                    func.case(
                        (LeadORM.status == "hot", 1),
                        (LeadORM.status == "warm", 2),
                        (LeadORM.status == "new", 3),
                        else_=4,
                    ),
                    LeadORM.created_at.desc(),
                ).offset(skip).limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by priority: {e}")
            raise e
    
    async def count_by_status(
        self,
        company_id: UUID,
        status: str,
    ) -> int:
        """Count leads by status."""
        try:
            result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status == status,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting leads by status: {e}")
            raise e
    
    async def count_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
    ) -> int:
        """Count leads by multiple statuses."""
        try:
            result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status.in_(statuses),
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting leads by statuses: {e}")
            raise e

