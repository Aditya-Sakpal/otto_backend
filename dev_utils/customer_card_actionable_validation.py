#!/usr/bin/env python3
"""
Validate customer-card actionable-only follow-up filtering.

Cases:
1. pending task -> visible
2. in_progress task -> visible
3. completed task -> hidden
4. cancelled task -> hidden
5. no actionable tasks -> empty state
6. existing customer-card behavior not broken (response shape sanity)
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if not _mod.stem.startswith("_"):
        importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from app.infrastructure.database.models.lead import LeadORM  # noqa: E402
from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.services.lead_service import LeadService  # noqa: E402

UTC = timezone.utc
TAG = "customer_card_actionable_validation"
EVIDENCE = ROOT / "dev_utils" / "evidence"


def sync_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql: str, params=()):
    conn = psycopg2.connect(sync_url())
    cur = conn.cursor()
    cur.execute(sql, params)
    count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return count


async def pick_lead() -> tuple[str, str]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(LeadORM.id, LeadORM.company_id).where(LeadORM.contact_card_id.isnot(None)).limit(100)
        )
        candidates = rows.all()
        if not candidates:
            raise RuntimeError("No lead with contact_card_id found for validation")

        service = LeadService(session)
        for lead_id, company_id in candidates:
            card = await service.get_customer_card(lead_id)
            has_follow_up = bool(card and card.result and card.result.follow_up)
            if has_follow_up:
                return str(lead_id), str(company_id)

        raise RuntimeError(
            "No lead with customer-card result.follow_up found for validation preconditions"
        )


def seed_actions(company_id: str, lead_id: str, statuses: list[str]) -> list[str]:
    now = datetime.now(UTC)
    created_ids: list[str] = []
    for idx, status in enumerate(statuses):
        action_id = str(uuid4())
        due_at = now + timedelta(minutes=10 + idx)
        db_exec(
            "INSERT INTO pending_actions "
            "(id, company_id, lead_id, action_type, raw_text, status, due_at, priority, source, extra_metadata, created_at) "
            "VALUES (%s, %s, %s, 'follow_up', %s, %s, %s, 2, %s, %s::jsonb, now())",
            (
                action_id,
                company_id,
                lead_id,
                f"{TAG}:{status}:{idx}",
                status,
                due_at,
                TAG,
                json.dumps({"validator_tag": TAG}),
            ),
        )
        created_ids.append(action_id)
    return created_ids


def cleanup(lead_id: str):
    db_exec(
        "DELETE FROM pending_actions WHERE lead_id = %s AND (source = %s OR raw_text LIKE %s)",
        (lead_id, TAG, f"{TAG}:%"),
    )


async def fetch_customer_card(lead_id: str):
    async with AsyncSessionLocal() as session:
        service = LeadService(session)
        return await service.get_customer_card(UUID(lead_id))


async def run() -> dict:
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": {},
        "evidence": {},
    }

    lead_id, company_id = await pick_lead()
    report["evidence"]["lead_id"] = lead_id
    report["evidence"]["company_id"] = company_id

    try:
        cleanup(lead_id)

        # Cases 1-4 + 6 in one seeded run
        seed_actions(company_id, lead_id, ["pending", "in_progress", "completed", "cancelled"])
        card = await fetch_customer_card(lead_id)
        tasks = ((card.result.follow_up.tasks if card and card.result and card.result.follow_up else []) or [])
        statuses = sorted([t.status for t in tasks])

        report["evidence"]["case1_4_statuses_returned"] = statuses
        report["evidence"]["case6_shape_sanity"] = {
            "has_contact": bool(card and card.contact),
            "has_lead_tab": bool(card and card.lead),
            "has_appointment_tab": bool(card and card.appointment),
            "has_result_tab": bool(card and card.result),
            "has_follow_up_tracking": bool(card and card.result and card.result.follow_up),
        }

        report["checks"]["case1_pending_visible"] = "pending" in statuses
        report["checks"]["case2_in_progress_visible"] = "in_progress" in statuses
        report["checks"]["case3_completed_hidden"] = "completed" not in statuses
        report["checks"]["case4_cancelled_hidden"] = "cancelled" not in statuses
        report["checks"]["case6_behavior_not_broken"] = (
            report["evidence"]["case6_shape_sanity"]["has_contact"]
            and report["evidence"]["case6_shape_sanity"]["has_lead_tab"]
            and report["evidence"]["case6_shape_sanity"]["has_result_tab"]
            and report["evidence"]["case6_shape_sanity"]["has_follow_up_tracking"]
        )

        # Case 5: no actionable tasks should produce empty follow_up list
        cleanup(lead_id)
        seed_actions(company_id, lead_id, ["completed", "cancelled"])
        card_empty = await fetch_customer_card(lead_id)
        tasks_empty = (
            (card_empty.result.follow_up.tasks if card_empty and card_empty.result and card_empty.result.follow_up else [])
            or []
        )
        report["evidence"]["case5_task_count"] = len(tasks_empty)
        report["checks"]["case5_empty_when_no_actionable"] = len(tasks_empty) == 0

    finally:
        cleanup(lead_id)

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    report = asyncio.run(run())
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = EVIDENCE / f"customer_card_actionable_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "validation.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nEvidence written to: {out_file}")
    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
