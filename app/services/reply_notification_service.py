"""
Reply notification service — personalized push notifications for homeowner replies.

Resolves homeowner names from lead → contact_card and sends contextual
push notifications to reps when homeowners reply via SMS or call.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.integrations.expo_push import get_expo_push_client
from app.infrastructure.repositories.rep_phone import RepPhoneRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.contact import ContactRepository

logger = get_logger(__name__)


class ReplyNotificationService:
    """Sends personalized push notifications when homeowners reply."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.rep_phone_repo = RepPhoneRepository(session)
        self.lead_repo = LeadRepository(session)
        self.contact_repo = ContactRepository(session)
        self.expo_push = get_expo_push_client()

    async def notify_rep_of_inbound_sms(
        self,
        session,  # ProxySession domain model
        message_body: str,
        comm_id: UUID,
    ) -> None:
        """
        Send personalized push notification when homeowner texts.

        Title: "{FirstName} replied"
        Body: First 100 chars of message
        Data: Includes masked_comm_id for deep linking to the exact message
        """
        rep_phone = await self.rep_phone_repo.get_verified_primary(session.rep_user_id)
        if not rep_phone or not rep_phone.expo_push_token:
            return

        homeowner_name = await self._get_homeowner_first_name(session.lead_id)
        preview = message_body[:100] + "..." if len(message_body) > 100 else message_body

        await self.expo_push.send_push(
            expo_push_token=rep_phone.expo_push_token,
            title=f"{homeowner_name} replied",
            body=preview,
            data={
                "type": "homeowner_reply",
                "session_id": str(session.id),
                "lead_id": str(session.lead_id),
                "masked_comm_id": str(comm_id),
                "screen": "masked-comms",
            },
        )

    async def notify_rep_of_inbound_call(
        self,
        session,  # ProxySession domain model
        call_sid: str,
    ) -> None:
        """
        Send personalized push notification when homeowner calls.

        Title: "{FirstName} is calling"
        Body: Context about call bridging
        """
        rep_phone = await self.rep_phone_repo.get_verified_primary(session.rep_user_id)
        if not rep_phone or not rep_phone.expo_push_token:
            return

        homeowner_name = await self._get_homeowner_first_name(session.lead_id)

        await self.expo_push.send_push(
            expo_push_token=rep_phone.expo_push_token,
            title=f"{homeowner_name} is calling",
            body="Tap to answer — call is bridging to your phone now",
            data={
                "type": "homeowner_call",
                "session_id": str(session.id),
                "lead_id": str(session.lead_id),
            },
        )

    async def _get_homeowner_first_name(self, lead_id: UUID) -> str:
        """
        Resolve homeowner first name from lead → contact_card.

        Falls back to "Homeowner" on any failure.
        """
        try:
            lead = await self.lead_repo.get_by_id(lead_id)
            if not lead or not lead.contact_card_id:
                return "Homeowner"

            contact = await self.contact_repo.get_by_id(lead.contact_card_id)
            if not contact or not contact.first_name:
                return "Homeowner"

            return contact.first_name
        except Exception as e:
            logger.warning(
                f"Failed to resolve homeowner name: {e}",
                lead_id=str(lead_id),
            )
            return "Homeowner"
