"""
Tests for MaskedCommsService — call bridging, SMS forwarding, recording pipeline, TwiML.

Modified from reference to verify:
- Delegation to ReplyNotificationService (not direct Expo Push)
- is_homeowner_reply flag on communication records
- Recording consent disclosure with 500ms timeout
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.masked_comms_service import MaskedCommsService


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_session(**overrides):
    s = MagicMock()
    s.id = overrides.get("id", uuid4())
    s.company_id = overrides.get("company_id", uuid4())
    s.lead_id = overrides.get("lead_id", uuid4())
    s.rep_user_id = overrides.get("rep_user_id", uuid4())
    s.proxy_number_id = overrides.get("proxy_number_id", uuid4())
    s.homeowner_phone = overrides.get("homeowner_phone", "+15559990000")
    s.rep_phone = overrides.get("rep_phone", "+15551111111")
    s.status = overrides.get("status", "active")
    return s


def _make_proxy(**overrides):
    p = MagicMock()
    p.id = overrides.get("id", uuid4())
    p.phone_number = overrides.get("phone_number", "+15552220000")
    return p


def _make_created_comm(comm_id=None):
    c = MagicMock()
    c.id = comm_id or uuid4()
    return c


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_twilio():
    twilio = MagicMock()
    twilio.is_available.return_value = True
    twilio.send_sms.return_value = {"message_sid": "SM_test_123"}
    twilio.create_outbound_call.return_value = {"call_sid": "CA_test_456"}
    return twilio


@pytest.fixture
def service(mock_db, mock_twilio):
    with (
        patch("app.services.masked_comms_service.get_twilio_client", return_value=mock_twilio),
        patch("app.services.proxy_session_service.get_twilio_client", return_value=mock_twilio),
        patch("app.services.proxy_pool_service.get_twilio_client", return_value=mock_twilio),
        patch("app.services.masked_comms_service.settings") as mock_settings,
    ):
        mock_settings.API_URL = "https://api.gomotto.com"
        svc = MaskedCommsService(mock_db)
        svc.comms_repo = AsyncMock()
        svc.session_repo = AsyncMock()
        svc.proxy_number_repo = AsyncMock()
        svc.rep_phone_repo = AsyncMock()
        svc.session_service = AsyncMock()
        svc.reply_notification = AsyncMock()
        svc.ci_repo = AsyncMock()
        # Default: ci_repo returns None (no recording disclosure)
        svc.ci_repo.get_by_company_id = AsyncMock(return_value=None)
        return svc


# ── handle_inbound_call ──────────────────────────────────────────────────────


class TestHandleInboundCall:
    @pytest.mark.asyncio
    async def test_homeowner_calls_bridges_to_rep(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        created_comm = _make_created_comm()
        service.comms_repo.create = AsyncMock(return_value=created_comm)

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_call1")

        assert "<Dial" in twiml
        assert session.rep_phone in twiml
        assert "record=" in twiml
        assert "recording-status" in twiml
        service.comms_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rep_calls_bridges_to_homeowner(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        twiml = await service.handle_inbound_call("+15552220000", "+15551111111", "CA_call2")

        assert session.homeowner_phone in twiml

    @pytest.mark.asyncio
    async def test_logs_communication_with_is_homeowner_reply(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_call("+15552220000", "+15559990000", "CA_call3")

        comm = service.comms_repo.create.call_args[0][0]
        assert comm.comm_type == "call"
        assert comm.direction == "homeowner_to_rep"
        assert comm.twilio_call_sid == "CA_call3"
        assert comm.call_status == "initiated"
        assert comm.is_homeowner_reply is True

    @pytest.mark.asyncio
    async def test_rep_call_not_marked_as_homeowner_reply(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_call("+15552220000", "+15551111111", "CA_call5")

        comm = service.comms_repo.create.call_args[0][0]
        assert comm.is_homeowner_reply is False

    @pytest.mark.asyncio
    async def test_delegates_to_reply_notification(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_call("+15552220000", "+15559990000", "CA_push1")

        service.reply_notification.notify_rep_of_inbound_call.assert_awaited_once_with(
            session, "CA_push1"
        )

    @pytest.mark.asyncio
    async def test_rep_to_homeowner_no_notification(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_call("+15552220000", "+15551111111", "CA_nopush")

        service.reply_notification.notify_rep_of_inbound_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_twiml_is_valid_xml(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_call4")

        assert twiml.startswith('<?xml version="1.0"')
        assert "<Response>" in twiml
        assert "</Response>" in twiml


# ── handle_inbound_sms ───────────────────────────────────────────────────────


class TestHandleInboundSms:
    @pytest.mark.asyncio
    async def test_homeowner_texts_forward_to_rep(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        created_comm = _make_created_comm()
        service.comms_repo.create = AsyncMock(return_value=created_comm)

        twiml = await service.handle_inbound_sms(
            "+15552220000", "+15559990000", "Hello!", "SM_msg1"
        )

        # Forwards via Twilio API
        mock_twilio.send_sms.assert_called_once_with(
            from_number="+15552220000",
            to_number=session.rep_phone,
            body="Hello!",
        )
        # Returns empty TwiML
        assert "<Response/>" in twiml

    @pytest.mark.asyncio
    async def test_rep_texts_forward_to_homeowner(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_sms(
            "+15552220000", "+15551111111", "Following up!", "SM_msg2"
        )

        mock_twilio.send_sms.assert_called_once_with(
            from_number="+15552220000",
            to_number=session.homeowner_phone,
            body="Following up!",
        )

    @pytest.mark.asyncio
    async def test_logs_sms_with_is_homeowner_reply(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_sms("+15552220000", "+15559990000", "Hi", "SM_msg3")

        comm = service.comms_repo.create.call_args[0][0]
        assert comm.comm_type == "sms"
        assert comm.message_body == "Hi"
        assert comm.twilio_message_sid == "SM_msg3"
        assert comm.is_homeowner_reply is True

    @pytest.mark.asyncio
    async def test_rep_sms_not_marked_as_homeowner_reply(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_sms("+15552220000", "+15551111111", "Hi", "SM_msg_rep")

        comm = service.comms_repo.create.call_args[0][0]
        assert comm.is_homeowner_reply is False

    @pytest.mark.asyncio
    async def test_delegates_sms_notification_to_reply_service(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        created_comm = _make_created_comm()
        service.comms_repo.create = AsyncMock(return_value=created_comm)

        await service.handle_inbound_sms(
            "+15552220000", "+15559990000", "Are you available?", "SM_push1"
        )

        service.reply_notification.notify_rep_of_inbound_sms.assert_awaited_once_with(
            session, "Are you available?", created_comm.id
        )

    @pytest.mark.asyncio
    async def test_rep_to_homeowner_no_sms_notification(self, service, mock_twilio):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "rep_to_homeowner")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        await service.handle_inbound_sms("+15552220000", "+15551111111", "Hi", "SM_nopush")

        service.reply_notification.notify_rep_of_inbound_sms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_forward_failure_does_not_crash(self, service, mock_twilio):
        """SMS forwarding failure should not prevent logging."""
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())
        mock_twilio.send_sms.side_effect = Exception("Twilio error")

        # Should not raise
        twiml = await service.handle_inbound_sms(
            "+15552220000", "+15559990000", "Hello", "SM_msg4"
        )

        assert "<Response/>" in twiml
        service.comms_repo.create.assert_awaited_once()


# ── initiate_outbound_call ───────────────────────────────────────────────────


class TestInitiateOutboundCall:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_twilio):
        session = _make_session()
        proxy = _make_proxy()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)
        service.comms_repo.create = AsyncMock()

        result = await service.initiate_outbound_call(session.id)

        assert result["call_sid"] == "CA_test_456"
        mock_twilio.create_outbound_call.assert_called_once()
        # Verify the call goes to rep first (first leg of bridge)
        call_kwargs = mock_twilio.create_outbound_call.call_args.kwargs
        assert call_kwargs["to_number"] == session.rep_phone
        assert call_kwargs["from_number"] == proxy.phone_number

    @pytest.mark.asyncio
    async def test_session_not_found(self, service):
        service.session_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.initiate_outbound_call(uuid4())

    @pytest.mark.asyncio
    async def test_twilio_unavailable(self, service, mock_twilio):
        mock_twilio.is_available.return_value = False
        session = _make_session()
        proxy = _make_proxy()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)

        with pytest.raises(RuntimeError, match="Twilio not configured"):
            await service.initiate_outbound_call(session.id)

    @pytest.mark.asyncio
    async def test_logs_outbound_call(self, service, mock_twilio):
        session = _make_session()
        proxy = _make_proxy()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)
        service.comms_repo.create = AsyncMock()

        await service.initiate_outbound_call(session.id)

        comm = service.comms_repo.create.call_args[0][0]
        assert comm.direction == "rep_to_homeowner"
        assert comm.twilio_call_sid == "CA_test_456"


# ── send_sms ─────────────────────────────────────────────────────────────────


class TestSendSms:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_twilio):
        session = _make_session()
        proxy = _make_proxy()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)
        service.comms_repo.create = AsyncMock()

        result = await service.send_sms(session.id, "Hello homeowner!")

        assert result["message_sid"] == "SM_test_123"
        mock_twilio.send_sms.assert_called_once_with(
            from_number=proxy.phone_number,
            to_number=session.homeowner_phone,
            body="Hello homeowner!",
        )

    @pytest.mark.asyncio
    async def test_session_not_found(self, service):
        service.session_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.send_sms(uuid4(), "Hello")


# ── handle_call_status ───────────────────────────────────────────────────────


class TestHandleCallStatus:
    @pytest.mark.asyncio
    async def test_updates_record(self, service):
        service.comms_repo.update_call_status = AsyncMock()

        await service.handle_call_status("CA_call1", "completed", 120)

        service.comms_repo.update_call_status.assert_awaited_once_with(
            "CA_call1", "completed", 120
        )


# ── handle_recording_ready ───────────────────────────────────────────────────


class TestHandleRecordingReady:
    @pytest.mark.asyncio
    async def test_updates_recording_info(self, service):
        service.comms_repo.update_recording = AsyncMock()

        await service.handle_recording_ready(
            "CA_call1", "https://api.twilio.com/recording/RE123", "RE123"
        )

        service.comms_repo.update_recording.assert_awaited_once_with(
            call_sid="CA_call1",
            recording_url="https://api.twilio.com/recording/RE123.mp3",
            recording_sid="RE123",
        )

    @pytest.mark.asyncio
    async def test_appends_mp3_extension(self, service):
        service.comms_repo.update_recording = AsyncMock()

        await service.handle_recording_ready("CA_call1", "https://twilio.com/rec/RE456", "RE456")

        call_kwargs = service.comms_repo.update_recording.call_args.kwargs
        assert call_kwargs["recording_url"].endswith(".mp3")


# ── get_bridge_twiml ─────────────────────────────────────────────────────────


class TestGetBridgeTwiml:
    @pytest.mark.asyncio
    async def test_bridges_to_homeowner(self, service):
        session = _make_session(homeowner_phone="+15559990000")
        proxy = _make_proxy(phone_number="+15552220000")
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)

        twiml = await service.get_bridge_twiml(session.id)

        assert "+15559990000" in twiml  # Homeowner's number
        assert "+15552220000" in twiml  # Proxy as callerId
        assert "record=" in twiml
        assert "<Dial" in twiml

    @pytest.mark.asyncio
    async def test_session_not_found(self, service):
        service.session_repo.get_by_id = AsyncMock(return_value=None)

        twiml = await service.get_bridge_twiml(uuid4())

        assert "Session not found" in twiml

    @pytest.mark.asyncio
    async def test_valid_twiml(self, service):
        session = _make_session()
        proxy = _make_proxy()
        service.session_repo.get_by_id = AsyncMock(return_value=session)
        service.proxy_number_repo.get_by_id = AsyncMock(return_value=proxy)

        twiml = await service.get_bridge_twiml(session.id)

        assert twiml.startswith('<?xml version="1.0"')
        assert "<Response>" in twiml
        assert "</Response>" in twiml


# ── Recording Disclosure ─────────────────────────────────────────────────────


class TestRecordingDisclosure:
    @pytest.mark.asyncio
    async def test_disclosure_enabled(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        # Mock company integration with disclosure enabled
        mock_integration = MagicMock()
        mock_integration.recording_disclosure_enabled = True
        service.ci_repo.get_by_company_id = AsyncMock(return_value=mock_integration)

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_disc1")

        assert '<Say voice="alice">' in twiml
        assert "recorded" in twiml

    @pytest.mark.asyncio
    async def test_disclosure_disabled(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        mock_integration = MagicMock()
        mock_integration.recording_disclosure_enabled = False
        service.ci_repo.get_by_company_id = AsyncMock(return_value=mock_integration)

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_disc2")

        assert "<Say" not in twiml

    @pytest.mark.asyncio
    async def test_disclosure_timeout_falls_back(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        # Simulate timeout
        async def slow_lookup(company_id):
            await asyncio.sleep(5)

        service.ci_repo.get_by_company_id = slow_lookup

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_timeout")

        # Should fall back to no disclosure (empty string)
        assert "<Say" not in twiml

    @pytest.mark.asyncio
    async def test_disclosure_exception_falls_back(self, service):
        session = _make_session()
        service.session_service.resolve_inbound = AsyncMock(
            return_value=(session, "homeowner_to_rep")
        )
        service.comms_repo.create = AsyncMock(return_value=_make_created_comm())

        service.ci_repo.get_by_company_id = AsyncMock(side_effect=Exception("DB error"))

        twiml = await service.handle_inbound_call("+15552220000", "+15559990000", "CA_err")

        assert "<Say" not in twiml


# ── get_conversation ─────────────────────────────────────────────────────────


class TestGetConversation:
    @pytest.mark.asyncio
    async def test_returns_messages(self, service):
        session_id = uuid4()
        msgs = [MagicMock(), MagicMock()]
        service.comms_repo.get_by_session = AsyncMock(return_value=msgs)

        result = await service.get_conversation(session_id)

        assert len(result) == 2
        service.comms_repo.get_by_session.assert_awaited_once_with(session_id, 0, 50)
