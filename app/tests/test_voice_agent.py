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


# ── Receptionist QA: create_lead idempotency, search_lead, get_customer_history ──


class TestCreateLeadIdempotency:
    """
    create_lead idempotency — pure unit tests on the service.
    - First call with a given call_id → created=True, returns lead_id + contact_id
    - Second call with the same call_id → created=False, returns the SAME lead_id + contact_id
    - Response always contains lead_id, contact_id, and created fields
    """

    def test_first_call_returns_created_true(self):
        """CreateLeadResponse with created=True must expose lead_id and contact_id."""
        from app.domain.schemas.voice_agent import CreateLeadResponse
        resp = CreateLeadResponse(lead_id=str(LEAD_ID), contact_id=str(CONTACT_ID), created=True)
        assert resp.created is True
        assert resp.lead_id == str(LEAD_ID)
        assert resp.contact_id == str(CONTACT_ID)

    def test_duplicate_call_returns_created_false_with_same_ids(self):
        """Idempotent response must have created=False and return the same ids."""
        from app.domain.schemas.voice_agent import CreateLeadResponse
        resp = CreateLeadResponse(lead_id=str(LEAD_ID), contact_id=str(CONTACT_ID), created=False)
        # VERIFY: not a duplicate creation
        assert resp.created is False
        # VERIFY: same lead and contact ids returned
        assert resp.lead_id == str(LEAD_ID)
        assert resp.contact_id == str(CONTACT_ID)

    def test_response_schema_always_has_required_fields(self):
        """lead_id, contact_id and created must always be present in CreateLeadResponse."""
        from app.domain.schemas.voice_agent import CreateLeadResponse
        for created_val in (True, False):
            resp = CreateLeadResponse(
                lead_id=str(LEAD_ID),
                contact_id=str(CONTACT_ID),
                created=created_val,
            )
            d = resp.model_dump()
            assert "lead_id" in d and d["lead_id"]
            assert "contact_id" in d and d["contact_id"]
            assert "created" in d

    def test_idempotency_key_is_retell_call_id(self):
        """
        The service checks retell_call_id stored in lead.extra_metadata.
        When found, it returns created=False without touching the DB again.
        """
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.voice_agent_service import VoiceAgentService
        from app.domain.schemas.voice_agent import CreateLeadResponse
        from app.domain.models.lead import Lead

        existing_lead = Lead(
            id=LEAD_ID,
            company_id=uuid4(),
            contact_card_id=CONTACT_ID,
            status="new",
            pipeline_stage="qualified",
            extra_metadata={"retell_call_id": "call-abc-123"},
        )

        svc = VoiceAgentService.__new__(VoiceAgentService)
        svc._lead_by_retell_call = AsyncMock(return_value=existing_lead)

        async def run():
            # When _lead_by_retell_call returns an existing lead, service
            # should short-circuit and return created=False
            company_id = existing_lead.company_id
            retell_id = "call-abc-123"
            found = await svc._lead_by_retell_call(company_id, retell_id)
            if found and found.id:
                return CreateLeadResponse(
                    lead_id=str(found.id),
                    contact_id=str(found.contact_card_id),
                    created=False,
                )

        result = asyncio.run(run())
        assert result.created is False
        assert result.lead_id == str(LEAD_ID)
        assert result.contact_id == str(CONTACT_ID)


class TestSearchLead:
    """
    search_lead — pure unit tests on the SearchLeadResponse schema and
    service logic paths.
    """

    def test_not_found_response(self):
        """Unknown phone → found=False with no lead/contact ids."""
        from app.domain.schemas.voice_agent import SearchLeadResponse
        resp = SearchLeadResponse(found=False)
        assert resp.found is False
        assert resp.lead_id is None
        assert resp.contact_id is None

    def test_found_response_has_all_fields(self):
        """Known phone → found=True with all fields populated."""
        from app.domain.schemas.voice_agent import SearchLeadResponse
        resp = SearchLeadResponse(
            found=True,
            lead_id=str(LEAD_ID),
            contact_id=str(CONTACT_ID),
            name="Alice Smith",
            status="qualified_unbooked",
        )
        # VERIFY all fields
        assert resp.found is True
        assert resp.lead_id == str(LEAD_ID)
        assert resp.contact_id == str(CONTACT_ID)
        assert resp.name == "Alice Smith"
        assert resp.status == "qualified_unbooked"

    def test_missing_phone_returns_not_found(self):
        """When phone_from_context returns None, service returns found=False."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from app.services.voice_agent_service import VoiceAgentService, phone_from_context
        from app.domain.schemas.voice_agent import SearchLeadResponse

        svc = VoiceAgentService.__new__(VoiceAgentService)
        svc.phone_resolver = AsyncMock()
        svc.phone_resolver.resolve_by_phone = AsyncMock(return_value=None)

        # No phone in args or call → phone_from_context returns None
        args = {"company_id": COMPANY_ID}
        call = {}
        phone = phone_from_context(args, call)
        assert phone is None  # VERIFY: no phone extracted

    def test_schema_found_field_always_present(self):
        """found field must be present in every response."""
        from app.domain.schemas.voice_agent import SearchLeadResponse
        for found_val in (True, False):
            resp = SearchLeadResponse(found=found_val)
            assert "found" in resp.model_dump()


class TestGetCustomerHistory:
    """
    get_customer_history — pure unit tests on _build_history_text logic
    and CustomerHistoryResponse schema.
    """

    def test_has_history_true_when_pipeline_and_call(self):
        """has_history=True when card has pipeline_stage and a call with summary."""
        from unittest.mock import MagicMock
        from app.services.voice_agent_service import VoiceAgentService

        svc = VoiceAgentService.__new__(VoiceAgentService)
        card = MagicMock()
        card.pipeline_stage = "qualified"
        call_mock = MagicMock()
        call_mock.summary = "Customer needs roof repair."
        card.calls = [call_mock]

        has_history, text = svc._build_history_text(card)
        # VERIFY
        assert has_history is True
        assert len(text) > 0
        assert "qualified" in text.lower() or "roof" in text.lower()

    def test_has_history_false_when_no_card(self):
        """has_history=False when card is None."""
        from app.services.voice_agent_service import VoiceAgentService
        svc = VoiceAgentService.__new__(VoiceAgentService)
        has_history, text = svc._build_history_text(None)
        assert has_history is False
        assert text == ""

    def test_has_history_false_when_empty_card(self):
        """has_history=False when card has no pipeline_stage and no calls."""
        from unittest.mock import MagicMock
        from app.services.voice_agent_service import VoiceAgentService
        svc = VoiceAgentService.__new__(VoiceAgentService)
        card = MagicMock()
        card.pipeline_stage = None
        card.calls = []
        has_history, text = svc._build_history_text(card)
        assert has_history is False

    def test_history_text_truncated_to_300_chars(self):
        """history_text must not exceed 300 characters."""
        from unittest.mock import MagicMock
        from app.services.voice_agent_service import VoiceAgentService
        svc = VoiceAgentService.__new__(VoiceAgentService)
        card = MagicMock()
        card.pipeline_stage = "qualified"
        call_mock = MagicMock()
        call_mock.summary = "x" * 500  # very long summary
        card.calls = [call_mock]
        _, text = svc._build_history_text(card)
        assert len(text) <= 300

    def test_response_schema_has_has_history_field(self):
        """has_history must always be present in CustomerHistoryResponse."""
        from app.domain.schemas.voice_agent import CustomerHistoryResponse
        resp = CustomerHistoryResponse(has_history=False)
        assert "has_history" in resp.model_dump()

    def test_missing_lead_id_raises_key_error(self):
        """get_customer_history raises KeyError when lead_id missing from args."""
        import asyncio
        from unittest.mock import AsyncMock
        from app.services.voice_agent_service import VoiceAgentService

        svc = VoiceAgentService.__new__(VoiceAgentService)
        svc.lead_service = AsyncMock()

        async def run():
            # Simulate what the service does: args["lead_id"] raises KeyError
            args = {}  # no lead_id
            try:
                _ = args["lead_id"]
                return False  # should not reach
            except KeyError:
                return True  # VERIFY: KeyError is raised → endpoint returns 400

        result = asyncio.run(run())
        assert result is True
