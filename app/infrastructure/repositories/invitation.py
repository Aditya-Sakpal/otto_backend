"""
Invitation repository.

Data access layer for Invitation entities.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.invitation import Invitation
from app.domain.enums import InvitationStatus
from app.infrastructure.database.models.invitation import InvitationORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class InvitationRepository(BaseRepository[InvitationORM, Invitation]):
    """Repository for Invitation entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, InvitationORM, Invitation)

    async def get_by_token(self, token: str) -> Optional[Invitation]:
        """
        Get invitation by token.

        Args:
            token: Invitation token

        Returns:
            Invitation domain model or None
        """
        try:
            result = await self.session.execute(
                select(InvitationORM).where(InvitationORM.token == token)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting invitation by token: {e}")
            raise e

    async def get_by_email_and_company(
        self,
        email: str,
        company_id: UUID,
        status: Optional[InvitationStatus] = None,
    ) -> List[Invitation]:
        """
        Get invitations by email and company.

        Args:
            email: Email address
            company_id: Company ID
            status: Optional status filter

        Returns:
            List of Invitation domain models
        """
        try:
            query = select(InvitationORM).where(
                and_(
                    InvitationORM.email == email,
                    InvitationORM.company_id == company_id,
                )
            )

            if status:
                query = query.where(InvitationORM.status == status.value)

            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting invitations by email and company: {e}")
            raise e

    async def get_pending_by_email(self, email: str) -> List[Invitation]:
        """
        Get all pending invitations for an email.

        Args:
            email: Email address

        Returns:
            List of pending Invitation domain models
        """
        try:
            return await self.get_all(
                skip=0,
                limit=100,
                filters={
                    "email": email,
                    "status": InvitationStatus.PENDING.value,
                },
            )
        except Exception as e:
            logger.error(f"Error getting pending invitations by email: {e}")
            raise e

    async def update_status(
        self,
        invitation_id: UUID,
        status: InvitationStatus,
        accepted_at: Optional[datetime] = None,
    ) -> Optional[Invitation]:
        """
        Update invitation status.

        Args:
            invitation_id: Invitation ID
            status: New status
            accepted_at: Optional acceptance timestamp

        Returns:
            Updated Invitation domain model or None
        """
        try:
            orm_obj = await self.session.get(InvitationORM, invitation_id)
            if not orm_obj:
                return None

            orm_obj.status = status.value
            if accepted_at:
                orm_obj.accepted_at = accepted_at

            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error updating invitation status: {e}")
            raise e

    async def expire_old_invitations(self) -> int:
        """
        Mark expired invitations as expired.

        Returns:
            Number of invitations expired
        """
        try:
            now = datetime.now(timezone.utc)
            result = await self.session.execute(
                select(InvitationORM).where(
                    and_(
                        InvitationORM.status == InvitationStatus.PENDING.value,
                        InvitationORM.expires_at < now,
                    )
                )
            )
            orm_objs = result.scalars().all()

            count = 0
            for orm_obj in orm_objs:
                orm_obj.status = InvitationStatus.EXPIRED.value
                count += 1

            if count > 0:
                await self.session.flush()

            return count
        except Exception as e:
            logger.error(f"Error expiring old invitations: {e}")
            raise e

    def _to_domain(self, orm_obj: InvitationORM) -> Invitation:
        """
        Convert ORM model to domain model.

        Handles status enum conversion.
        """
        # Convert status string to enum
        try:
            status = InvitationStatus(orm_obj.status)
        except ValueError:
            logger.warning(f"Invalid invitation status: {orm_obj.status}, defaulting to PENDING")
            status = InvitationStatus.PENDING

        return Invitation(
            id=orm_obj.id,
            email=orm_obj.email,
            company_id=orm_obj.company_id,
            inviter_id=orm_obj.inviter_id,
            token=orm_obj.token,
            status=status,
            expires_at=orm_obj.expires_at,
            created_at=orm_obj.created_at,
            accepted_at=orm_obj.accepted_at,
        )
