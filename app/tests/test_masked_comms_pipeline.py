"""Unit tests for masked-comms recording pipeline branch logic (no DB/network).

Exercises handle_recording_ready's guard branches with stubbed repos/services:
idempotency skip, no-comm early return, S3-unavailable graceful stop. The full
S3→Call→Shunya→PendingActions flow is covered by the staging validation.
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.masked_comms_service import MaskedCommsService


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _svc():
    svc = MaskedCommsService.__new__(MaskedCommsService)
    # Minimal collaborators; tests set what each branch needs.
    svc.session = SimpleNamespace(commit=_anoop)
    return svc


async def _anoop(*a, **k):
    return None


class _CommsRepo:
    def __init__(self, comm, captured):
        self._comm = comm
        self._captured = captured

    async def update_recording(self, **kw):
        self._captured.append(kw)
        return None

    async def get_by_twilio_call_sid(self, call_sid):
        return self._comm


def test_no_comm_returns_early(monkeypatch):
    captured = []
    svc = _svc()
    svc.comms_repo = _CommsRepo(comm=None, captured=captured)
    # Should update recording (step 1) then return — no crash.
    _run(svc.handle_recording_ready("CA1", "https://api.twilio.com/rec", "RE1"))
    # step 1 update_recording was called
    assert any("recording_sid" in c for c in captured)


def test_idempotent_skip_when_call_id_set(monkeypatch):
    captured = []
    comm = SimpleNamespace(call_id=uuid4(), company_id=uuid4(), lead_id=uuid4(),
                           from_number="+15551230000", session_id=uuid4())
    svc = _svc()
    svc.comms_repo = _CommsRepo(comm=comm, captured=captured)

    # If it did NOT skip, it would import s3/CallService — make that explode to prove skip.
    import app.core.s3 as s3mod
    def _boom():
        raise AssertionError("should not reach S3 when already processed")
    monkeypatch.setattr(s3mod, "get_s3_service", _boom)

    _run(svc.handle_recording_ready("CA2", "https://api.twilio.com/rec", "RE2"))
    # Only the step-1 update happened; no second (call_id) update.
    assert all("call_id" not in c for c in captured)


def test_s3_unavailable_stops_gracefully(monkeypatch):
    captured = []
    comm = SimpleNamespace(call_id=None, company_id=uuid4(), lead_id=uuid4(),
                           from_number="+15551230000", session_id=uuid4())
    svc = _svc()
    svc.comms_repo = _CommsRepo(comm=comm, captured=captured)
    svc.twilio = SimpleNamespace(account_sid="AC", auth_token="tok")

    import app.core.s3 as s3mod
    monkeypatch.setattr(s3mod, "get_s3_service", lambda: None)  # S3 unavailable

    # Must not raise; must not link a call_id (nothing processed).
    _run(svc.handle_recording_ready("CA3", "https://api.twilio.com/rec", "RE3"))
    assert all(c.get("call_id") is None for c in captured if "call_id" in c) or \
        all("call_id" not in c for c in captured)
