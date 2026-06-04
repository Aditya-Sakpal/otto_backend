"""API tests for GET /recordings/{appointment_id}/analysis state surfacing.

Uses FastAPI dependency overrides + monkeypatched repo/presign so no DB or S3 is
required. Covers the 6 validation cases from the Phase-1 spec.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
from app.core.dependencies import get_db
import app.routes.v1.recordings as rec
from app.domain.enums import UserRole


# ── Fixtures / overrides ─────────────────────────────────────────────────

def _fake_user():
    return SimpleNamespace(id=uuid4(), role=UserRole.SALES_REP, company_id=uuid4())


async def _fake_db():
    yield None  # endpoint only uses db to construct a repo we monkeypatch


def _appt(**kw):
    base = dict(
        id=uuid4(), recording_status=None, analysis_status=None, audio_url=None,
        extra_metadata=None, summary=None, key_points=None, action_items=None,
        next_steps=None, objections=None, objection_texts=None,
        objections_total_count=None, qualification_status=None, booking_status=None,
        sentiment_score=None, sop_compliance_score=None, sop_compliance_rate=None,
        sop_stages_completed=None, sop_stages_missed=None, sop_compliance_issues=None,
        sop_compliance_positive_behaviors=None, compliance_target_role=None,
        transcript=None, duration_seconds=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    # Presign stub: deterministic, proves the endpoint routes audio_url through it.
    monkeypatch.setattr(
        rec, "presign_audio_url_for_playback",
        lambda url, expiration=14400: (f"PRESIGNED::{url}" if url else None),
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _patch_appt(monkeypatch, appt):
    async def fake_get_by_id(self, _id):
        return appt
    monkeypatch.setattr(rec.AppointmentRepository, "get_by_id", fake_get_by_id)


URL = "/api/v1/recordings/{}/analysis"


# ── Case 1: uploaded ─────────────────────────────────────────────────────
def test_uploaded_returns_uploaded_state(client, monkeypatch):
    appt = _appt(recording_status="uploaded", analysis_status=None,
                 audio_url="https://b.s3.us-east-1.amazonaws.com/recordings/a.wav")
    _patch_appt(monkeypatch, appt)
    r = client.get(URL.format(appt.id))
    assert r.status_code == 200
    body = r.json()
    assert body["recording_state"] == "uploaded"
    assert body["ready"] is False
    assert body["failure_reason"]  # explains analysis not started
    assert body["audio_url"] == "PRESIGNED::https://b.s3.us-east-1.amazonaws.com/recordings/a.wav"


# ── Case 2: processing ───────────────────────────────────────────────────
def test_processing_returns_processing_state(client, monkeypatch):
    appt = _appt(recording_status="uploaded", analysis_status="processing")
    _patch_appt(monkeypatch, appt)
    r = client.get(URL.format(appt.id))
    assert r.status_code == 200
    body = r.json()
    assert body["recording_state"] == "processing"
    assert body["ready"] is False
    assert body["failure_reason"] is None


# ── Case 3: failed ───────────────────────────────────────────────────────
def test_failed_returns_failed_state_and_reason(client, monkeypatch):
    appt = _appt(analysis_status="failed",
                 extra_metadata={"analysis_error": "Shunya unreachable"})
    _patch_appt(monkeypatch, appt)
    r = client.get(URL.format(appt.id))
    assert r.status_code == 200
    body = r.json()
    assert body["recording_state"] == "failed"
    assert body["ready"] is False
    assert body["failure_reason"] == "Shunya unreachable"


# ── Case 4: completed → playback URL + analysis ──────────────────────────
def test_completed_returns_data_and_playback_url(client, monkeypatch):
    appt = _appt(
        recording_status="uploaded", analysis_status="completed",
        audio_url="https://b.s3.us-east-1.amazonaws.com/recordings/done.wav",
        summary="Great meeting", next_steps=["Send quote"], duration_seconds=600,
    )
    _patch_appt(monkeypatch, appt)
    r = client.get(URL.format(appt.id))
    assert r.status_code == 200
    body = r.json()
    assert body["recording_state"] == "completed"
    assert body["ready"] is True
    assert body["failure_reason"] is None
    assert body["summary"] == "Great meeting"
    assert body["next_steps"] == ["Send quote"]
    assert body["audio_url"].startswith("PRESIGNED::")


# ── 404 only for a genuinely missing appointment ─────────────────────────
def test_missing_appointment_still_404(client, monkeypatch):
    async def none_get_by_id(self, _id):
        return None
    monkeypatch.setattr(rec.AppointmentRepository, "get_by_id", none_get_by_id)
    r = client.get(URL.format(uuid4()))
    assert r.status_code == 404


# ── Backward-compat: a completed recording with no audio still 200 ───────
def test_completed_without_audio_url(client, monkeypatch):
    appt = _appt(analysis_status="completed", audio_url=None, summary="x")
    _patch_appt(monkeypatch, appt)
    r = client.get(URL.format(appt.id))
    assert r.status_code == 200
    assert r.json()["audio_url"] is None
    assert r.json()["ready"] is True
