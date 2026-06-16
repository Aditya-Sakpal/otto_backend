"""
Tests for Twilio webhook routes — signature validation, TwiML responses.

Uses FastAPI TestClient with mocked services and Twilio signature validation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.v1.twilio_webhooks import router
from app.services.proxy_session_service import SessionNotFoundError


# ── App Setup ────────────────────────────────────────────────────────────────


def _create_test_app():
    app = FastAPI()
    app.include_router(router)
    return app


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_twilio():
    twilio = MagicMock()
    twilio.is_available.return_value = True
    twilio.validate_request.return_value = True
    return twilio


@pytest.fixture
def mock_masked_comms_service():
    svc = AsyncMock()
    svc.handle_inbound_call = AsyncMock(
        return_value='<?xml version="1.0" encoding="UTF-8"?><Response><Dial><Number>+15551111111</Number></Dial></Response>'
    )
    svc.handle_inbound_sms = AsyncMock(
        return_value='<?xml version="1.0" encoding="UTF-8"?><Response/>'
    )
    svc.handle_call_status = AsyncMock()
    svc.handle_recording_ready = AsyncMock()
    svc.get_bridge_twiml = AsyncMock(
        return_value='<?xml version="1.0" encoding="UTF-8"?><Response><Dial><Number>+15559990000</Number></Dial></Response>'
    )
    return svc


@pytest.fixture
def client(mock_twilio, mock_masked_comms_service):
    """Create FastAPI TestClient with mocked dependencies."""

    async def mock_db_session():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    app = _create_test_app()

    with (
        patch(
            "app.routes.v1.twilio_webhooks.get_twilio_client",
            return_value=mock_twilio,
        ),
        patch(
            "app.routes.v1.twilio_webhooks.MaskedCommsService",
            return_value=mock_masked_comms_service,
        ),
    ):
        # Override the DbSession dependency
        from app.core.dependencies import get_db

        app.dependency_overrides[get_db] = mock_db_session
        yield TestClient(app)
        app.dependency_overrides.clear()


# ── Signature Validation ─────────────────────────────────────────────────────


class TestSignatureValidation:
    def test_missing_signature_returns_403(self, client, mock_twilio):
        """Requests without X-Twilio-Signature should be rejected."""
        mock_twilio.validate_request.return_value = True

        response = client.post(
            "/twilio/inbound-call",
            data={"From": "+15559990000", "To": "+15552220000", "CallSid": "CA_test"},
            # No X-Twilio-Signature header
        )

        assert response.status_code == 403

    def test_invalid_signature_returns_403(self, client, mock_twilio):
        mock_twilio.validate_request.return_value = False

        response = client.post(
            "/twilio/inbound-call",
            data={"From": "+15559990000", "To": "+15552220000", "CallSid": "CA_test"},
            headers={"X-Twilio-Signature": "invalid_sig"},
        )

        assert response.status_code == 403


# ── Inbound Call ─────────────────────────────────────────────────────────────


class TestInboundCall:
    def test_success_returns_twiml(self, client, mock_masked_comms_service):
        response = client.post(
            "/twilio/inbound-call",
            data={"From": "+15559990000", "To": "+15552220000", "CallSid": "CA_test"},
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"
        assert "<Dial" in response.text

    def test_session_not_found_returns_error_twiml(self, client, mock_masked_comms_service):
        mock_masked_comms_service.handle_inbound_call.side_effect = SessionNotFoundError(
            "+15552220000", "+15550000000"
        )

        response = client.post(
            "/twilio/inbound-call",
            data={"From": "+15550000000", "To": "+15552220000", "CallSid": "CA_unknown"},
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200  # Always 200 for Twilio
        assert "<Say>" in response.text  # Error TwiML


# ── Inbound SMS ──────────────────────────────────────────────────────────────


class TestInboundSms:
    def test_success_returns_empty_twiml(self, client, mock_masked_comms_service):
        response = client.post(
            "/twilio/inbound-sms",
            data={
                "From": "+15559990000",
                "To": "+15552220000",
                "Body": "Hello!",
                "MessageSid": "SM_test",
            },
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        assert "<Response/>" in response.text

    def test_session_not_found_returns_empty_twiml(self, client, mock_masked_comms_service):
        mock_masked_comms_service.handle_inbound_sms.side_effect = SessionNotFoundError(
            "+15552220000", "+15550000000"
        )

        response = client.post(
            "/twilio/inbound-sms",
            data={
                "From": "+15550000000",
                "To": "+15552220000",
                "Body": "Hello",
                "MessageSid": "SM_unk",
            },
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        assert "<Response/>" in response.text


# ── Call Status ──────────────────────────────────────────────────────────────


class TestCallStatus:
    def test_success(self, client, mock_masked_comms_service):
        response = client.post(
            "/twilio/call-status",
            data={
                "CallSid": "CA_test",
                "CallStatus": "completed",
                "CallDuration": "120",
            },
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200

    def test_service_error_still_returns_200(self, client, mock_masked_comms_service):
        mock_masked_comms_service.handle_call_status.side_effect = Exception("DB error")

        response = client.post(
            "/twilio/call-status",
            data={
                "CallSid": "CA_fail",
                "CallStatus": "failed",
                "CallDuration": "0",
            },
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        # Must return 200 to Twilio even on internal error
        assert response.status_code == 200


# ── Recording Status ─────────────────────────────────────────────────────────


class TestRecordingStatus:
    def test_success(self, client, mock_masked_comms_service):
        response = client.post(
            "/twilio/recording-status",
            data={
                "CallSid": "CA_test",
                "RecordingUrl": "https://api.twilio.com/recording/RE123",
                "RecordingSid": "RE123",
            },
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        mock_masked_comms_service.handle_recording_ready.assert_awaited_once()


# ── Bridge Call ──────────────────────────────────────────────────────────────


class TestBridgeCall:
    def test_success(self, client, mock_masked_comms_service):
        session_id = uuid4()

        response = client.post(
            f"/twilio/bridge-call/{session_id}",
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        assert "<Dial" in response.text
        mock_masked_comms_service.get_bridge_twiml.assert_awaited_once_with(session_id)

    def test_error_returns_error_twiml(self, client, mock_masked_comms_service):
        mock_masked_comms_service.get_bridge_twiml.side_effect = Exception("Not found")
        session_id = uuid4()

        response = client.post(
            f"/twilio/bridge-call/{session_id}",
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert response.status_code == 200
        assert "<Say>" in response.text  # Error TwiML


# ── Response Format ──────────────────────────────────────────────────────────


class TestResponseFormat:
    def test_all_endpoints_return_xml(self, client, mock_masked_comms_service):
        """All Twilio webhook endpoints must return application/xml."""
        endpoints_data = [
            ("/twilio/inbound-call", {"From": "+1", "To": "+2", "CallSid": "CA"}),
            ("/twilio/inbound-sms", {"From": "+1", "To": "+2", "Body": "hi", "MessageSid": "SM"}),
            ("/twilio/call-status", {"CallSid": "CA", "CallStatus": "completed", "CallDuration": "0"}),
            ("/twilio/recording-status", {"CallSid": "CA", "RecordingUrl": "http://x", "RecordingSid": "RE"}),
        ]

        for endpoint, data in endpoints_data:
            response = client.post(
                endpoint,
                data=data,
                headers={"X-Twilio-Signature": "valid_sig"},
            )
            assert response.headers["content-type"] == "application/xml", (
                f"{endpoint} returned {response.headers['content-type']}"
            )
