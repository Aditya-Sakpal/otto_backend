"""API test: ai_briefing is in the appointment-context response contract.

Mirrors test_property_brief_api by monkeypatching the service to return an
AppointmentContextResponse with a populated AIBriefing, proving the route +
response_model serialize the new field end-to-end.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
import app.routes.v1.appointments as appt_routes
from app.domain.enums import UserRole
from app.domain.schemas.appointment import (
    AppointmentContextResponse,
    ContactCardInfo,
    LeadContextInfo,
    AggregatedObjections,
    AIBriefing,
)

UTC = timezone.utc


def _user():
    return type(
        "U",
        (),
        {"id": uuid4(), "role": UserRole.SALES_REP, "company_id": uuid4()},
    )()


async def _db():
    yield None


def _response_with_ai_briefing(briefing: AIBriefing | None):
    return AppointmentContextResponse(
        appointment_id=uuid4(),
        scheduled_start=datetime(2026, 6, 2, 14, 0, tzinfo=UTC),
        scheduled_end=None,
        location_address="123 Main St",
        latitude=None,
        longitude=None,
        outcome="pending",
        recording_status=None,
        audio_url=None,
        appointment_analysis=None,
        contact_info=ContactCardInfo(
            id=uuid4(),
            first_name="Jane",
            last_name="Doe",
            email=None,
            primary_phone="+15551230000",
            address="123 Main St",
            city="Phoenix",
            state="AZ",
        ),
        sales_rep_name="Rep One",
        property_brief=None,
        lead_info=LeadContextInfo(
            id=uuid4(),
            status="qualified_booked",
            deal_size=None,
            deal_type=None,
            lead_score=None,
        ),
        conversation_history=[],
        objections=AggregatedObjections(
            unique_objections=[],
            objection_counts={},
            top_objections=[],
        ),
        pending_actions=[],
        phases=None,
        ai_briefing=briefing,
        follow_up=None,
    )


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _user
    from app.core.dependencies import get_db

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _patch_service(monkeypatch, briefing: AIBriefing | None):
    async def fake_ctx(self, appointment_id):
        return _response_with_ai_briefing(briefing)

    monkeypatch.setattr(
        appt_routes.AppointmentService, "get_appointment_context", fake_ctx
    )


def test_ai_briefing_serialized_non_null(client, monkeypatch):
    briefing = AIBriefing(
        briefing_text="Meeting with Jane Doe about roof repair.",
        focus_areas=[
            "Clarify the problem and desired outcome.",
            "Agree on next steps.",
        ],
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    _patch_service(monkeypatch, briefing)

    r = client.get(f"/api/v1/appointments/{uuid4()}/context")
    assert r.status_code == 200
    body = r.json()
    assert "ai_briefing" in body
    ab = body["ai_briefing"]
    assert ab is not None
    assert ab["briefing_text"].startswith("Meeting with Jane Doe")
    assert isinstance(ab["focus_areas"], list)
    assert len(ab["focus_areas"]) >= 1
    assert ab["generated_at"] is not None


def test_ai_briefing_serialized_null(client, monkeypatch):
    _patch_service(monkeypatch, None)

    r = client.get(f"/api/v1/appointments/{uuid4()}/context")
    assert r.status_code == 200
    body = r.json()
    assert "ai_briefing" in body
    assert body["ai_briefing"] is None

