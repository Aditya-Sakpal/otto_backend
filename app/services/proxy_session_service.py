"""
Proxy session lifecycle service.

Manages the creation and teardown of masked communication sessions:
- Auto-creates sessions when appointments reach APPOINTMENT_RAN
- Auto-closes sessions when leads move to WON/LOST
- Routes inbound calls/SMS to the correct session
- Sends intro SMS to homeowner on session creation
"""
from typing import Optional, Tuple, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.proxy_session import ProxySession
from app.infrastructure.integrations.twilio_client import get_twilio_client
from app.infrastructure.repositories.proxy_session import ProxySessionRepository
from app.infrastructure.repositories.rep_phone import RepPhoneRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.proxy_number import ProxyNumberRepository
from app.services.proxy_pool_service import ProxyPoolService
from app.services.rep_phone_service import RepPhoneNotRegisteredError

logger = get_logger(__name__)


class SessionNotFoundError(Exception):
    """No active session found for the given proxy+caller combination."""

    def __init__(self, proxy_number: str, caller_number: str):
        self.proxy_number = proxy_number
        self.caller_number = caller_number
        super().__init__(
            f"No active session for proxy={proxy_number}, caller={caller_number}"
        )


class ProxySessionService:
    """Manages proxy session lifecycle."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.session_repo = ProxySessionRepository(session)
        self.proxy_pool = ProxyPoolService(session)
        self.rep_phone_repo = RepPhoneRepository(session)
        self.contact_repo = ContactRepository(session)
        self.lead_repo = LeadRepository(session)
        self.proxy_number_repo = ProxyNumberRepository(session)
        self.twilio = get_twilio_client()

    async def create_session(
        self,
        company_id: UUID,
        lead_id: UUID,
        rep_user_id: UUID,
    ) -> ProxySession:
        """
        Create a new proxy session for a lead-rep pair.

        Called when pipeline_stage transitions to APPOINTMENT_RAN.
        Idempotent — returns existing active session if one exists.

        Steps:
        1. Check for existing active session (idempotent)
        2. Get rep's verified phone number
        3. Get homeowner's phone from contact_card
        4. Allocate a proxy number from the pool
        5. Create the session record
        6. Send intro SMS to homeowner
        """
        # 1. Idempotency check
        existing = await self.session_repo.get_active_by_lead_and_rep(lead_id, rep_user_id)
        if existing:
            logger.info(
                "Session already exists",
                session_id=str(existing.id),
                lead_id=str(lead_id),
            )
            return existing

        # 2. Get rep's verified phone
        rep_phone = await self.rep_phone_repo.get_verified_primary(rep_user_id)
        if not rep_phone:
            raise RepPhoneNotRegisteredError(rep_user_id)

        # 3. Get homeowner phone from contact_card via lead
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        contact = await self.contact_repo.get_by_id(lead.contact_card_id)
        if not contact:
            raise ValueError(f"Contact card {lead.contact_card_id} not found for lead {lead_id}")

        homeowner_phone = contact.primary_phone
        if not homeowner_phone:
            raise ValueError(f"No phone number on contact card for lead {lead_id}")

        # 4. Allocate proxy number
        proxy_number = await self.proxy_pool.allocate_number(company_id)

        # 5. Create session
        proxy_session = ProxySession(
            company_id=company_id,
            lead_id=lead_id,
            rep_user_id=rep_user_id,
            proxy_number_id=proxy_number.id,
            homeowner_phone=homeowner_phone,
            rep_phone=rep_phone.phone_number,
            status="active",
        )
        created = await self.session_repo.create(proxy_session)

        logger.info(
            "Created proxy session",
            session_id=str(created.id),
            lead_id=str(lead_id),
            rep_user_id=str(rep_user_id),
            proxy_number=proxy_number.phone_number,
        )

        # 6. Send intro SMS to homeowner
        await self._send_intro_sms(
            proxy_phone=proxy_number.phone_number,
            homeowner_phone=homeowner_phone,
            homeowner_first_name=contact.first_name or "there",
            rep_first_name=None,  # Will be resolved from user model in integration
            company_name=None,  # Will be resolved from company model in integration
        )

        return created

    async def close_session(self, session_id: UUID, reason: str) -> None:
        """Close a session and return proxy number to pool."""
        session_obj = await self.session_repo.get_by_id(session_id)
        if session_obj and session_obj.status == "active":
            await self.session_repo.close_session(session_id, reason)
            await self.proxy_pool.deallocate_number(session_obj.proxy_number_id)
            logger.info(
                "Closed proxy session",
                session_id=str(session_id),
                reason=reason,
            )

    async def close_sessions_for_lead(self, lead_id: UUID, reason: str) -> int:
        """
        Close all active sessions when deal moves to won/lost.

        Returns the number of sessions closed.
        """
        # Get sessions to deallocate their proxy numbers
        sessions = await self.session_repo.get_active_sessions_for_lead(lead_id)
        for s in sessions:
            await self.proxy_pool.deallocate_number(s.proxy_number_id)

        count = await self.session_repo.close_sessions_for_lead(lead_id, reason)
        if count:
            logger.info(
                "Closed sessions for lead",
                lead_id=str(lead_id),
                reason=reason,
                count=count,
            )
        return count

    async def resolve_inbound(
        self, proxy_number: str, caller_number: str
    ) -> Tuple[ProxySession, str]:
        """
        Core routing logic for inbound calls/SMS.

        Given a proxy_number (Twilio number that received the call/SMS)
        and caller_number (who is calling/texting), determines:
        - Which session this belongs to
        - The direction (rep_to_homeowner or homeowner_to_rep)

        Returns: (session_domain_model, direction_string)
        """
        session_orm = await self.session_repo.get_by_proxy_and_caller(
            proxy_number, caller_number
        )
        if not session_orm:
            raise SessionNotFoundError(proxy_number, caller_number)

        session = self.session_repo._to_domain(session_orm)

        if caller_number == session.rep_phone:
            return session, "rep_to_homeowner"
        elif caller_number == session.homeowner_phone:
            return session, "homeowner_to_rep"
        else:
            raise SessionNotFoundError(proxy_number, caller_number)

    async def get_sessions_for_rep(self, rep_user_id: UUID) -> List[ProxySession]:
        """Get all active sessions for mobile app display."""
        return await self.session_repo.get_active_sessions_for_rep(rep_user_id)

    async def get_session_by_lead(self, lead_id: UUID) -> Optional[ProxySession]:
        """Get active session for a lead."""
        return await self.session_repo.get_active_by_lead(lead_id)

    # ── Internal ──────────────────────────────────────────────────────────

    async def _send_intro_sms(
        self,
        proxy_phone: str,
        homeowner_phone: str,
        homeowner_first_name: str,
        rep_first_name: Optional[str],
        company_name: Optional[str],
    ) -> None:
        """Send the intro SMS to the homeowner from the proxy number."""
        if not self.twilio.is_available():
            logger.warning("Twilio not available — skipping intro SMS")
            return

        rep_name = rep_first_name or "your representative"
        company = company_name or "our team"

        body = (
            f"Hi {homeowner_first_name}, this is {rep_name} from {company}. "
            f"You can reach me directly at this number going forward about "
            f"your project. — {rep_name}"
        )

        try:
            self.twilio.send_sms(
                from_number=proxy_phone,
                to_number=homeowner_phone,
                body=body,
            )
            logger.info(
                "Sent intro SMS",
                proxy_phone=proxy_phone,
                homeowner_phone=homeowner_phone,
            )
        except Exception as e:
            # Non-blocking — don't fail session creation if intro SMS fails
            logger.warning(f"Failed to send intro SMS: {e}")
