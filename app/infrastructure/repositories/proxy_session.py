"""Repository for proxy session management."""
import traceback
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.logging import get_logger
from app.domain.models.proxy_session import ProxySession
from app.infrastructure.database.models.proxy_session import ProxySessionORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class ProxySessionRepository(BaseRepository[ProxySessionORM, ProxySession]):
    """Repository for ProxySession entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ProxySessionORM, ProxySession)

    async def get_active_by_lead_and_rep(
        self, lead_id: UUID, rep_user_id: UUID
    ) -> Optional[ProxySession]:
        """Find an active session for this lead-rep pair."""
        try:
            result = await self.session.execute(
                select(ProxySessionORM).where(
                    and_(
                        ProxySessionORM.lead_id == lead_id,
                        ProxySessionORM.rep_user_id == rep_user_id,
                        ProxySessionORM.status == "active",
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error finding active session by lead+rep: {e}")
            traceback.print_exc()
            raise

    async def get_active_by_lead(self, lead_id: UUID) -> Optional[ProxySession]:
        """Find any active session for a lead."""
        try:
            result = await self.session.execute(
                select(ProxySessionORM).where(
                    and_(
                        ProxySessionORM.lead_id == lead_id,
                        ProxySessionORM.status == "active",
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error finding active session by lead: {e}")
            traceback.print_exc()
            raise

    async def get_by_proxy_and_caller(
        self, proxy_number: str, caller_number: str
    ) -> Optional[ProxySessionORM]:
        """
        Given a proxy number and caller, find the active session.

        The caller could be either the rep or the homeowner.
        Returns the ORM object (not domain) for direct attribute access.
        """
        try:
            result = await self.session.execute(
                select(ProxySessionORM)
                .join(
                    ProxySessionORM.proxy_number,
                )
                .where(
                    and_(
                        ProxySessionORM.status == "active",
                        or_(
                            ProxySessionORM.rep_phone == caller_number,
                            ProxySessionORM.homeowner_phone == caller_number,
                        ),
                    )
                )
                .where(
                    # Filter by the proxy number on the session's assigned proxy
                    ProxySessionORM.proxy_number.has(phone_number=proxy_number)
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding session by proxy+caller: {e}")
            traceback.print_exc()
            raise

    async def get_active_sessions_for_rep(
        self, rep_user_id: UUID
    ) -> List[ProxySession]:
        """Get all active sessions for a rep (for mobile app display)."""
        try:
            result = await self.session.execute(
                select(ProxySessionORM)
                .where(
                    and_(
                        ProxySessionORM.rep_user_id == rep_user_id,
                        ProxySessionORM.status == "active",
                    )
                )
                .order_by(ProxySessionORM.created_at.desc())
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting active sessions for rep: {e}")
            traceback.print_exc()
            raise

    async def get_active_sessions_for_lead(
        self, lead_id: UUID
    ) -> List[ProxySession]:
        """Get all active sessions for a lead."""
        try:
            result = await self.session.execute(
                select(ProxySessionORM).where(
                    and_(
                        ProxySessionORM.lead_id == lead_id,
                        ProxySessionORM.status == "active",
                    )
                )
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting active sessions for lead: {e}")
            traceback.print_exc()
            raise

    async def close_session(self, session_id: UUID, reason: str) -> None:
        """Mark a session as closed."""
        try:
            await self.session.execute(
                update(ProxySessionORM)
                .where(ProxySessionORM.id == session_id)
                .values(
                    status="closed",
                    closed_reason=reason,
                    closed_at=datetime.now(timezone.utc),
                )
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error closing session: {e}")
            traceback.print_exc()
            raise

    async def close_sessions_for_lead(self, lead_id: UUID, reason: str) -> int:
        """Close all active sessions for a lead. Returns count closed."""
        try:
            result = await self.session.execute(
                update(ProxySessionORM)
                .where(
                    and_(
                        ProxySessionORM.lead_id == lead_id,
                        ProxySessionORM.status == "active",
                    )
                )
                .values(
                    status="closed",
                    closed_reason=reason,
                    closed_at=datetime.now(timezone.utc),
                )
            )
            await self.session.flush()
            return result.rowcount
        except Exception as e:
            logger.error(f"Error closing sessions for lead: {e}")
            traceback.print_exc()
            raise

    async def get_session_orm_by_id(self, session_id: UUID) -> Optional[ProxySessionORM]:
        """Get session ORM object by ID (for webhook handlers that need direct access)."""
        try:
            result = await self.session.execute(
                select(ProxySessionORM)
                .options(joinedload(ProxySessionORM.proxy_number))
                .where(ProxySessionORM.id == session_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting session ORM by ID: {e}")
            traceback.print_exc()
            raise
