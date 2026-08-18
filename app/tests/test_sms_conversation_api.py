"""API test: masked comms conversation surfaces SMS intent + reply draft fields."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
import app.routes.v1.masked_comms as masked_routes
from app.domain.enums import UserRole
from app.domain.models.masked_communication import MaskedCommunication

UTC = timezone.utc


def _user():
    return type("U", (), {"id": uuid4(), "role": UserRole.SALES_REP, "company_id": uuid4()})()


async def _db():
    yield None


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _user
    from app.core.dependencies import get_db

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_conversation_exposes_intent_and_reply_draft(client, monkeypatch):
    session_id = uuid4()
    msg = MaskedCommunication(
        id=uuid4(),
        session_id=session_id,
        company_id=uuid4(),
        lead_id=uuid4(),
        comm_type="sms",
        direction="homeowner_to_rep",
        from_number="+15550001111",
        to_number="+15550002222",
        proxy_number="+15550003333",
        twilio_message_sid="SMTEST123",
        message_body="Call me please",
        is_homeowner_reply=True,
        intent_label="call_me",
        confidence_score=0.99,
        extra_metadata={
            "intent_to_action": {
                "reply_draft": "Got it — someone will give you a call shortly.",
            }
        },
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )

    async def fake_get_conversation(self, _session_id, skip=0, limit=50):
        return [msg]

    monkeypatch.setattr(
        masked_routes.MaskedCommsService, "get_conversation", fake_get_conversation
    )

    r = client.get(f"/api/v1/masked-comms/sessions/{session_id}/conversation")
    assert r.status_code == 200
    body = r.json()
    assert body["messages"]
    m = body["messages"][0]
    assert m["intent_label"] == "call_me"
    assert m["confidence_score"] == 0.99
    assert "reply_draft" in m
    assert "call shortly" in (m["reply_draft"] or "")

