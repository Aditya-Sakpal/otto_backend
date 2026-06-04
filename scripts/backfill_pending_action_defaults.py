#!/usr/bin/env python3
"""
Backfill owner_id, due_at, and priority on historical pending_actions rows.

Defaults (conservative):
- owner_id: from calls.handled_by_user_id or appointments.assigned_rep_id
- due_at: created_at + 24h (skip rows older than 90 days without due_at)
- priority: 3 when null

Usage:
    python scripts/backfill_pending_action_defaults.py --dry-run
    python scripts/backfill_pending_action_defaults.py --apply
    python scripts/backfill_pending_action_defaults.py --apply --company-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_

from app.infrastructure.database.models import (
    PendingActionORM,
    CallORM,
    AppointmentORM,
)
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM  # noqa: F401
from app.infrastructure.database.session import AsyncSessionLocal
from app.domain.enums import PendingActionStatus
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)

MAX_AGE_DAYS = 90
DEFAULT_PRIORITY = 3


async def backfill_pending_action_defaults(
    *,
    apply: bool,
    company_id: UUID | None = None,
    batch_size: int = 200,
) -> None:
    setup_logging()
    now_utc = datetime.now(ZoneInfo("UTC"))
    cutoff = now_utc - timedelta(days=MAX_AGE_DAYS)

    stats = {
        "scanned": 0,
        "owner_from_call": 0,
        "owner_from_appointment": 0,
        "due_at_set": 0,
        "due_at_skipped_stale": 0,
        "priority_set": 0,
        "updated": 0,
    }

    async with AsyncSessionLocal() as session:
        base_filters = [
            PendingActionORM.status == PendingActionStatus.PENDING.value,
            or_(
                PendingActionORM.owner_id.is_(None),
                PendingActionORM.due_at.is_(None),
                PendingActionORM.priority.is_(None),
            ),
        ]
        if company_id:
            base_filters.append(PendingActionORM.company_id == company_id)

        result = await session.execute(
            select(PendingActionORM).where(and_(*base_filters)).order_by(PendingActionORM.created_at)
        )
        rows = list(result.scalars().all())
        stats["scanned"] = len(rows)
        logger.info(f"Found {len(rows)} pending actions needing backfill")

        for idx, row in enumerate(rows, start=1):
            changed = False

            if row.owner_id is None:
                if row.call_id:
                    call_result = await session.execute(
                        select(CallORM.handled_by_user_id).where(CallORM.id == row.call_id)
                    )
                    owner = call_result.scalar_one_or_none()
                    if owner:
                        row.owner_id = owner
                        stats["owner_from_call"] += 1
                        changed = True
                elif row.appointment_id:
                    appt_result = await session.execute(
                        select(AppointmentORM.assigned_rep_id).where(
                            AppointmentORM.id == row.appointment_id
                        )
                    )
                    owner = appt_result.scalar_one_or_none()
                    if owner:
                        row.owner_id = owner
                        stats["owner_from_appointment"] += 1
                        changed = True

            if row.due_at is None and row.created_at:
                created = row.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=ZoneInfo("UTC"))
                if created < cutoff:
                    stats["due_at_skipped_stale"] += 1
                else:
                    row.due_at = created + timedelta(hours=24)
                    stats["due_at_set"] += 1
                    changed = True

            if row.priority is None:
                row.priority = DEFAULT_PRIORITY
                stats["priority_set"] += 1
                changed = True

            if changed:
                stats["updated"] += 1
                if apply:
                    if idx % batch_size == 0:
                        await session.flush()

        if apply and stats["updated"]:
            await session.commit()
            logger.info("Backfill committed")
        elif not apply:
            await session.rollback()
            logger.info("Dry run — no changes committed")

    logger.info("Backfill summary: %s", stats)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill pending action defaults")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only (default)",
    )
    parser.add_argument("--company-id", type=str, default=None)
    args = parser.parse_args()

    apply = args.apply and not args.dry_run
    company_id = UUID(args.company_id) if args.company_id else None

    asyncio.run(
        backfill_pending_action_defaults(
            apply=apply,
            company_id=company_id,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
