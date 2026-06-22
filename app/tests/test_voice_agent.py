"""Tests for Retell voice-agent endpoints."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.voice_agent_service import VoiceAgentService, parse_company_id

SECRET = "test-voice-agent-secret"
COMPANY_ID = str(uuid4())
LEAD_ID = uuid4()
CONTACT_ID = uuid4()


@pytest.fixture(autouse=True)
def _voice_secret(monkeypatch):
    monkeypatch.setattr(settings, "VOICE_AGENT_SECRET", SECRET)
    monkeypatch.setattr(settings, "VOICE_AGENT_DEFAULT_COMPANY_ID", COMPANY_ID)
    monkeypatch.setattr(settings, "APP_ENV", "PROD")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _headers():
    return {"X-Voice-Agent-Secret": SECRET}


def _retell_body(args: dict, call: dict | None = None):
    return {"name": "test", "args": args, "call": call or {"from_number": "+16025551234"}}


# ── Auth ──────────────────────────────────────────────────────────────────


def test_rejects_missing_secret(client):
    r = client.get(f"/api/v1/voice-agent/get_current_date?company_id={COMPANY_ID}")
    assert r.status_code == 401


def test_accepts_valid_secret(client, monkeypatch):
    async def fake_current_date(self, company_id):
        from app.domain.schemas.voice_agent import CurrentDateResponse

        return CurrentDateResponse(datetime="2026-06-17T10:00:00-07:00")

    monkeypatch.setattr(VoiceAgentService, "get_current_date", fake_current_date)
    r = client.get(
        f"/api/v1/voice-agent/get_current_date?company_id={COMPANY_ID}",
        headers=_headers(),
    )
    assert r.status_code == 200
    assert "datetime" in r.json()


def test_get_current_date_falls_back_on_invalid_company_id(client, monkeypatch):
    async def fake_current_date(self, company_id):
        from app.domain.schemas.voice_agent import CurrentDateResponse

        assert str(company_id) == COMPANY_ID
        return CurrentDateResponse(datetime="2026-06-17T10:00:00-07:00")

    monkeypatch.setattr(VoiceAgentService, "get_current_date", fake_current_date)
    for bad in ("1", "{{company_id}}", "not-a-uuid"):
        r = client.get(
            f"/api/v1/voice-agent/get_current_date?company_id={bad}",
            headers=_headers(),
        )
        assert r.status_code == 200, bad


def test_create_lead_falls_back_on_invalid_company_id(client, monkeypatch):
    async def fake_create(self, args, call, call_id=None):
        from app.domain.schemas.voice_agent import CreateLeadResponse
        from app.services.voice_agent_service import resolve_company_id

        assert str(resolve_company_id(args)) == COMPANY_ID
        return CreateLeadResponse(lead_id=str(LEAD_ID), contact_id=str(CONTACT_ID), created=True)

    monkeypatch.setattr(VoiceAgentService, "create_lead", fake_create)
    r = client.post(
        "/api/v1/voice-agent/create_lead",
        headers=_headers(),
        json=_retell_body({"company_id": "1", "customer_name": "John", "lead_source": "voice_agent"}),
    )
    assert r.status_code == 200


# ── search_lead / create_lead (mocked service) ────────────────────────────


def test_search_lead_unknown(client, monkeypatch):
    async def fake_search(self, args, call):
        from app.domain.schemas.voice_agent import SearchLeadResponse

        return SearchLeadResponse(found=False)

    monkeypatch.setattr(VoiceAgentService, "search_lead", fake_search)
    r = client.post(
        "/api/v1/voice-agent/search_lead",
        headers=_headers(),
        json=_retell_body({"company_id": COMPANY_ID}),
    )
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_search_lead_found(client, monkeypatch):
    async def fake_search(self, args, call):
        from app.domain.schemas.voice_agent import SearchLeadResponse

        return SearchLeadResponse(
            found=True,
            lead_id=str(LEAD_ID),
            contact_id=str(CONTACT_ID),
            name="Brenda Johnson",
        )

    monkeypatch.setattr(VoiceAgentService, "search_lead", fake_search)
    r = client.post(
        "/api/v1/voice-agent/search_lead",
        headers=_headers(),
        json=_retell_body({"company_id": COMPANY_ID}),
    )
    body = r.json()
    assert body["found"] is True
    assert body["lead_id"] == str(LEAD_ID)


def test_create_lead(client, monkeypatch):
    async def fake_create(self, args, call, call_id=None):
        from app.domain.schemas.voice_agent import CreateLeadResponse

        return CreateLeadResponse(lead_id=str(LEAD_ID), contact_id=str(CONTACT_ID), created=True)

    monkeypatch.setattr(VoiceAgentService, "create_lead", fake_create)
    r = client.post(
        "/api/v1/voice-agent/create_lead?call_id=retell-call-1",
        headers=_headers(),
        json=_retell_body(
            {
                "company_id": COMPANY_ID,
                "customer_name": "John Smith",
                "lead_source": "voice_agent",
            }
        ),
    )
    assert r.status_code == 200
    assert r.json()["lead_id"] == str(LEAD_ID)


def test_save_property_details_uses_call_phone(client, monkeypatch):
    captured: dict = {}

    async def fake_save(self, args, call):
        from app.domain.schemas.voice_agent import GenericStatusResponse

        captured["call"] = call
        return GenericStatusResponse(status="saved")

    monkeypatch.setattr(VoiceAgentService, "save_property_details", fake_save)
    r = client.post(
        "/api/v1/voice-agent/save_property_details",
        headers=_headers(),
        json=_retell_body(
            {"company_id": COMPANY_ID, "property_address": "123 Main St"},
            call={"from_number": "+16025559999"},
        ),
    )
    assert r.status_code == 200
    assert captured["call"].get("from_number") == "+16025559999"


def test_create_lead_idempotency_shape(client, monkeypatch):
    async def fake_create(self, args, call, call_id=None):
        from app.domain.schemas.voice_agent import CreateLeadResponse

        return CreateLeadResponse(lead_id=str(LEAD_ID), contact_id=str(CONTACT_ID), created=False)

    monkeypatch.setattr(VoiceAgentService, "create_lead", fake_create)
    r = client.post(
        "/api/v1/voice-agent/create_lead?call_id=retell-call-1",
        headers=_headers(),
        json=_retell_body({"company_id": COMPANY_ID, "customer_name": "John", "lead_source": "voice_agent"}),
    )
    assert r.json()["created"] is False


# ── slots / appointment ───────────────────────────────────────────────────


def test_get_available_slots(client, monkeypatch):
    async def fake_slots(self, company_id, target_date, assigned_rep_id=None):
        from app.domain.schemas.voice_agent import AvailableSlotsResponse

        return AvailableSlotsResponse(slots=["2026-06-18T17:00:00+00:00"])

    monkeypatch.setattr(VoiceAgentService, "get_available_slots", fake_slots)
    r = client.get(
        "/api/v1/voice-agent/get_available_slots",
        headers=_headers(),
        params={"company_id": COMPANY_ID, "date": "2026-06-18"},
    )
    assert r.status_code == 200
    assert len(r.json()["slots"]) == 1


def test_create_appointment(client, monkeypatch):
    appt_id = uuid4()

    async def fake_appt(self, args, call, call_id=None):
        from app.domain.schemas.voice_agent import CreateAppointmentResponse

        return CreateAppointmentResponse(appointment_id=str(appt_id))

    monkeypatch.setattr(VoiceAgentService, "create_appointment", fake_appt)
    r = client.post(
        "/api/v1/voice-agent/create_appointment",
        headers=_headers(),
        json=_retell_body(
            {
                "company_id": COMPANY_ID,
                "customer_name": "Jane",
                "selected_start": "2026-06-18T17:00:00+00:00",
            }
        ),
    )
    assert r.status_code == 200
    assert r.json()["appointment_id"] == str(appt_id)


# ── follow-up ─────────────────────────────────────────────────────────────


def test_generate_followup_accepted(client, monkeypatch):
    async def fake_gen(self, args):
        return uuid4()

    monkeypatch.setattr(VoiceAgentService, "generate_followup", fake_gen)
    r = client.post(
        "/api/v1/voice-agent/generate_followup",
        headers=_headers(),
        json=_retell_body({"company_id": COMPANY_ID, "lead_id": str(LEAD_ID)}),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


# ── Retell webhook ────────────────────────────────────────────────────────


def test_retell_webhook_dev_skip_verify(client, monkeypatch):
    monkeypatch.setattr(settings, "RETELL_API_KEY", "")
    monkeypatch.setattr(settings, "APP_ENV", "DEV")

    async def patched_ingest(self, payload):
        from app.domain.schemas.voice_agent import SaveCallSummaryResponse

        return SaveCallSummaryResponse(call_id=str(uuid4()))

    monkeypatch.setattr(
        VoiceAgentService,
        "ingest_retell_call",
        patched_ingest,
    )

    r = client.post(
        "/api/v1/webhooks/retell/call-ended",
        json={"call": {"call_id": "c1", "from_number": "+16025551234", "transcript": "hi"}},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "success"


# ── Unit: company_id resolution ───────────────────────────────────────────


def test_parse_company_id_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "VOICE_AGENT_DEFAULT_COMPANY_ID", COMPANY_ID)
    assert str(parse_company_id("1")) == COMPANY_ID
    assert str(parse_company_id("{{company_id}}")) == COMPANY_ID
    assert str(parse_company_id(COMPANY_ID)) == COMPANY_ID
    assert str(parse_company_id(None)) == COMPANY_ID


# ── Unit: slot service defaults ───────────────────────────────────────────


def test_slot_service_weekday_closed(monkeypatch):
    import asyncio

    from app.domain.schemas.tenant_config import BusinessHours, DaySchedule
    from app.services.slot_availability_service import SlotAvailabilityService

    class _FakeTenant:
        async def get_config_by_company(self, _cid):
            return SimpleNamespace(
                business_hours=BusinessHours(
                    timezone="America/Phoenix",
                    sunday=DaySchedule(open="00:00", close="00:00", is_closed=True),
                ).model_dump()
            )

    svc = SlotAvailabilityService.__new__(SlotAvailabilityService)
    svc.session = None
    svc._tenant_svc = _FakeTenant()

    async def _run():
        return await svc.get_slots(uuid4(), date(2026, 6, 14))

    slots = asyncio.run(_run())
    assert slots == []
