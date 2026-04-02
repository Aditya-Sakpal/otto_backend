"""Repository for masked communication records."""
import traceback
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.masked_communication import MaskedCommunication
from app.infrastructure.database.models.masked_communication import MaskedCommunicationORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class MaskedCommunicationRepository(
    BaseRepository[MaskedCommunicationORM, MaskedCommunication]
):
    """Repository for MaskedCommunication entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, MaskedCommunicationORM, MaskedCommunication)

    async def get_by_session(
        self, session_id: UUID, skip: int = 0, limit: int = 50
    ) -> List[MaskedCommunication]:
        """Get communications for a session, ordered by created_at ascending (thread view)."""
        try:
            result = await self.session.execute(
                select(MaskedCommunicationORM)
                .where(MaskedCommunicationORM.session_id == session_id)
                .order_by(MaskedCommunicationORM.created_at.asc())
                .offset(skip)
                .limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting communications by session: {e}")
            traceback.print_exc()
            raise

    async def get_by_twilio_call_sid(
        self, call_sid: str
    ) -> Optional[MaskedCommunicationORM]:
        """Look up by Twilio Call SID (for status/recording callbacks)."""
        try:
            result = await self.session.execute(
                select(MaskedCommunicationORM).where(
                    MaskedCommunicationORM.twilio_call_sid == call_sid
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting communication by call SID: {e}")
            traceback.print_exc()
            raise

    async def get_by_twilio_message_sid(
        self, message_sid: str
    ) -> Optional[MaskedCommunicationORM]:
        """Look up by Twilio Message SID."""
        try:
            result = await self.session.execute(
                select(MaskedCommunicationORM).where(
                    MaskedCommunicationORM.twilio_message_sid == message_sid
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting communication by message SID: {e}")
            traceback.print_exc()
            raise

    async def update_call_status(
        self,
        call_sid: str,
        call_status: str,
        duration_seconds: int,
    ) -> None:
        """Update a call record with status and duration from Twilio callback."""
        try:
            await self.session.execute(
                update(MaskedCommunicationORM)
                .where(MaskedCommunicationORM.twilio_call_sid == call_sid)
                .values(
                    call_status=call_status,
                    duration_seconds=duration_seconds,
                )
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error updating call status: {e}")
            traceback.print_exc()
            raise

    async def update_recording(
        self,
        call_sid: str,
        recording_url: str,
        recording_sid: str,
        audio_url: Optional[str] = None,
        call_id: Optional[UUID] = None,
    ) -> None:
        """Update a call record with recording details."""
        try:
            values = {
                "recording_url": recording_url,
                "recording_sid": recording_sid,
            }
            if audio_url:
                values["audio_url"] = audio_url
            if call_id:
                values["call_id"] = call_id

            await self.session.execute(
                update(MaskedCommunicationORM)
                .where(MaskedCommunicationORM.twilio_call_sid == call_sid)
                .values(**values)
            )
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error updating recording: {e}")
            traceback.print_exc()
            raise

    async def get_last_communication(
        self, session_id: UUID
    ) -> Optional[MaskedCommunication]:
        """Get the most recent communication in a session (for previews)."""
        try:
            result = await self.session.execute(
                select(MaskedCommunicationORM)
                .where(MaskedCommunicationORM.session_id == session_id)
                .order_by(MaskedCommunicationORM.created_at.desc())
                .limit(1)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting last communication: {e}")
            traceback.print_exc()
            raise
