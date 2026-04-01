"""
Link orphaned missed-call rows to contact_cards and leads for a company.

Problem this fixes:
- Some integrations create `calls` with missed_call / call_type=missed_call but leave
  `contact_card_id` and/or `lead_id` null. CSR / metrics views that expect CRM links then
  return empty contact_card, null lead_id, and status counts stay at zero.
- Example: ServiceTitan ingestion creates a ContactCard for missed calls but intentionally
  skips lead creation for missed calls (`if contact_card and not is_missed`), so `lead_id`
  is never set on those calls. Rows with BOTH FKs null usually mean the call was inserted
  without the normal find-or-create contact step (different pipeline, bulk import, etc.).

This script:
- Finds calls for one company where (missed_call OR call_type == missed_call) AND
  (contact_card_id IS NULL OR lead_id IS NULL).
- Resolves or creates a ContactCard (match existing by normalized phone when possible).
- Resolves or creates a Lead (status "new") for that contact + company.
- Updates the call with contact_card_id and lead_id.

Optional: --old-company-id copies first/last name from the old company when the normalized
phone matches exactly one named contact there (skips ambiguous phones). Names are applied to
any resolved contact that is still missing first and/or last name — not only brand-new cards.
After linking, a second pass updates all contact cards tied to missed calls in the company
(optional date range) so already-linked rows get names too.

Usage (dry run):
    python scripts/link_missed_calls_contacts_leads.py \\
      --company-id b414e9f9-7786-4a80-b746-3e63a567cb04

Apply:
    python scripts/link_missed_calls_contacts_leads.py \\
      --company-id b414e9f9-7786-4a80-b746-3e63a567cb04 \\
      --apply

With date range (optional) and name backfill source:
    python scripts/link_missed_calls_contacts_leads.py \\
      --company-id ... \\
      --start-date 2026-03-03 \\
      --end-date 2026-04-01 \\
      --old-company-id ce9091df-db37-4e7e-877c-2ed0cf2f4c37 \\
      --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database.session import AsyncSessionLocal, engine
import app.infrastructure.database.models  # noqa: F401
import app.infrastructure.database.models.company_integration  # noqa: F401
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.lead import LeadORM


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _clean_name_part(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _day_bounds(
    start: date | None, end: date | None
) -> tuple[datetime | None, datetime | None]:
    """Interpret dates as UTC [start 00:00:00, end 23:59:59.999999]."""
    start_dt = (
        datetime.combine(start, time.min, tzinfo=timezone.utc) if start else None
    )
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc) if end else None
    return start_dt, end_dt


async def _load_name_map_from_old_company(
    session, old_company_id: UUID
) -> tuple[dict[str, tuple[str | None, str | None]], set[str]]:
    """phone_key -> (first, last); ambiguous keys are excluded."""
    result = await session.execute(
        select(ContactCardORM).where(ContactCardORM.company_id == old_company_id)
    )
    rows = result.scalars().all()
    by_phone: dict[str, set[tuple[str | None, str | None]]] = defaultdict(set)
    for c in rows:
        key = _normalize_phone(c.primary_phone)
        if not key:
            continue
        first = _clean_name_part(c.first_name)
        last = _clean_name_part(c.last_name)
        if not first and not last:
            continue
        by_phone[key].add((first, last))

    unique: dict[str, tuple[str | None, str | None]] = {}
    ambiguous: set[str] = set()
    for key, candidates in by_phone.items():
        if len(candidates) == 1:
            unique[key] = next(iter(candidates))
        else:
            ambiguous.add(key)
    return unique, ambiguous


def _apply_old_company_names_if_missing(
    contact: ContactCardORM,
    phone_key: str,
    name_by_phone: dict[str, tuple[str | None, str | None]],
    ambiguous_phones: set[str],
    apply: bool,
) -> bool:
    """
    Fill missing first/last on contact from name_by_phone. Returns True if anything
    would change / changed.
    """
    if not name_by_phone:
        return False
    if phone_key in ambiguous_phones:
        return False
    src = name_by_phone.get(phone_key)
    if not src:
        return False
    src_first, src_last = src
    cur_first = _clean_name_part(contact.first_name)
    cur_last = _clean_name_part(contact.last_name)
    changed = False
    if cur_first is None and src_first:
        if apply:
            contact.first_name = src_first
        changed = True
    if cur_last is None and src_last:
        if apply:
            contact.last_name = src_last
        changed = True
    return changed


async def _backfill_names_on_missed_call_contacts(
    session,
    company_id: UUID,
    start_dt: datetime | None,
    end_dt: datetime | None,
    name_by_phone: dict[str, tuple[str | None, str | None]],
    ambiguous_phones: set[str],
    apply: bool,
) -> tuple[int, list[str]]:
    """
    Distinct contact_card_id from company missed calls; fill missing names from old company.
    """
    conds = [
        CallORM.company_id == company_id,
        CallORM.contact_card_id.isnot(None),
        or_(CallORM.missed_call == True, CallORM.call_type == "missed_call"),
    ]
    if start_dt is not None:
        conds.append(CallORM.created_at >= start_dt)
    if end_dt is not None:
        conds.append(CallORM.created_at <= end_dt)

    r = await session.execute(select(CallORM.contact_card_id).where(*conds).distinct())
    cc_ids = [row[0] for row in r.all()]

    filled = 0
    previews: list[str] = []
    seen_fill: set[UUID] = set()

    for cc_id in cc_ids:
        contact = await session.get(ContactCardORM, cc_id)
        if not contact or contact.company_id != company_id:
            continue
        key = _normalize_phone(contact.primary_phone)
        if not key:
            continue
        before_first = _clean_name_part(contact.first_name)
        before_last = _clean_name_part(contact.last_name)
        if not _apply_old_company_names_if_missing(
            contact, key, name_by_phone, ambiguous_phones, apply
        ):
            continue
        if cc_id in seen_fill:
            continue
        seen_fill.add(cc_id)
        filled += 1
        src = name_by_phone.get(key) or (None, None)
        sf, sl = src
        after_first = _clean_name_part(contact.first_name) if apply else (before_first or sf)
        after_last = _clean_name_part(contact.last_name) if apply else (before_last or sl)
        previews.append(
            f"contact={cc_id} phone={contact.primary_phone} "
            f"({before_first or '-'}, {before_last or '-'}) -> ({after_first or '-'}, {after_last or '-'})"
        )

    return filled, previews


async def link_calls(
    company_id: UUID,
    apply: bool,
    limit: int | None,
    start_date: date | None,
    end_date: date | None,
    old_company_id: UUID | None,
) -> None:
    start_dt, end_dt = _day_bounds(start_date, end_date)

    async with AsyncSessionLocal() as session:
        name_by_phone: dict[str, tuple[str | None, str | None]] = {}
        ambiguous_phones: set[str] = set()
        if old_company_id:
            name_by_phone, ambiguous_phones = await _load_name_map_from_old_company(
                session, old_company_id
            )

        # Existing contacts for company: normalized phone -> first ORM row (stable pick)
        cc_result = await session.execute(
            select(ContactCardORM).where(ContactCardORM.company_id == company_id)
        )
        contacts = cc_result.scalars().all()
        norm_to_contact: dict[str, ContactCardORM] = {}
        for c in contacts:
            key = _normalize_phone(c.primary_phone)
            if key and key not in norm_to_contact:
                norm_to_contact[key] = c

        conds = [
            CallORM.company_id == company_id,
            or_(CallORM.missed_call == True, CallORM.call_type == "missed_call"),
            or_(CallORM.lead_id.is_(None), CallORM.contact_card_id.is_(None)),
        ]
        if start_dt is not None:
            conds.append(CallORM.created_at >= start_dt)
        if end_dt is not None:
            conds.append(CallORM.created_at <= end_dt)

        q = select(CallORM).where(*conds).order_by(CallORM.created_at.desc())
        if limit is not None:
            q = q.limit(limit)
        calls_result = await session.execute(q)
        calls = calls_result.scalars().all()

        would_create_contacts = 0
        would_create_leads = 0
        would_update_calls = 0
        contacts_named_in_link_loop: set[UUID] = set()
        skipped_bad_phone = 0
        preview: list[str] = []

        for call in calls:
            phone_raw = (call.phone_number or "").strip()
            if not phone_raw or phone_raw.lower() == "anonymous":
                skipped_bad_phone += 1
                continue
            phone_key = _normalize_phone(phone_raw)
            if not phone_key:
                skipped_bad_phone += 1
                continue

            contact: ContactCardORM | None = None
            if call.contact_card_id:
                contact = await session.get(ContactCardORM, call.contact_card_id)
            if contact is None:
                contact = norm_to_contact.get(phone_key)
            if contact is None:
                would_create_contacts += 1
                contact = ContactCardORM(
                    id=uuid4(),
                    company_id=company_id,
                    primary_phone=phone_raw,
                    first_name=None,
                    last_name=None,
                )
                if apply:
                    session.add(contact)
                    await session.flush()
                norm_to_contact[phone_key] = contact

            if old_company_id and _apply_old_company_names_if_missing(
                contact,
                phone_key,
                name_by_phone,
                ambiguous_phones,
                apply,
            ):
                contacts_named_in_link_loop.add(contact.id)

            lead: LeadORM | None = None
            if call.lead_id:
                lead = await session.get(LeadORM, call.lead_id)
            if lead is None:
                lr = await session.execute(
                    select(LeadORM)
                    .where(
                        LeadORM.company_id == company_id,
                        LeadORM.contact_card_id == contact.id,
                    )
                    .order_by(LeadORM.created_at.desc())
                    .limit(1)
                )
                lead = lr.scalar_one_or_none()
            if lead is None:
                would_create_leads += 1
                # Align with call time so date-filtered CSR/metrics queries still see the row.
                lead_created = call.created_at or datetime.now(timezone.utc)
                lead = LeadORM(
                    id=uuid4(),
                    company_id=company_id,
                    contact_card_id=contact.id,
                    status="new",
                    created_at=lead_created,
                )
                if apply:
                    session.add(lead)
                    await session.flush()

            need_patch = (
                call.contact_card_id != contact.id or call.lead_id != lead.id
            )
            if need_patch:
                would_update_calls += 1
                preview.append(
                    f"call={call.id} phone={phone_raw} -> "
                    f"contact={contact.id} lead={lead.id}"
                )
                if apply:
                    call.contact_card_id = contact.id
                    call.lead_id = lead.id

        names_pass2 = 0
        name_pass2_previews: list[str] = []
        if old_company_id:
            names_pass2, name_pass2_previews = await _backfill_names_on_missed_call_contacts(
                session,
                company_id,
                start_dt,
                end_dt,
                name_by_phone,
                ambiguous_phones,
                apply,
            )

        print("\n=== Link missed calls -> contact_card + lead ===")
        print(f"Company: {company_id}")
        if start_date or end_date:
            print(f"Date filter: {start_date} .. {end_date} (UTC)")
        if limit is not None:
            print(f"Limit: {limit}")
        if old_company_id:
            print(f"Name source (old company): {old_company_id}")
        print(f"Calls scanned (orphan missed): {len(calls)}")
        print(f"Skipped (no usable phone): {skipped_bad_phone}")
        print(f"New contacts to add: {would_create_contacts}")
        print(f"New leads to add: {would_create_leads}")
        print(f"Calls to update: {would_update_calls}")
        if old_company_id:
            print(
                f"Contacts with names filled (link loop): {len(contacts_named_in_link_loop)}; "
                f"missed-call contacts pass: {names_pass2}"
            )
        print("\nSample (up to 25):")
        for row in preview[:25]:
            print(f"  {row}")
        if len(preview) > 25:
            print(f"  ... and {len(preview) - 25} more")

        if old_company_id and name_pass2_previews:
            print("\nName backfill on missed-call contacts (sample, up to 25):")
            for row in name_pass2_previews[:25]:
                print(f"  {row}")
            if len(name_pass2_previews) > 25:
                print(f"  ... and {len(name_pass2_previews) - 25} more")

        if apply:
            await session.commit()
            print("\nApplied and committed.")
        else:
            await session.rollback()
            print("\nDry run — no changes committed. Re-run with --apply.")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Backfill contact_card_id and lead_id on missed calls for one company"
    )
    p.add_argument("--company-id", required=True, type=UUID, help="Target company UUID")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default is dry run)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max calls to process (most recent first)",
    )
    p.add_argument("--start-date", type=date.fromisoformat, default=None)
    p.add_argument("--end-date", type=date.fromisoformat, default=None)
    p.add_argument(
        "--old-company-id",
        type=UUID,
        default=None,
        help="Source company: fill missing first/last on contacts (link loop + all missed-call-linked cards)",
    )
    args = p.parse_args()

    async def _run() -> None:
        try:
            await link_calls(
                company_id=args.company_id,
                apply=args.apply,
                limit=args.limit,
                start_date=args.start_date,
                end_date=args.end_date,
                old_company_id=args.old_company_id,
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
