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
    
    def _to_domain(self, orm_obj: LeadORM) -> Lead:
        """
        Convert ORM model to domain model.
        
        Handles enum conversions for status and deal_status.
        """
        from app.domain.enums import LeadStatus, DealStatus
        
        # Handle status conversion
        status = orm_obj.status
        if isinstance(status, str):
            try:
                status = LeadStatus(status.lower())
            except ValueError:
                # Try to find by value
                for enum_member in LeadStatus:
                    if enum_member.value.lower() == status.lower():
                        status = enum_member
                        break
                else:
                    # Default to NEW if unknown
                    logger.warning(f"Unknown lead status '{status}', defaulting to NEW")
                    status = LeadStatus.NEW
        
        # Handle deal_status conversion (can be None or invalid value)
        deal_status = orm_obj.deal_status
        if deal_status is not None and isinstance(deal_status, str):
            try:
                deal_status = DealStatus(deal_status.lower())
            except ValueError:
                # Try to find by value
                for enum_member in DealStatus:
                    if enum_member.value.lower() == deal_status.lower():
                        deal_status = enum_member
                        break
                else:
                    # If not found, set to None (deal_status is optional)
                    logger.warning(f"Unknown deal_status '{deal_status}', setting to None")
                    deal_status = None
        
        # Create domain model with converted enums
        return Lead(
            id=orm_obj.id,
            company_id=orm_obj.company_id,
            contact_card_id=orm_obj.contact_card_id,
            status=status,
            deal_status=deal_status,
            assigned_rep_id=orm_obj.assigned_rep_id,
            deal_size=orm_obj.deal_size,
            closed_at=orm_obj.closed_at,
            extra_metadata=orm_obj.extra_metadata,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )
    
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

