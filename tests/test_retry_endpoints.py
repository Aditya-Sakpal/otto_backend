"""
Integration tests for the two retry endpoints the frontend needs to wire
the "Retry analysis" button:

  * ``POST /api/v1/recordings/{appointment_id}/retry``
  * ``POST /api/v1/calls/{call_id}/retry``

These tests avoid hitting real DB / real Shoonya by patching the repository
and Shoonya-client factories at module scope. Coverage focuses on the
precondition matrix the FE relies on: 404 (missing record / missing audio),
409 (already processing), 403 (cross-tenant), 503 (Shoonya unavailable),
and the 202 happy path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.routes.v1.calls import router as calls_router
from app.routes.v1.recordings import router as recordings_router


TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(company_id: UUID | None = TENANT_A) -> User:
    return User(
        id=uuid4(),
        email="retry@test.local",
        role=UserRole.EXECUTIVE,
        is_active=True,
        company_id=company_id,
        created_at=datetime.utcnow(),
    )


def _make_app(current_user: User, prefix: str, router) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    # Override auth — we don't want to decode a real JWT inside these tests.
    app.dependency_overrides[get_current_user] = lambda: current_user
    # Override role checkers the routes declare directly. The factory
    # `require_any_role` returns a fresh callable per call, so we match it
    # via the route's explicit Depends — easier to blanket-override any
    # User-returning dep via dependency_overrides on the function refs.
    app.dependency_overrides[require_any_role] = lambda *_a, **_kw: lambda: current_user
    # Override the DB session dependency — the routes' own patches make the
    # DB a no-op, but FastAPI still needs something that behaves like an
    # async session (``await db.commit()`` / ``await db.rollback()`` etc.).
    async def _fake_db():
        fake = MagicMock()
        fake.commit = AsyncMock(return_value=None)
        fake.rollback = AsyncMock(return_value=None)
        fake.refresh = AsyncMock(return_value=None)
        fake.flush = AsyncMock(return_value=None)
        fake.execute = AsyncMock(return_value=MagicMock())
        yield fake

    app.dependency_overrides[get_db] = _fake_db
    return app


def _make_appointment(
    *,
    company_id: UUID = TENANT_A,
    audio_url: str | None = "https://s3/example.wav",
    analysis_status: str | None = "failed",
    extra_metadata: dict | None = None,
    duration_seconds: int | None = 1200,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        lead_id=uuid4(),
        contact_card_id=uuid4(),
        scheduled_start=datetime(2026, 4, 16, 14, 0, tzinfo=timezone.utc),
        audio_url=audio_url,
        analysis_status=analysis_status,
        extra_metadata=extra_metadata,
        duration_seconds=duration_seconds,
        shunya_job_id=None,
        mark_updated=lambda: None,
    )


def _make_call(
    *,
    company_id: UUID = TENANT_A,
    audio_url: str | None = "https://s3/example.wav",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        lead_id=uuid4(),
        contact_card_id=uuid4(),
        phone_number="+15555550123",
        audio_url=audio_url,
        duration_seconds=180,
        handled_by_user_id=None,
        call_type=None,
        created_at=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        extra_metadata=None,
    )


# ── Recordings retry ─────────────────────────────────────────────────────────


class _FakeAppointmentRepo:
    def __init__(self, appointment):
        self._appt = appointment

    async def get_by_id(self, _appointment_id):
        return self._appt

    async def update(self, _id, obj):
        return obj


def _patch_recordings(monkeypatch, *, appointment, shoonya_available: bool = True, shoonya_raises: Exception | None = None):
    from app.routes.v1 import recordings as recordings_module

    def _repo_factory(_db):
        return _FakeAppointmentRepo(appointment)

    monkeypatch.setattr(recordings_module, "AppointmentRepository", _repo_factory)

    mock_shoonya = MagicMock()
    mock_shoonya.is_available = MagicMock(return_value=shoonya_available)
    if shoonya_raises is not None:
        mock_shoonya.process_call = AsyncMock(side_effect=shoonya_raises)
    else:
        mock_shoonya.process_call = AsyncMock(
            return_value={"job_id": "shoonya-job-new-123", "status": "queued"}
        )

    monkeypatch.setattr(
        recordings_module, "get_shoonya_client", lambda: mock_shoonya
    )
    return mock_shoonya


def test_recordings_retry_happy_path(monkeypatch):
    appt = _make_appointment(analysis_status="failed", extra_metadata={
        "analysis_failure": {"source": "old", "detail": "prior"},
        "created_from_call": "abc",
    })
    _patch_recordings(monkeypatch, appointment=appt)

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["analysis_status"] == "processing"
    assert body["processing_job_id"] == "shoonya-job-new-123"
    # Failure marker cleared; unrelated metadata preserved
    assert "analysis_failure" not in (appt.extra_metadata or {})
    assert appt.extra_metadata.get("created_from_call") == "abc"


def test_recordings_retry_returns_404_when_no_audio(monkeypatch):
    appt = _make_appointment(audio_url=None)
    _patch_recordings(monkeypatch, appointment=appt)

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 404
    assert "audio_url" in resp.json()["detail"]


def test_recordings_retry_returns_404_when_missing(monkeypatch):
    _patch_recordings(monkeypatch, appointment=None)

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{uuid4()}/retry")

    assert resp.status_code == 404


def test_recordings_retry_returns_409_when_already_processing(monkeypatch):
    appt = _make_appointment(analysis_status="processing")
    _patch_recordings(monkeypatch, appointment=appt)

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 409


def test_recordings_retry_returns_403_on_cross_tenant(monkeypatch):
    appt = _make_appointment(company_id=TENANT_B)
    _patch_recordings(monkeypatch, appointment=appt)

    # Caller belongs to TENANT_A; appointment belongs to TENANT_B.
    app = _make_app(_make_user(company_id=TENANT_A), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 403


def test_recordings_retry_returns_503_when_shoonya_unavailable(monkeypatch):
    appt = _make_appointment()
    _patch_recordings(monkeypatch, appointment=appt, shoonya_available=False)

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 503


def test_recordings_retry_returns_failed_state_when_submission_raises(monkeypatch):
    """
    Shoonya is reachable (is_available()==True) but the process_call call
    itself raises — the endpoint should record the failure and return 202
    with analysis_status="failed" so the FE can show another retry button.
    """
    appt = _make_appointment()
    _patch_recordings(
        monkeypatch,
        appointment=appt,
        shoonya_available=True,
        shoonya_raises=RuntimeError("shoonya 5xx"),
    )

    app = _make_app(_make_user(), "/api/v1/recordings", recordings_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/recordings/{appt.id}/retry")

    assert resp.status_code == 202
    body = resp.json()
    assert body["analysis_status"] == "failed"
    assert body["processing_job_id"] is None
    assert appt.extra_metadata["analysis_failure"]["source"] == "recordings_retry_submission"


# ── Calls retry ──────────────────────────────────────────────────────────────


class _FakeCallRepo:
    def __init__(self, call):
        self._call = call

    async def get_by_id(self, _call_id):
        return self._call


class _FakeAnalysisRepo:
    def __init__(self, analysis):
        self._analysis = analysis

    async def get_by_call_id(self, _call_id):
        return self._analysis

    async def update(self, _id, obj):
        return obj


def _patch_calls(
    monkeypatch,
    *,
    call,
    analysis=None,
    shoonya_available: bool = True,
    shoonya_raises: Exception | None = None,
):
    from app.routes.v1 import calls as calls_module

    class _FakeService:
        def __init__(self, _db):
            self.call_repo = _FakeCallRepo(call)
            self.analysis_repo = _FakeAnalysisRepo(analysis)

    monkeypatch.setattr(calls_module, "CallService", _FakeService)

    mock_shoonya = MagicMock()
    mock_shoonya.is_available = MagicMock(return_value=shoonya_available)
    if shoonya_raises is not None:
        mock_shoonya.process_call = AsyncMock(side_effect=shoonya_raises)
    else:
        mock_shoonya.process_call = AsyncMock(
            return_value={"job_id": "shoonya-call-retry-456", "status": "queued"}
        )

    from app.infrastructure.integrations import shoonya as shoonya_module

    monkeypatch.setattr(
        shoonya_module, "get_shoonya_client", lambda: mock_shoonya
    )

    # Also patch the webhooks helper that the retry path calls on failure —
    # don't want the test to touch the DB via the real marker function.
    from app.routes.v1 import webhooks as webhooks_module

    async def _noop_mark(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        webhooks_module, "_mark_call_analysis_failed", _noop_mark
    )
    return mock_shoonya


def test_calls_retry_happy_path(monkeypatch):
    call = _make_call()
    analysis = SimpleNamespace(id=uuid4(), status="failed")
    _patch_calls(monkeypatch, call=call, analysis=analysis)

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["analysis_status"] == "processing"
    assert body["processing_job_id"] == "shoonya-call-retry-456"


def test_calls_retry_returns_404_when_no_audio(monkeypatch):
    call = _make_call(audio_url=None)
    _patch_calls(monkeypatch, call=call)

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 404
    assert "audio_url" in resp.json()["detail"]


def test_calls_retry_returns_404_when_missing(monkeypatch):
    _patch_calls(monkeypatch, call=None)

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{uuid4()}/retry")

    assert resp.status_code == 404


def test_calls_retry_returns_409_when_analysis_in_progress(monkeypatch):
    call = _make_call()
    analysis = SimpleNamespace(id=uuid4(), status="processing")
    _patch_calls(monkeypatch, call=call, analysis=analysis)

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 409


def test_calls_retry_returns_403_on_cross_tenant(monkeypatch):
    call = _make_call(company_id=TENANT_B)
    _patch_calls(monkeypatch, call=call)

    app = _make_app(_make_user(company_id=TENANT_A), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 403


def test_calls_retry_returns_503_when_shoonya_unavailable(monkeypatch):
    call = _make_call()
    _patch_calls(monkeypatch, call=call, shoonya_available=False)

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 503


def test_calls_retry_returns_failed_state_when_submission_raises(monkeypatch):
    call = _make_call()
    _patch_calls(
        monkeypatch,
        call=call,
        shoonya_available=True,
        shoonya_raises=RuntimeError("shoonya network error"),
    )

    app = _make_app(_make_user(), "/api/v1/calls", calls_router)
    client = TestClient(app)

    resp = client.post(f"/api/v1/calls/{call.id}/retry")

    assert resp.status_code == 202
    body = resp.json()
    assert body["analysis_status"] == "failed"
    assert body["processing_job_id"] is None
