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
    ) -> int:
        """Upsert the Expo push token for a rep.

        The old implementation issued a bare UPDATE on (user_id, is_primary=True);
        when the rep had no rep_phones row yet it silently updated zero rows, so
        every device that registered a token before completing the phone-OTP flow
        ended up with no token persisted. We now upsert: update the primary row if
        present, else any row for the user, else create a minimal row carrying the
        token. phone_number is NOT-NULL, so a created row uses an empty-string
        sentinel — it is never matched for masked-comms routing (that path filters
        on is_verified=True).

        Returns the number of rows written (1 = updated or created).
        """
        try:
            # 1. Prefer the primary row.
            result = await self.session.execute(
                select(RepPhoneORM).where(
                    and_(
                        RepPhoneORM.user_id == user_id,
                        RepPhoneORM.is_primary == True,
                    )
                )
            )
            orm_obj = result.scalar_one_or_none()

            # 2. Else fall back to any (newest) row for the user.
            if orm_obj is None:
                result = await self.session.execute(
                    select(RepPhoneORM)
                    .where(RepPhoneORM.user_id == user_id)
                    .order_by(RepPhoneORM.created_at.desc())
                    .limit(1)
                )
                orm_obj = result.scalar_one_or_none()

            if orm_obj is not None:
                orm_obj.expo_push_token = expo_push_token
                await self.session.flush()
                return 1

            # 3. No row exists — create a minimal token-only registration.
            orm_obj = RepPhoneORM(
                user_id=user_id,
                phone_number="",
                is_verified=False,
                is_primary=True,
                expo_push_token=expo_push_token,
            )
            self.session.add(orm_obj)
            await self.session.flush()
            return 1
        except Exception as e:
            logger.error(f"Error updating push token: {e}")
            traceback.print_exc()
            raise
