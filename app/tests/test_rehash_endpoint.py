"""Unit tests for the on-demand rehash scan endpoint (no DB/app server).

The route handler is a thin wrapper over scan_and_sync_rehash; its only logic
beyond the service call is tenant isolation (403 on company mismatch) and mapping
the SyncResult into RehashSyncResponse. We exercise the handler function directly
with a fake session/user, stubbing the service, so the routing contract is covered
without a running app or database. The service itself is exercised in live
verification (idempotency: a second real run creates 0).
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.routes.v1.tasks as tasks_routes
from app.domain.enums import UserRole
from app.domain.schemas.tasks import RehashSyncResponse
from app.services.rehash_service import SyncResult


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeSession:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


def _exec_user(company_id):
    return SimpleNamespace(id=uuid4(), role=UserRole.EXECUTIVE, company_id=company_id)


def test_rehash_scan_returns_counts(monkeypatch):
    """Happy path: service result is mapped into RehashSyncResponse and committed."""
    company_id = uuid4()
    session = _FakeSession()

    async def _fake_scan(_session, *, company_id=None, **_kw):
        assert company_id is not None
        return SyncResult(
            scanned=10, created=3, cancelled=1, skipped=6,
            by_category={"qualified_unbooked": 2, "stale_lead": 1},
        )

    monkeypatch.setattr(tasks_routes, "scan_and_sync_rehash", _fake_scan, raising=False)
    # The route imports scan_and_sync_rehash lazily from the service module, so
    # patch it there too.
    import app.services.rehash_service as rehash_mod
    monkeypatch.setattr(rehash_mod, "scan_and_sync_rehash", _fake_scan)

    resp = _run(tasks_routes.trigger_rehash_scan(
        db=session, company_id=company_id, user=_exec_user(company_id),
    ))

    assert isinstance(resp, RehashSyncResponse)
    assert resp.scanned == 10
    assert resp.created == 3
    assert resp.cancelled == 1
    assert resp.skipped == 6
    assert resp.by_category == {"qualified_unbooked": 2, "stale_lead": 1}
    assert session.committed is True


def test_rehash_scan_company_mismatch_403():
    """Executive from a different company is rejected before any scan runs."""
    session = _FakeSession()
    user = _exec_user(uuid4())  # belongs to a different company

    with pytest.raises(HTTPException) as exc:
        _run(tasks_routes.trigger_rehash_scan(
            db=session, company_id=uuid4(), user=user,
        ))

    assert exc.value.status_code == 403
    assert session.committed is False


def test_sync_result_idempotency_shape():
    """A re-run SyncResult (created == 0) maps cleanly — documents idempotency."""
    rerun = SyncResult(scanned=10, created=0, cancelled=0, skipped=10, by_category={})
    resp = RehashSyncResponse(
        scanned=rerun.scanned, created=rerun.created, cancelled=rerun.cancelled,
        skipped=rerun.skipped, by_category=rerun.by_category,
    )
    assert resp.created == 0
    assert resp.skipped == 10
