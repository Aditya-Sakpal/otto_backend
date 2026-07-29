"""
Tenant isolation enforcement.

Provides a FastAPI dependency that validates the calling user has access to
the requested tenant (company). Used to close the multi-tenant data leak
documented in the product audit (SI-45 / PDF issue #45).

Two helpers are exposed:

``require_company_access``
    Lightweight dependency that only inspects the ``company_id`` Query
    parameter. Safe to mount at the router-include level — works on every
    endpoint regardless of whether it also accepts ``user_id`` as a Query
    or a Path parameter (FastAPI forbids dependency-level Query params that
    collide with route-level Path params, hence the narrow scope).

``assert_user_access``
    Plain async function (NOT a FastAPI dependency). Call this from inside
    a route handler whenever you resolve a ``user_id`` — works for both
    Query-supplied and Path-supplied user IDs.

Contract-preserving note:
    Neither helper modifies successful response shapes. They raise
    ``HTTPException(403)`` on cross-tenant requests; all other paths are
    unchanged.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.infrastructure.database import get_db_session
from app.infrastructure.database.models.user import UserORM
from app.domain.users.models import User

logger = get_logger(__name__)


# ── Router-level dependency ──────────────────────────────────────────────────


async def require_company_access(
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Query(None),
) -> None:
    """
    Block cross-tenant reads driven by the ``company_id`` Query parameter.

    - If ``company_id`` is absent, the dependency is a no-op (route handles
      its own 400 if the param was required).
    - If ``company_id`` matches the caller's ``company_id``, allow.
    - Otherwise raise 403.

    This is the primary attack vector the audit identified: a caller passes
    another tenant's ``company_id`` to ``/users/sales-reps?company_id=…`` or
    ``/metrics/exec/company-overview?company_id=…`` and receives that tenant's
    data. Declaring only ``company_id`` here (and not ``user_id``) keeps the
    dependency safe to apply at the router-include level — some routes carry
    ``{user_id}`` as a Path parameter and a Query-level ``user_id`` would
    collide.

    ``assert_user_access`` handles the ``user_id`` side of the same problem.
    """
    if company_id is None:
        return

    caller_company_id = current_user.company_id
    if caller_company_id is None:
        logger.warning(
            "Tenant access denied: caller has no company_id",
            extra={
                "caller_user_id": str(current_user.id),
                "target_company_id": str(company_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: no company context on caller",
        )

    if caller_company_id != company_id:
        logger.warning(
            "Tenant access denied: company mismatch",
            extra={
                "caller_user_id": str(current_user.id),
                "caller_company_id": str(caller_company_id),
                "target_company_id": str(company_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cross-tenant request",
        )


# ── In-route helper for user_id scoping ──────────────────────────────────────


async def assert_user_access(
    target_user_id: UUID,
    current_user: User,
    session: Optional[AsyncSession] = None,
) -> UUID:
    """
    Assert the current user can read data belonging to ``target_user_id``.

    Returns the resolved ``company_id`` of the target user so callers can
    reuse it without a second DB round-trip.

    Raises ``HTTPException(403)`` if the target user belongs to a different
    tenant. If the target user cannot be resolved we return silently — the
    caller's own logic will produce the appropriate 404.
    """
    target_company_id = await _resolve_user_company(session, target_user_id)
    if target_company_id is None:
        # Unknown user — stay quiet and let the route produce its own 404.
        return None  # type: ignore[return-value]

    caller_company_id = current_user.company_id
    if caller_company_id is None:
        logger.warning(
            "Tenant access denied: caller has no company_id",
            extra={
                "caller_user_id": str(current_user.id),
                "target_user_id": str(target_user_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: no company context on caller",
        )

    if caller_company_id != target_company_id:
        logger.warning(
            "Tenant access denied: user_id resolves to foreign tenant",
            extra={
                "caller_user_id": str(current_user.id),
                "caller_company_id": str(caller_company_id),
                "target_user_id": str(target_user_id),
                "target_company_id": str(target_company_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cross-tenant request",
        )

    return target_company_id


async def _resolve_user_company(
    session: Optional[AsyncSession], user_id: UUID
) -> Optional[UUID]:
    """Return target user's company_id, or None if user not found / no company."""
    if session is None:
        async for s in get_db_session():
            return await _resolve_user_company(s, user_id)
        return None

    result = await session.execute(
        select(UserORM.company_id).where(UserORM.id == user_id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0]
