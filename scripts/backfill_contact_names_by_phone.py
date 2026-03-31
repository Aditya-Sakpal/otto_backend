"""
Backfill missing contact names in a target company using phone matches from a source company.

Use case:
- You have historical calls in an old company with contact names.
- New company has contacts with same phone numbers but missing first/last names.
- This script copies names from old -> new by normalized phone number.

Behavior:
- Matches by normalized phone (digits only, prefers last 10 digits for US numbers).
- Only updates contacts in new company where first_name or last_name is missing/blank.
- Skips ambiguous phones in old company (multiple distinct names for same phone).

Usage:
    python scripts/backfill_contact_names_by_phone.py \
      --old-company-id ce9091df-db37-4e7e-877c-2ed0cf2f4c37 \
      --new-company-id b05c2c61-20d4-4a20-96e8-ca1bb6a64972

    python scripts/backfill_contact_names_by_phone.py \
      --old-company-id ce9091df-db37-4e7e-877c-2ed0cf2f4c37 \
      --new-company-id b05c2c61-20d4-4a20-96e8-ca1bb6a64972 \
      --apply
"""
import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database.session import AsyncSessionLocal, engine
import app.infrastructure.database.models  # noqa: F401 - ensure ORM models are registered
import app.infrastructure.database.models.company_integration  # noqa: F401 - CompanyORM.integrations → CompanyIntegrationORM
from app.infrastructure.database.models.contact import ContactCardORM


def _normalize_phone(phone: str | None) -> str | None:
    """Normalize phone to comparable key (prefer last 10 digits when available)."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _clean_name_part(value: str | None) -> str | None:
    """Normalize blank names to None and trim whitespace."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def backfill_names(
    old_company_id: UUID,
    new_company_id: UUID,
    apply: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        # 1) Load old-company contacts with names
        old_result = await session.execute(
            select(ContactCardORM).where(ContactCardORM.company_id == old_company_id)
        )
        old_contacts = old_result.scalars().all()

        # phone -> set of (first_name, last_name) candidates
        names_by_phone: dict[str, set[tuple[str | None, str | None]]] = defaultdict(set)

        for c in old_contacts:
            phone_key = _normalize_phone(c.primary_phone)
            if not phone_key:
                continue
            first = _clean_name_part(c.first_name)
            last = _clean_name_part(c.last_name)
            if not first and not last:
                continue
            names_by_phone[phone_key].add((first, last))

        unique_names_by_phone: dict[str, tuple[str | None, str | None]] = {}
        ambiguous_phones: set[str] = set()
        for phone_key, candidates in names_by_phone.items():
            if len(candidates) == 1:
                unique_names_by_phone[phone_key] = next(iter(candidates))
            else:
                ambiguous_phones.add(phone_key)

        # 2) Load new-company contacts
        new_result = await session.execute(
            select(ContactCardORM).where(ContactCardORM.company_id == new_company_id)
        )
        new_contacts = new_result.scalars().all()

        total_new = len(new_contacts)
        missing_name_contacts = 0
        matched_by_phone = 0
        updated_contacts = 0
        skipped_ambiguous = 0
        skipped_no_match = 0

        preview_rows: list[str] = []

        for c in new_contacts:
            first_current = _clean_name_part(c.first_name)
            last_current = _clean_name_part(c.last_name)
            needs_update = (first_current is None) or (last_current is None)
            if not needs_update:
                continue

            missing_name_contacts += 1
            phone_key = _normalize_phone(c.primary_phone)
            if not phone_key:
                skipped_no_match += 1
                continue

            if phone_key in ambiguous_phones:
                skipped_ambiguous += 1
                continue

            source_name = unique_names_by_phone.get(phone_key)
            if not source_name:
                skipped_no_match += 1
                continue

            matched_by_phone += 1
            src_first, src_last = source_name
            next_first = first_current or src_first
            next_last = last_current or src_last

            if next_first == first_current and next_last == last_current:
                continue

            updated_contacts += 1
            preview_rows.append(
                f"{c.id} | phone={c.primary_phone} | "
                f"{first_current or '-'} {last_current or '-'} -> "
                f"{next_first or '-'} {next_last or '-'}"
            )

            if apply:
                c.first_name = next_first
                c.last_name = next_last

        print("\n=== Backfill Contact Names By Phone ===")
        print(f"Old company: {old_company_id}")
        print(f"New company: {new_company_id}")
        print(f"Total contacts in new company: {total_new}")
        print(f"Contacts with missing first/last name: {missing_name_contacts}")
        print(f"Matched by phone (unique source name): {matched_by_phone}")
        print(f"Will update / updated contacts: {updated_contacts}")
        print(f"Skipped (ambiguous phone in old company): {skipped_ambiguous}")
        print(f"Skipped (no phone match): {skipped_no_match}")

        print("\nSample changes (up to 25):")
        for row in preview_rows[:25]:
            print(f"  {row}")
        if len(preview_rows) > 25:
            print(f"  ... and {len(preview_rows) - 25} more")

        if apply:
            await session.commit()
            print("\nApplied changes and committed.")
        else:
            await session.rollback()
            print("\nDry run only. No changes committed. Re-run with --apply to persist.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill missing contact names in new company from old company by phone"
    )
    parser.add_argument("--old-company-id", required=True, help="Source (old) company UUID")
    parser.add_argument("--new-company-id", required=True, help="Target (new) company UUID")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update DB records. Without this, script runs in dry-run mode.",
    )
    args = parser.parse_args()

    old_company_id = UUID(args.old_company_id)
    new_company_id = UUID(args.new_company_id)

    async def _run() -> None:
        try:
            await backfill_names(old_company_id, new_company_id, apply=args.apply)
        finally:
            await engine.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()

