"""Lightweight follow-up proposal for voice-agent leads (bypasses scanner gates)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.follow_up_otto import FollowUpOttoORM

logger = get_logger(__name__)


class VoiceFollowUpService:
    """Queue a proposed follow_up_otto row for a voice-intake lead."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def propose_for_voice_lead(
        self,
        company_id: UUID,
        lead_id: UUID,
        *,
        context: str | None = None,
        follow_up_required: bool = True,
    ) -> UUID | None:
        if not follow_up_required:
            return None

        body = (context or "").strip()
        if not body:
            body = (
                "Hi — thanks for speaking with us today. "
                "We're following up about your roofing request and next steps."
            )

        now = datetime.now(timezone.utc)
        row = FollowUpOttoORM(
            id=uuid4(),
            lead_id=lead_id,
            company_id=company_id,
            message_content=body[:1600],
            action_type="sms_to_lead",
            scheduled_at=now,
            status="proposed",
            queue_type="qualified_unbooked",
            attempt_number=1,
            ai_reasoning={"source": "voice_agent", "context": context or ""},
        )
        self.session.add(row)
        await self.session.flush()
        logger.info(
            "Voice follow-up proposed",
            follow_up_id=str(row.id),
            lead_id=str(lead_id),
        )
        return row.id
