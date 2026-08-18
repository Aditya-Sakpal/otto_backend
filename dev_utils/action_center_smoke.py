#!/usr/bin/env python3
"""Non-destructive smoke test for the Action Center service against staging.

Seeds a handful of pending_actions for one synthetic owner_id (a random UUID not
tied to a real user — the query is owner-scoped so it cannot collide), calls the
real PendingActionService.get_action_center, asserts ranking/grouping, and
deletes every row it created.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if not _mod.stem.startswith("_"):
        importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.services.pending_action_service import PendingActionService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
# Real active sales rep for COMPANY (owner_id has a FK to users).
OWNER = "22d04d63-5151-4c18-b33f-0c60fed70f02"


def sync_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


async def main() -> int:
    owner = OWNER
    now = datetime.now(timezone.utc)
    seeds = [
        # (action_type, due_at offset minutes, extra_metadata)
        ("call_back", -5, None),                                             # overdue, top value
        ("appointment_reminder", 10, {"reminder_kind": "one_hour_before"}),  # due_now
        ("appointment_reminder", 10, {"reminder_kind": "day_before"}),       # due_now, lower
        ("rehash", 90, {"rehash_category": "qualified_unbooked"}),           # due_soon
        ("follow_up", None, None),                                           # no_due_date
        ("send_quote", 5, None),                                             # EXCLUDED (not whitelisted)
    ]
    ids = []
    import json
    for atype, off, meta in seeds:
        pid = str(uuid4()); ids.append(pid)
        due = None if off is None else now + timedelta(minutes=off)
        db_exec(
            """
            INSERT INTO pending_actions
              (id, company_id, owner_id, action_type, status, due_at, priority, source, extra_metadata, created_at)
            VALUES (%s, %s, %s, %s, 'pending', %s, 2, 'smoke', %s, now())
            """,
            (pid, COMPANY, owner, atype, due, json.dumps(meta) if meta else None),
        )

    try:
        async with AsyncSessionLocal() as session:
            svc = PendingActionService(session)
            resp = await svc.get_action_center(
                company_id=UUID(COMPANY), owner_id=UUID(owner), limit=50
            )

        checks = {}
        checks["total_excludes_send_quote"] = resp.summary.total == 5
        checks["next_is_overdue_callback"] = (
            resp.next is not None
            and resp.next.action_family == "call_back"
            and resp.next.urgency_tier == "overdue"
        )
        tiers = [g.urgency_tier for g in resp.groups]
        checks["groups_in_tier_order"] = tiers == sorted(
            tiers, key=lambda t: ["overdue", "due_now", "due_soon", "later_today", "upcoming", "no_due_date"].index(t)
        )
        due_now_group = next((g for g in resp.groups if g.urgency_tier == "due_now"), None)
        checks["one_hour_before_first_in_due_now"] = (
            due_now_group is not None
            and due_now_group.items[0].extra_metadata.get("reminder_kind") == "one_hour_before"
        )
        checks["follow_up_in_no_due_date"] = any(
            g.urgency_tier == "no_due_date" and g.items[0].action_family == "follow_up"
            for g in resp.groups
        )

        print("Summary:", resp.summary.model_dump())
        print("Tiers:", tiers)
        print("Next:", resp.next.action_family, resp.next.urgency_tier, "score=", resp.next.value_score)
        for k, v in checks.items():
            print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        ok = all(checks.values())
        print("\nVERDICT:", "GO" if ok else "NO-GO")
        return 0 if ok else 1
    finally:
        deleted = db_exec(
            "DELETE FROM pending_actions WHERE owner_id = %s AND source = 'smoke'",
            (owner,),
        )
        print(f"[cleanup] deleted {deleted} seeded rows")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
