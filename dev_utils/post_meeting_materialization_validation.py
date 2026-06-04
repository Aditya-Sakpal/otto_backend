#!/usr/bin/env python3
"""
Post-meeting action materialization validation (Option B, staging).

Drives the REAL apply_appointment_analysis against the staging DB with a Shunya
summary containing 3 post-meeting actions, and proves they become actionable
PendingAction tasks that surface in Action Center + Follow-up Guidance, owned by
the assigned rep, idempotent across webhook + reconciliation replay.

Non-destructive: synthetic appointment + materialized tasks hard-deleted at end.
Mirrors recording_reconciliation_validation.py / rehash_validation.py.

Cases:
  1. analysis with 3 rep actions → 3 PendingActions created
  2. webhook replay              → no duplicates
  3. reconciliation replay        → no duplicates
  4. tasks appear in Action Center
  5. tasks appear in Follow-up Guidance
  6. assigned-rep ownership correct
  7. no pending_actions           → no tasks

Usage:
    cd backend
    python dev_utils/post_meeting_materialization_validation.py
"""
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if not _mod.stem.startswith("_"):
        importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from sqlalchemy import select  # noqa: E402
from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.infrastructure.database.models.appointment import AppointmentORM  # noqa: E402
from app.services.recording_reconciliation_service import apply_appointment_analysis  # noqa: E402
from app.services.pending_action_service import PendingActionService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
REP = "22d04d63-5151-4c18-b33f-0c60fed70f02"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc

SUMMARY_3_ACTIONS = {
    "summary": {
        "summary": "Roof inspection complete; homeowner wants written proposal.",
        "next_steps": ["Call to confirm Friday"],
        "action_items": ["Send estimate"],
        "pending_actions": [
            {"type": "send_proposal", "owner": "Sales Rep",
             "due_at": "2026-06-05T15:00:00Z", "raw_text": "Send written roof proposal",
             "confidence": 0.95, "contact_method": "email"},
            {"type": "schedule_appointment", "owner": "Sales Rep",
             "due_at": None, "raw_text": "Schedule crew measurement visit",
             "confidence": 0.9, "contact_method": "phone"},
            {"type": "follow_up", "owner": "Sales Rep",
             "due_at": None, "raw_text": "Follow up on HOA approval",
             "confidence": 0.8, "contact_method": "phone"},
            # Customer-owned → must be skipped (not a rep task)
            {"type": "other", "owner": "Customer",
             "due_at": None, "raw_text": "Homeowner to email HOA docs",
             "confidence": 0.7, "contact_method": "email"},
        ],
    },
    "qualification": {"qualification_status": "qualified", "booking_status": "proposal_pending",
                      "follow_up_required": False},
}


def sync_url():
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


def db_rows(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close(); c.close()
    return rows


async def _seed_appointment() -> str:
    appt_id = str(uuid4())
    async with AsyncSessionLocal() as session:
        session.add(AppointmentORM(
            id=UUID(appt_id), company_id=UUID(COMPANY), lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT), scheduled_start=datetime.now(UTC) - timedelta(hours=2),
            assigned_rep_id=UUID(REP), outcome="pending", analysis_status="processing",
            extra_metadata={"tag": "pmm_smoke"},
        ))
        await session.commit()
    return appt_id


async def _apply(appt_id: str, summary: dict):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(AppointmentORM).where(AppointmentORM.id == UUID(appt_id)))
        appt = res.scalar_one()
        await apply_appointment_analysis(session, appt, summary)
        await session.commit()


def _materialized(appt_id: str):
    return db_rows(
        "SELECT id, action_type, owner_id, due_at, raw_text, source, extra_metadata "
        "FROM pending_actions WHERE appointment_id = %s AND source = 'ai_analysis' "
        "AND (extra_metadata->>'materialized_from') = 'post_meeting_analysis' ORDER BY raw_text",
        (appt_id,),
    )


def _cleanup(appt_id: str):
    db_exec("DELETE FROM action_items WHERE appointment_id = %s", (appt_id,))
    db_exec("DELETE FROM pending_actions WHERE appointment_id = %s", (appt_id,))
    db_exec("DELETE FROM appointments WHERE id = %s", (appt_id,))


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    created_appts = []

    try:
        # ── Cases 1, 6: 3 rep actions materialized, owned by rep ──────────
        appt = await _seed_appointment(); created_appts.append(appt)
        await _apply(appt, SUMMARY_3_ACTIONS)
        rows = _materialized(appt)
        report["evidence"]["materialized"] = [
            {k: (str(v) if not isinstance(v, (str, type(None), dict)) else v) for k, v in r.items()}
            for r in rows
        ]
        report["checks"]["case1_three_tasks_created"] = len(rows) == 3  # customer action skipped
        report["checks"]["case6_owner_is_rep"] = all(str(r["owner_id"]) == REP for r in rows)
        report["checks"]["case1_all_followup_family"] = all(
            r["action_type"].startswith("follow_up") for r in rows
        )
        report["checks"]["case1_due_parsed_and_defaulted"] = (
            any(r["raw_text"] == "Send written roof proposal" and r["due_at"] is not None for r in rows)
        )

        # ── Case 2: webhook replay (same apply path) → no duplicates ──────
        await _apply(appt, SUMMARY_3_ACTIONS)
        report["checks"]["case2_webhook_replay_no_dup"] = len(_materialized(appt)) == 3

        # ── Case 3: reconciliation replay → no duplicates ────────────────
        # Reconciliation recovers the same job via the SAME shared apply path.
        await _apply(appt, SUMMARY_3_ACTIONS)
        report["checks"]["case3_reconcile_replay_no_dup"] = len(_materialized(appt)) == 3

        # ── Case 4: tasks appear in Action Center ────────────────────────
        async with AsyncSessionLocal() as session:
            svc = PendingActionService(session)
            ac = await svc.get_action_center(company_id=UUID(COMPANY), owner_id=UUID(REP), limit=200)
        ac_ids = {str(it.id) for g in ac.groups for it in g.items}
        our_ids = {str(r["id"]) for r in rows}
        report["checks"]["case4_in_action_center"] = our_ids.issubset(ac_ids)

        # ── Case 5: tasks appear in Follow-up Guidance ───────────────────
        async with AsyncSessionLocal() as session:
            svc = PendingActionService(session)
            target = rows[0]["id"]
            guidance = await svc.get_follow_up_guidance(UUID(str(target)))
        report["checks"]["case5_guidance_resolves"] = (
            guidance is not None and guidance.action_family == "follow_up"
        )

        # ── Case 7: no pending_actions → no tasks ────────────────────────
        appt2 = await _seed_appointment(); created_appts.append(appt2)
        await _apply(appt2, {"summary": {"summary": "no actions"}, "qualification": {}})
        report["checks"]["case7_no_actions_no_tasks"] = len(_materialized(appt2)) == 0

    finally:
        for a in created_appts:
            _cleanup(a)
        report["cleanup_appointments"] = len(created_appts)

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"post_meeting_materialization_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 64)
    for k, v in report["checks"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\nVERDICT: {report['verdict']}")
    if report["failed_checks"]:
        print(f"FAILED: {report['failed_checks']}")
    print(f"Evidence: {out_dir / 'validation.json'}")
    print("=" * 64)
    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
