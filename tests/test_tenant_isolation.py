"""
Regression tests for SI-45 (PDF #45) — multi-tenant isolation on
``/metrics/*`` and ``/users/sales-reps`` routes.

The tenant module exposes two helpers:

* ``require_company_access`` — FastAPI dependency gating cross-tenant reads
  driven by the ``company_id`` Query parameter. Safe to mount at the
  router-include level; only covers the Query-based attack vector.
* ``assert_user_access`` — plain async helper invoked from route handlers
  that resolve a ``user_id`` (either Query or Path) and want to verify the
  caller owns that user's tenant.

These tests exercise each helper in isolation with a tiny FastAPI app so the
coverage stays tight and doesn't require spinning up the full metrics service.
"""
from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.tenant import assert_user_access, require_company_access
from app.domain.enums import UserRole
from app.domain.users.models import User


# ── Helpers ──────────────────────────────────────────────────────────────────

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")

USER_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_user(company_id: UUID | None, user_id: UUID | None = None) -> User:
    return User(
        id=user_id or uuid4(),
        email="test@example.com",
        role=UserRole.EXECUTIVE,
        is_active=True,
        company_id=company_id,
        created_at=datetime.utcnow(),
    )


def _make_app(current_user: User) -> FastAPI:
    """Minimal app with a /ping route guarded by require_company_access."""
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(require_company_access)])
    def ping():
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


# ── Tests: require_company_access (Query-based) ──────────────────────────────


def test_matching_company_id_allows_request():
    app = _make_app(_make_user(company_id=TENANT_A))
    client = TestClient(app)

    resp = client.get("/ping", params={"company_id": str(TENANT_A)})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_mismatched_company_id_returns_403():
    app = _make_app(_make_user(company_id=TENANT_A))
    client = TestClient(app)

    resp = client.get("/ping", params={"company_id": str(TENANT_B)})

    assert resp.status_code == 403
    assert "cross-tenant" in resp.json()["detail"].lower()


def test_no_company_id_is_noop_and_lets_route_decide():
    """
    When ``company_id`` is not supplied the dependency returns silently and
    leaves it to the route to produce its own 400. Verifies we don't break
    endpoints that only take ``user_id`` or require no tenant context.
    """
    app = _make_app(_make_user(company_id=TENANT_A))
    client = TestClient(app)

    resp = client.get("/ping")

    assert resp.status_code == 200


def test_caller_without_company_rejected_when_company_id_present():
    app = _make_app(_make_user(company_id=None))
    client = TestClient(app)

    resp = client.get("/ping", params={"company_id": str(TENANT_A)})

    assert resp.status_code == 403


# ── Tests: assert_user_access (in-route helper) ──────────────────────────────


@pytest.fixture
def mock_resolve_user_company(monkeypatch):
    """Patch the DB resolver so we don't need a real session."""
    from app.core import tenant as tenant_module

    async def _resolve(session, user_id):
        return {
            USER_A: TENANT_A,
            USER_B: TENANT_B,
        }.get(user_id)

    monkeypatch.setattr(tenant_module, "_resolve_user_company", _resolve)
    return _resolve


async def test_user_id_same_tenant_returns_company(mock_resolve_user_company):
    caller = _make_user(company_id=TENANT_A)

    resolved = await assert_user_access(USER_A, caller)

    assert resolved == TENANT_A


async def test_user_id_other_tenant_raises_403(mock_resolve_user_company):
    """Core audit vector: caller passes a foreign tenant's user_id."""
    caller = _make_user(company_id=TENANT_A)

    with pytest.raises(HTTPException) as exc_info:
        await assert_user_access(USER_B, caller)

    assert exc_info.value.status_code == 403


async def test_user_id_unknown_returns_none_without_raising(
    mock_resolve_user_company,
):
    """
    Unknown user_id stays quiet — the route will produce its own 404. We
    specifically don't 403 here so existence isn't leaked via status code.
    """
    caller = _make_user(company_id=TENANT_A)

    resolved = await assert_user_access(uuid4(), caller)

    assert resolved is None


async def test_caller_without_company_rejected_for_user_access(
    mock_resolve_user_company,
):
    caller = _make_user(company_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await assert_user_access(USER_A, caller)

    assert exc_info.value.status_code == 403
