"""Repository for proxy number pool management."""
import traceback
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.proxy_number import ProxyNumber
from app.infrastructure.database.models.proxy_number import ProxyNumberORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)

# Minimum days before a released number can be reassigned
COOLDOWN_DAYS = 30


class ProxyNumberRepository(BaseRepository[ProxyNumberORM, ProxyNumber]):
    """Repository for ProxyNumber entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ProxyNumberORM, ProxyNumber)

    async def get_available_for_company(self, company_id: UUID) -> Optional[ProxyNumber]:
        """
        Get first available proxy number for a company.

        Conditions: is_active=True, is_assigned=False, and past cooldown period.
        Uses FOR UPDATE SKIP LOCKED to handle concurrent allocation safely.
        """
        try:
            cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
            query = (
                select(ProxyNumberORM)
                .where(
                    and_(
                        ProxyNumberORM.company_id == company_id,
                        ProxyNumberORM.is_active == True,
                        ProxyNumberORM.is_assigned == False,
                        # Number must either have never been released, or be past cooldown
                        (
                            (ProxyNumberORM.last_released_at == None)
                            | (ProxyNumberORM.last_released_at < cooldown_cutoff)
                        ),
                    )
                )
                .order_by(ProxyNumberORM.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await self.session.execute(query)
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting available proxy number: {e}")
            traceback.print_exc()
            raise

    async def mark_assigned(self, proxy_number_id: UUID) -> None:
        """Mark a proxy number as assigned."""
        try:
            await self.session.execute(
                update(ProxyNumberORM)
                .where(ProxyNumberORM.id == proxy_number_id)
                .values(is_assigned=True, last_released_at=None)
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error marking proxy number assigned: {e}")
            traceback.print_exc()
            raise

    async def mark_unassigned(self, proxy_number_id: UUID) -> None:
        """Mark a proxy number as unassigned and set cooldown timestamp."""
        try:
            await self.session.execute(
                update(ProxyNumberORM)
                .where(ProxyNumberORM.id == proxy_number_id)
                .values(
                    is_assigned=False,
                    last_released_at=datetime.now(timezone.utc),
                )
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error marking proxy number unassigned: {e}")
            traceback.print_exc()
            raise

    async def get_by_phone_number(self, phone_number: str) -> Optional[ProxyNumber]:
        """Look up a proxy number record by E.164 phone number."""
        try:
            result = await self.session.execute(
                select(ProxyNumberORM).where(
                    ProxyNumberORM.phone_number == phone_number
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting proxy number by phone: {e}")
            traceback.print_exc()
            raise

    async def count_available(self, company_id: UUID) -> int:
        """Count available (unassigned, active, past cooldown) numbers for a company."""
        try:
            cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
            result = await self.session.execute(
                select(func.count(ProxyNumberORM.id)).where(
                    and_(
                        ProxyNumberORM.company_id == company_id,
                        ProxyNumberORM.is_active == True,
                        ProxyNumberORM.is_assigned == False,
                        (
                            (ProxyNumberORM.last_released_at == None)
                            | (ProxyNumberORM.last_released_at < cooldown_cutoff)
                        ),
                    )
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting available proxy numbers: {e}")
            traceback.print_exc()
            raise

    async def count_by_company(self, company_id: UUID) -> dict:
        """Get pool statistics for a company."""
        try:
            total_result = await self.session.execute(
                select(func.count(ProxyNumberORM.id)).where(
                    and_(
                        ProxyNumberORM.company_id == company_id,
                        ProxyNumberORM.is_active == True,
                    )
                )
            )
            total = total_result.scalar() or 0

            assigned_result = await self.session.execute(
                select(func.count(ProxyNumberORM.id)).where(
                    and_(
                        ProxyNumberORM.company_id == company_id,
                        ProxyNumberORM.is_active == True,
                        ProxyNumberORM.is_assigned == True,
                    )
                )
            )
            assigned = assigned_result.scalar() or 0

            available = await self.count_available(company_id)

            return {
                "total": total,
                "assigned": assigned,
                "available": available,
                "cooling_down": total - assigned - available,
            }
        except Exception as e:
            logger.error(f"Error getting pool statistics: {e}")
            traceback.print_exc()
            raise
