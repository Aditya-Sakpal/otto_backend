"""
Tests for ReplyNotificationService — personalized push notifications.

Verifies:
- Homeowner first name resolution from lead → contact_card
- Personalized push titles ("{name} replied", "{name} is calling")
- Fallback to "Homeowner" on name resolution failure
- No push when rep has no push token
- Correct data payload for deep linking
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.reply_notification_service import ReplyNotificationService


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_session(**overrides):
    s = MagicMock()
    s.id = overrides.get("id", uuid4())
    s.company_id = overrides.get("company_id", uuid4())
    s.lead_id = overrides.get("lead_id", uuid4())
    s.rep_user_id = overrides.get("rep_user_id", uuid4())
    s.homeowner_phone = overrides.get("homeowner_phone", "+15559990000")
    s.rep_phone = overrides.get("rep_phone", "+15551111111")
    return s


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_expo():
    expo = AsyncMock()
    return expo


@pytest.fixture
def service(mock_db, mock_expo):
    with patch(
        "app.services.reply_notification_service.get_expo_push_client",
        return_value=mock_expo,
    ):
        svc = ReplyNotificationService(mock_db)
        svc.rep_phone_repo = AsyncMock()
        svc.lead_repo = AsyncMock()
        svc.contact_repo = AsyncMock()
        return svc


# ── notify_rep_of_inbound_sms ────────────────────────────────────────────────


class TestNotifyRepOfInboundSms:
    @pytest.mark.asyncio
    async def test_personalized_title_with_name(self, service, mock_expo):
        session = _make_session()
        comm_id = uuid4()

        # Rep has push token
        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[abc123]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        # Lead + contact with name
        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.first_name = "Sarah"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        await service.notify_rep_of_inbound_sms(session, "Hey, what time works?", comm_id)

        mock_expo.send_push.assert_awaited_once()
        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert push_kwargs["title"] == "Sarah replied"
        assert "Hey, what time works?" in push_kwargs["body"]
        assert push_kwargs["data"]["type"] == "homeowner_reply"
        assert push_kwargs["data"]["masked_comm_id"] == str(comm_id)
        assert push_kwargs["data"]["screen"] == "masked-comms"

    @pytest.mark.asyncio
    async def test_truncates_long_messages(self, service, mock_expo):
        session = _make_session()
        comm_id = uuid4()

        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[abc123]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)
        contact = MagicMock()
        contact.first_name = "John"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        long_message = "A" * 200
        await service.notify_rep_of_inbound_sms(session, long_message, comm_id)

        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert len(push_kwargs["body"]) <= 104  # 100 chars + "..."

    @pytest.mark.asyncio
    async def test_no_push_token_skips(self, service, mock_expo):
        session = _make_session()
        rep_phone = MagicMock()
        rep_phone.expo_push_token = None
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        await service.notify_rep_of_inbound_sms(session, "Hello", uuid4())

        mock_expo.send_push.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_rep_phone_skips(self, service, mock_expo):
        session = _make_session()
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=None)

        await service.notify_rep_of_inbound_sms(session, "Hello", uuid4())

        mock_expo.send_push.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_to_homeowner_on_no_contact(self, service, mock_expo):
        session = _make_session()
        comm_id = uuid4()

        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[abc123]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        # Lead exists but no contact card
        lead = MagicMock()
        lead.contact_card_id = None
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        await service.notify_rep_of_inbound_sms(session, "Hello", comm_id)

        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert push_kwargs["title"] == "Homeowner replied"

    @pytest.mark.asyncio
    async def test_fallback_to_homeowner_on_exception(self, service, mock_expo):
        session = _make_session()
        comm_id = uuid4()

        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[abc123]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        # Lead lookup fails
        service.lead_repo.get_by_id = AsyncMock(side_effect=Exception("DB error"))

        await service.notify_rep_of_inbound_sms(session, "Hello", comm_id)

        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert push_kwargs["title"] == "Homeowner replied"


# ── notify_rep_of_inbound_call ───────────────────────────────────────────────


class TestNotifyRepOfInboundCall:
    @pytest.mark.asyncio
    async def test_personalized_call_title(self, service, mock_expo):
        session = _make_session()

        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[xyz789]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)
        contact = MagicMock()
        contact.first_name = "Mike"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        await service.notify_rep_of_inbound_call(session, "CA_test_call")

        mock_expo.send_push.assert_awaited_once()
        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert push_kwargs["title"] == "Mike is calling"
        assert "bridging" in push_kwargs["body"]
        assert push_kwargs["data"]["type"] == "homeowner_call"

    @pytest.mark.asyncio
    async def test_no_push_token_skips_call(self, service, mock_expo):
        session = _make_session()
        rep_phone = MagicMock()
        rep_phone.expo_push_token = None
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        await service.notify_rep_of_inbound_call(session, "CA_nopush")

        mock_expo.send_push.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_name_on_call(self, service, mock_expo):
        session = _make_session()

        rep_phone = MagicMock()
        rep_phone.expo_push_token = "ExponentPushToken[abc]"
        service.rep_phone_repo.get_verified_primary = AsyncMock(return_value=rep_phone)

        service.lead_repo.get_by_id = AsyncMock(return_value=None)

        await service.notify_rep_of_inbound_call(session, "CA_fallback")

        push_kwargs = mock_expo.send_push.call_args.kwargs
        assert push_kwargs["title"] == "Homeowner is calling"


# ── _get_homeowner_first_name ────────────────────────────────────────────────


class TestGetHomeownerFirstName:
    @pytest.mark.asyncio
    async def test_returns_first_name(self, service):
        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.first_name = "Jennifer"
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        name = await service._get_homeowner_first_name(uuid4())

        assert name == "Jennifer"

    @pytest.mark.asyncio
    async def test_returns_homeowner_when_lead_not_found(self, service):
        service.lead_repo.get_by_id = AsyncMock(return_value=None)

        name = await service._get_homeowner_first_name(uuid4())

        assert name == "Homeowner"

    @pytest.mark.asyncio
    async def test_returns_homeowner_when_no_first_name(self, service):
        lead = MagicMock()
        lead.contact_card_id = uuid4()
        service.lead_repo.get_by_id = AsyncMock(return_value=lead)

        contact = MagicMock()
        contact.first_name = None
        service.contact_repo.get_by_id = AsyncMock(return_value=contact)

        name = await service._get_homeowner_first_name(uuid4())

        assert name == "Homeowner"

    @pytest.mark.asyncio
    async def test_returns_homeowner_on_exception(self, service):
        service.lead_repo.get_by_id = AsyncMock(side_effect=Exception("DB down"))

        name = await service._get_homeowner_first_name(uuid4())

        assert name == "Homeowner"
