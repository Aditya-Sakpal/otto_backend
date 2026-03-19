"""Repository for rep phone registration."""
import traceback
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.rep_phone import RepPhone
from app.infrastructure.database.models.rep_phone import RepPhoneORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class RepPhoneRepository(BaseRepository[RepPhoneORM, RepPhone]):
    """Repository for RepPhone entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RepPhoneORM, RepPhone)

    async def get_verified_primary(self, user_id: UUID) -> Optional[RepPhone]:
        """Get the verified primary phone for a user."""
        try:
            result = await self.session.execute(
                select(RepPhoneORM).where(
                    and_(
                        RepPhoneORM.user_id == user_id,
                        RepPhoneORM.is_verified == True,
                        RepPhoneORM.is_primary == True,
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting verified primary phone: {e}")
            traceback.print_exc()
            raise

    async def get_by_user(self, user_id: UUID) -> Optional[RepPhone]:
        """Get any phone record for a user (verified or not)."""
        try:
            result = await self.session.execute(
                select(RepPhoneORM)
                .where(RepPhoneORM.user_id == user_id)
                .order_by(RepPhoneORM.created_at.desc())
                .limit(1)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting phone by user: {e}")
            traceback.print_exc()
            raise

    async def get_by_phone_number(self, phone_number: str) -> Optional[RepPhone]:
        """Look up by phone number (for inbound routing — which rep owns this number)."""
        try:
            result = await self.session.execute(
                select(RepPhoneORM).where(
                    and_(
                        RepPhoneORM.phone_number == phone_number,
                        RepPhoneORM.is_verified == True,
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting phone by number: {e}")
            traceback.print_exc()
            raise

    async def upsert_phone(
        self, user_id: UUID, phone_number: str, verification_code: str, expires_at
    ) -> RepPhone:
        """
        Create or update a phone registration (for OTP flow).

        If the user already has a phone record, update it with the new code.
        Otherwise create a new record.
        """
        try:
            result = await self.session.execute(
                select(RepPhoneORM).where(RepPhoneORM.user_id == user_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.phone_number = phone_number
                existing.verification_code = verification_code
                existing.verification_expires_at = expires_at
                existing.is_verified = False
                existing.verified_at = None
                await self.session.flush()
                await self.session.refresh(existing)
                return self._to_domain(existing)
            else:
                orm_obj = RepPhoneORM(
                    user_id=user_id,
                    phone_number=phone_number,
                    verification_code=verification_code,
                    verification_expires_at=expires_at,
                    is_verified=False,
                    is_primary=True,
                )
                self.session.add(orm_obj)
                await self.session.flush()
                await self.session.refresh(orm_obj)
                return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error upserting phone: {e}")
            traceback.print_exc()
            raise

    async def mark_verified(self, user_id: UUID, phone_number: str, verified_at) -> Optional[RepPhone]:
        """Mark a phone as verified after OTP confirmation."""
        try:
            result = await self.session.execute(
                select(RepPhoneORM).where(
                    and_(
                        RepPhoneORM.user_id == user_id,
                        RepPhoneORM.phone_number == phone_number,
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()
            if not orm_obj:
                return None

            orm_obj.is_verified = True
            orm_obj.verified_at = verified_at
            orm_obj.verification_code = None
            orm_obj.verification_expires_at = None
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error marking phone verified: {e}")
            traceback.print_exc()
            raise

    async def update_push_token(
        self, user_id: UUID, expo_push_token: str
    ) -> None:
        """Update the Expo push token for a rep's phone."""
        try:
            await self.session.execute(
                update(RepPhoneORM)
                .where(
                    and_(
                        RepPhoneORM.user_id == user_id,
                        RepPhoneORM.is_primary == True,
                    )
                )
                .values(expo_push_token=expo_push_token)
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error updating push token: {e}")
            traceback.print_exc()
            raise
