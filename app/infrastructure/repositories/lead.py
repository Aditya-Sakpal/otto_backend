"""
Lead repository.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, or_, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.enums import DealStatus
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class LeadRepository(BaseRepository[LeadORM, Lead]):
    """Repository for Lead entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LeadORM, Lead)

    async def get_by_id(self, id: UUID) -> Optional[Lead]:
        """Get lead by ID with call audio URLs."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(selectinload(LeadORM.calls))
                .where(LeadORM.id == id)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting lead by ID: {e}")
            raise e

    def _to_domain(self, orm_obj: LeadORM) -> Lead:
        """Convert ORM model to domain model with call audio URLs."""
        # Extract audio URLs from associated calls
        call_audio_urls = None
        if orm_obj.calls:
            call_audio_urls = [
                call.audio_url for call in orm_obj.calls
                if call.audio_url is not None
            ]
            # Return None if empty list instead of empty list
            if not call_audio_urls:
                call_audio_urls = None

        # Validate and convert deal_status
        deal_status = None
        if orm_obj.deal_status:
            try:
                deal_status = DealStatus(orm_obj.deal_status)
            except ValueError:
                logger.warning(
                    f"Invalid deal_status value: {orm_obj.deal_status} for lead {orm_obj.id}, "
                    "setting to None"
                )
                deal_status = None

        # Convert to domain model
        lead_data = {
            "id": orm_obj.id,
            "company_id": orm_obj.company_id,
            "contact_card_id": orm_obj.contact_card_id,
            "status": orm_obj.status,
            "deal_status": deal_status,
            "assigned_rep_id": orm_obj.assigned_rep_id,
            "deal_size": orm_obj.deal_size,
            "closed_at": orm_obj.closed_at,
            "extra_metadata": orm_obj.extra_metadata,
            "call_audio_urls": call_audio_urls,
            "created_at": orm_obj.created_at,
            "updated_at": orm_obj.updated_at,
        }
        return Lead(**lead_data)

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get all leads for a company."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(selectinload(LeadORM.calls))
                .where(LeadORM.company_id == company_id)
                .offset(skip)
                .limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
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
                select(LeadORM)
                .options(selectinload(LeadORM.calls))
                .where(
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
                select(LeadORM)
                .options(selectinload(LeadORM.calls))
                .where(
                    LeadORM.company_id == company_id,
                ).order_by(
                    case(
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

