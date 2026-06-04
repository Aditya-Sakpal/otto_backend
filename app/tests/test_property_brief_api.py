"""API test: property_brief is in the appointment-context response contract.

Monkeypatches the service to return a response whose property_brief is built by
the REAL build_property_brief, proving the route + response_model serialize the
new field end-to-end. (Data-loading wiring is covered by the staging validation.)
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
import app.routes.v1.appointments as appt_routes
from app.services.appointment_service import build_property_brief
from app.domain.enums import UserRole
from app.domain.schemas.appointment import (
    AppointmentContextResponse,
    ContactCardInfo,
    LeadContextInfo,
    AggregatedObjections,
)

UTC = timezone.utc


def _user():
    return type("U", (), {"id": uuid4(), "role": UserRole.SALES_REP, "company_id": uuid4()})()


async def _db():
    yield None


def _response_with_brief(brief):
    return AppointmentContextResponse(
        appointment_id=uuid4(),
        scheduled_start=datetime(2026, 6, 2, 14, 0, tzinfo=UTC),
        scheduled_end=None, location_address="123 Main St", latitude=None, longitude=None,
        outcome="pending", recording_status=None, audio_url=None,
        appointment_analysis=None,
        contact_info=ContactCardInfo(
            id=uuid4(), first_name="Jane", last_name="Doe", email=None,
            primary_phone="+15551230000", address="123 Main St", city="Phoenix", state="AZ",
        ),
        sales_rep_name="Rep One",
        property_brief=brief,
        lead_info=LeadContextInfo(id=uuid4(), status="qualified_booked", deal_size=None,
                                  deal_type=None, lead_score=None),
        conversation_history=[],
        objections=AggregatedObjections(unique_objections=[], objection_counts={}, top_objections=[]),
        pending_actions=[],
        phases=None, ai_briefing=None, follow_up=None,
    )


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _user
    from app.core.dependencies import get_db
    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _patch_service(monkeypatch, brief):
    async def fake_ctx(self, appointment_id):
        return _response_with_brief(brief)
    monkeypatch.setattr(appt_routes.AppointmentService, "get_appointment_context", fake_ctx)


def test_property_brief_serialized_full(client, monkeypatch):
    brief = build_property_brief([{
        "call_id": uuid4(), "call_date": datetime(2026, 6, 1, tzinfo=UTC), "call_type": "csr_call",
        "property_details": {"roof_type": "tile", "roof_age_years": 14, "stories": "two",
                             "property_size": "2400 sqft", "hoa_status": "yes", "hoa_name": "Sunridge",
                             "gate_access": "code 4417", "pets": "large dog",
                             "current_issues": ["Leak over garage"]},
        "customer_details": {"decision_makers": ["homeowner", "spouse"]},
        "service_requested": "Roof repair", "qualification_status": "qualified",
        "booking_status": "booked", "summary": "Wants quote",
    }])
    _patch_service(monkeypatch, brief)

    r = client.get(f"/api/v1/appointments/{uuid4()}/context")
    assert r.status_code == 200
    pb = r.json()["property_brief"]
    assert pb["has_data"] is True
    assert pb["roof_type"] == "tile"
    assert pb["property_size"] == "2400 sqft"
    assert pb["stories"] == "two"
    assert pb["decision_makers"] == ["homeowner", "spouse"]
    assert pb["service_requested"] == "Roof repair"
    assert pb["booking_status"] == "booked"
    assert pb["current_issues"] == ["Leak over garage"]


def test_property_brief_serialized_empty(client, monkeypatch):
    brief = build_property_brief([])  # no data
    _patch_service(monkeypatch, brief)
    r = client.get(f"/api/v1/appointments/{uuid4()}/context")
    assert r.status_code == 200
    pb = r.json()["property_brief"]
    assert pb["has_data"] is False
    assert pb["roof_type"] is None
    assert pb["decision_makers"] == []
