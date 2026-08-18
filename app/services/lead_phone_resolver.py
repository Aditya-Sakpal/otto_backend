"""
LeadPhoneResolver — single authority for "given a phone number, which lead does it belong to?"

Consolidates two resolution strategies:

1. **Proxy resolution** (Twilio masked comms):
   The inbound "To" is a *proxy* number, not the rep's real number.  We must
   join ``proxy_sessions`` ↔ ``proxy_numbers`` to find the active session whose
   proxy number matches ``to_number``, then match the ``From`` (homeowner phone)
   against ``homeowner_phone`` on that session.  This yields ``lead_id``,
   ``company_id``, ``session_id``, and the canonical proxy number.

2. **Direct phone resolution** (contact-card path):
   Look up ``contact_cards`` by ``primary_phone`` for a given company, then find
   the most recent lead linked to that contact.  Used by call-ingestion,
   GHL, CTM, and ServiceTitan webhooks.

Phone normalisation helpers (``digits_only``, ``phones_match``) live here so
every caller uses the same rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Phone normalisation ────────────────────────────────────────────────


def digits_only(phone: str) -> str:
    """Strip everything except digits."""
    return re.sub(r"\D", "", phone or "")


def phones_match(a: str, b: str) -> bool:
    """
    Compare two phone strings by last-10 digits (handles country-code
    prefix differences like +1 vs bare 10-digit).
    """
    da, db = digits_only(a), digits_only(b)
    if not da or not db:
        return False
    if len(da) >= 10 and len(db) >= 10:
        return da[-10:] == db[-10:]
    return da == db


# ── Result containers ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ProxySessionResult:
    """Resolved proxy-session context for an inbound message."""
    session_id: UUID
    company_id: UUID
    lead_id: UUID
    proxy_number: str
    homeowner_phone: str


@dataclass(frozen=True)
class DirectLeadResult:
    """Resolved lead via contact-card phone lookup."""
    lead_id: UUID
    contact_card_id: UUID
    company_id: UUID


# ── Resolver ───────────────────────────────────────────────────────────


class LeadPhoneResolver:
    """
    Stateless helper bound to a single async DB session.

    Usage::

        resolver = LeadPhoneResolver(session)
        ctx = await resolver.resolve_by_proxy(from_number, to_number)
        if ctx:
            print(ctx.lead_id)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Strategy 1: proxy number → session → lead ──────────────────────

    async def resolve_by_proxy(
        self, from_number: str, to_number: str
    ) -> ProxySessionResult | None:
        """
        Resolve *proxy_number* (``to_number``) → active ``proxy_session`` → lead.

        The inbound ``To`` is the Twilio proxy number assigned to the session,
        **not** the rep's real phone.  We join ``proxy_numbers`` to translate it
        back to a session, then confirm the ``From`` matches the session's
        ``homeowner_phone``.

        Returns ``None`` when no matching active session is found or when the
        required tables do not exist yet.
        """
        to_digits = digits_only(to_number)
        if not to_digits:
            return None

        try:
            q = text(
                """
                SELECT ps.id        AS session_id,
                       ps.company_id,
                       ps.lead_id,
                       pn.phone_number AS proxy_number,
                       ps.homeowner_phone
                FROM   proxy_sessions ps
                JOIN   proxy_numbers  pn ON pn.id = ps.proxy_number_id
                WHERE  ps.status = 'active'
                  AND  regexp_replace(pn.phone_number, '[^0-9]', '', 'g') = :to_digits
                ORDER  BY ps.created_at DESC
                LIMIT  50
                """
            )
            res = await self._session.execute(q, {"to_digits": to_digits})
            rows = res.mappings().all()
        except Exception as e:
            err = str(e).lower()
            if "proxy_sessions" in err or "proxy_numbers" in err:
                logger.warning(
                    "proxy tables missing or query error — skipping resolution",
                    error=str(e),
                )
            else:
                logger.error("resolve_by_proxy failed", error=str(e))
            return None

        for r in rows:
            if phones_match(r["homeowner_phone"], from_number):
                return ProxySessionResult(
                    session_id=r["session_id"],
                    company_id=r["company_id"],
                    lead_id=r["lead_id"],
                    proxy_number=r["proxy_number"],
                    homeowner_phone=r["homeowner_phone"],
                )
        return None

    # ── Strategy 2: raw phone → contact_card → lead ────────────────────

    async def resolve_by_phone(
        self, phone: str, company_id: UUID
    ) -> DirectLeadResult | None:
        """
        Find the most-recent lead whose contact_card matches *phone* within
        *company_id*.  Falls back to last-10-digit matching when an exact hit
        is not found.
        """
        if not phone or phone in ("anonymous", "unknown"):
            return None

        from app.infrastructure.database.models.contact import ContactCardORM
        from app.infrastructure.database.models.lead import LeadORM

        try:
            result = await self._session.execute(
                select(ContactCardORM).where(
                    ContactCardORM.company_id == company_id,
                    ContactCardORM.primary_phone == phone,
                )
            )
            contact = result.scalar_one_or_none()

            if not contact:
                phone_digits = digits_only(phone)
                if len(phone_digits) < 10:
                    return None
                last10 = phone_digits[-10:]
                result = await self._session.execute(
                    text(
                        """
                        SELECT id FROM contact_cards
                        WHERE company_id = :cid
                          AND RIGHT(regexp_replace(primary_phone, '[^0-9]', '', 'g'), 10) = :last10
                        LIMIT 1
                        """
                    ),
                    {"cid": str(company_id), "last10": last10},
                )
                row = result.first()
                if not row:
                    return None
                contact_card_id = row[0]
            else:
                contact_card_id = contact.id

            lead_result = await self._session.execute(
                select(LeadORM)
                .where(
                    LeadORM.contact_card_id == contact_card_id,
                    LeadORM.company_id == company_id,
                )
                .order_by(LeadORM.created_at.desc())
                .limit(1)
            )
            lead_orm = lead_result.scalar_one_or_none()
            if not lead_orm:
                return None

            return DirectLeadResult(
                lead_id=lead_orm.id,
                contact_card_id=contact_card_id,
                company_id=company_id,
            )
        except Exception as e:
            logger.error(
                "resolve_by_phone failed",
                phone=phone,
                company_id=str(company_id),
                error=str(e),
            )
            return None
