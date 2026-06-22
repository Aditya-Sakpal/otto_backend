"""
Tests for ProxySessionService — session creation, closing, inbound routing.

Uses pytest-asyncio with mocked repositories, Twilio, and proxy pool.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

from app.services.proxy_session_service import (
    ProxySessionService,
    SessionNotFoundError,
)
from app.services.proxy_pool_service import NoAvailableProxyNumberError
from app.services.rep_phone_service import RepPhoneNotRegisteredError


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_twilio():
    twilio = MagicMock()
    twilio.is_available.return_value = True
    twilio.send_sms.return_value = {"message_sid": "SM_test"}
    return twilio


def _make_session(
    session_id=None, lead_id=None, rep_user_id=None,
    proxy_number_id=None, homeowner_phone="+15559990000",
    rep_phone="+15551111111", status="active",
):
    s = MagicMock()
    s.id = session_id or uuid4()
    s.lead_id = lead_id or uuid4()
    s.rep_user_id = rep_user_id or uuid4()
    s.company_id = uuid4()
    s.proxy_number_id = proxy_number_id or uuid4()
    s.homeowner_phone = homeowner_phone
    s.rep_phone = rep_phone
    s.status = status
    return s


def _make_proxy(proxy_id=None, phone="+15552220000"):
    p = MagicMock()
    p.id = proxy_id or uuid4()
    p.phone_number = phone
    return p


@pytest.fixture
def service(mock_db, mock_twilio):
    with (
        patch("app.services.proxy_session_service.get_twilio_client", return_value=mock_twilio),
        patch("app.services.proxy_pool_service.get_twilio_client", return_value=mock_twilio),
    ):
        svc = ProxySessionService(mock_db)
        svc.session_repo = AsyncMock()
        svc.rep_phone_repo = AsyncMock()
        svc.contact_repo = AsyncMock()
        svc.lead_repo = AsyncMock()
        svc.proxy_number_repo = AsyncMock()
        svc.proxy_pool = AsyncMock()
        return svc


# ── create_session ───────────────────────────────────────────────────────────


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_idempotent_returns_existing(self, service):
        """If an active session already exists for the lead-rep pair, return it."""
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()
        existing = _make_session(lead_id=lead_id, rep_user_id=rep_id)
        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=existing)

        result = await service.create_session(company_id, lead_id, rep_id)

        assert result == existing
        service.proxy_pool.allocate_number.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_full_flow(self, service, mock_twilio):
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()

        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=None)

        # Rep phone
        rep_phone = MagicMock()
        rep_phone.phone_number = "+15551111111"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        # Lead + contact
        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.primary_phone = "+15559990000"
        contact.first_name = "John"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        # Proxy number
        proxy = _make_proxy()
        service.proxy_pool.allocate_number = AsyncMock(return_value=proxy)

        # Session creation
        created = _make_session()
        service.session_repo.create = AsyncMock(return_value=created)

        result = await service.create_session(company_id, lead_id, rep_id)

        assert result == created
        service.proxy_pool.allocate_number.assert_awaited_once_with(company_id)
        service.session_repo.create.assert_awaited_once()
        mock_twilio.send_sms.assert_called_once()  # Intro SMS

    @pytest.mark.asyncio
    async def test_rep_phone_not_registered(self, service):
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()

        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=None)
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=None)

        with pytest.raises(RepPhoneNotRegisteredError):
            await service.create_session(company_id, lead_id, rep_id)

    @pytest.mark.asyncio
    async def test_lead_not_found(self, service):
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()

        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=None)
        rep_phone = MagicMock()
        rep_phone.phone_number = "+15551111111"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)
        service.lead_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Lead .* not found"):
            await service.create_session(company_id, lead_id, rep_id)

    @pytest.mark.asyncio
    async def test_no_phone_on_contact(self, service):
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()

        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=None)
        rep_phone = MagicMock()
        rep_phone.phone_number = "+15551111111"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.primary_phone = None
        contact.first_name = "John"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        with pytest.raises(ValueError, match="No phone number"):
            await service.create_session(company_id, lead_id, rep_id)

    @pytest.mark.asyncio
    async def test_intro_sms_failure_does_not_fail_session(self, service, mock_twilio):
        """Intro SMS failure should not prevent session creation."""
        company_id = uuid4()
        lead_id = uuid4()
        rep_id = uuid4()

        service.session_repo.get_active_by_lead_and_rep = AsyncMock(return_value=None)
        rep_phone = MagicMock()
        rep_phone.phone_number = "+15551111111"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.primary_phone = "+15559990000"
        contact.first_name = "John"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        proxy = _make_proxy()
        service.proxy_pool.allocate_number = AsyncMock(return_value=proxy)

        created = _make_session()
        service.session_repo.create = AsyncMock(return_value=created)

        # Twilio SMS throws
        mock_twilio.send_sms.side_effect = Exception("Twilio down")

        result = await service.create_session(company_id, lead_id, rep_id)

        # Session still created despite SMS failure
        assert result == created


# ── close_session ────────────────────────────────────────────────────────────


class TestCloseSession:
    @pytest.mark.asyncio
    async def test_closes_and_deallocates(self, service):
        session = _make_session()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.session_repo.close_session = AsyncMock()
        service.proxy_pool.deallocate_number = AsyncMock()

        await service.close_session(session.id, "deal_won")

        service.session_repo.close_session.assert_awaited_once_with(session.id, "deal_won")
        service.proxy_pool.deallocate_number.assert_awaited_once_with(session.proxy_number_id)

    @pytest.mark.asyncio
    async def test_already_closed_no_op(self, service):
        session = _make_session(status="closed")
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.session_repo.close_session = AsyncMock()
        service.proxy_pool.deallocate_number = AsyncMock()

        await service.close_session(session.id, "deal_won")

        service.session_repo.close_session.assert_not_awaited()
        service.proxy_pool.deallocate_number.assert_not_awaited()


# ── close_sessions_for_lead ──────────────────────────────────────────────────


class TestCloseSessionsForLead:
    @pytest.mark.asyncio
    async def test_closes_all_and_deallocates(self, service):
        lead_id = uuid4()
        s1 = _make_session(lead_id=lead_id)
        s2 = _make_session(lead_id=lead_id)

        service.session_repo.get_active_sessions_for_lead = AsyncMock(return_value=[s1, s2])
        service.session_repo.close_sessions_for_lead = AsyncMock(return_value=2)
        service.proxy_pool.deallocate_number = AsyncMock()

        count = await service.close_sessions_for_lead(lead_id, "deal_won")

        assert count == 2
        assert service.proxy_pool.deallocate_number.await_count == 2

    @pytest.mark.asyncio
    async def test_no_active_sessions(self, service):
        lead_id = uuid4()
        service.session_repo.get_active_sessions_for_lead = AsyncMock(return_value=[])
        service.session_repo.close_sessions_for_lead = AsyncMock(return_value=0)

        count = await service.close_sessions_for_lead(lead_id, "deal_lost")

        assert count == 0


# ── resolve_inbound ──────────────────────────────────────────────────────────


class TestResolveInbound:
    @pytest.mark.asyncio
    async def test_homeowner_calling(self, service):
        session_orm = MagicMock()
        session_orm.homeowner_phone = "+15559990000"
        session_orm.rep_phone = "+15551111111"
        service.session_repo.get_by_proxy_and_caller = AsyncMock(return_value=session_orm)

        session_domain = MagicMock()
        session_domain.homeowner_phone = "+15559990000"
        session_domain.rep_phone = "+15551111111"
        service.session_repo._to_domain = MagicMock(return_value=session_domain)

        session, direction = await service.resolve_inbound("+15552220000", "+15559990000")

        assert direction == "homeowner_to_rep"

    @pytest.mark.asyncio
    async def test_rep_calling(self, service):
        session_orm = MagicMock()
        service.session_repo.get_by_proxy_and_caller = AsyncMock(return_value=session_orm)

        session_domain = MagicMock()
        session_domain.homeowner_phone = "+15559990000"
        session_domain.rep_phone = "+15551111111"
        service.session_repo._to_domain = MagicMock(return_value=session_domain)

        session, direction = await service.resolve_inbound("+15552220000", "+15551111111")

        assert direction == "rep_to_homeowner"

    @pytest.mark.asyncio
    async def test_no_session_found(self, service):
        service.session_repo.get_by_proxy_and_caller = AsyncMock(return_value=None)

        with pytest.raises(SessionNotFoundError):
            await service.resolve_inbound("+15552220000", "+15550000000")


# ── get_sessions_for_rep ─────────────────────────────────────────────────────


class TestGetSessionsForRep:
    @pytest.mark.asyncio
    async def test_returns_sessions(self, service):
        rep_id = uuid4()
        sessions = [_make_session(), _make_session()]
        service.session_repo.get_active_sessions_for_rep = AsyncMock(return_value=sessions)

        result = await service.get_sessions_for_rep(rep_id)

        assert len(result) == 2
