#!/usr/bin/env python3
"""
Unified rep work queue validation (Option A, staging).

Drives the REAL WorkQueueService.get_work_queue against the staging DB with a
SYNTHETIC rep + synthetic tasks / unresolved appointment / pending lead, and
proves each section + counts. RBAC (Cases 6/7) is verified at the route level via
TestClient with overridden auth. Non-destructive: all synthetic rows (incl. the
synthetic rep user) hard-deleted at the end.

Mirrors rehash_validation.py / post_meeting_materialization_validation.py.

Cases:
  1. only tasks → tasks populated
  2. unresolved appointments → unresolved section populated
  3. pending leads → leads section populated
  4. all three → all sections populated
  5. counts match underlying data
  6. rep cannot view another rep's queue (route forces self)
  7. executive can view a specified rep's queue
  8. empty workload → valid empty response

Usage:
    cd backend
    python dev_utils/work_queue_validation.py
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

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.services.work_queue_service import WorkQueueService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc
TAG = "wq_smoke"


def sync_url():
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


def make_rep() -> str:
    rep_id = str(uuid4())
    db_exec(
        "INSERT INTO users (id, email, role, is_active, first_name, last_name, company_id) "
        "VALUES (%s, %s, 'sales_rep', true, 'WQ', 'Rep', %s)",
        (rep_id, f"wq-rep-{rep_id[:8]}@example.invalid", COMPANY),
    )
    return rep_id


def seed_task(rep_id, due_minutes=10):
    pid = str(uuid4())
    db_exec(
        "INSERT INTO pending_actions (id, company_id, owner_id, action_type, status, due_at, "
        "priority, source, raw_text, created_at) "
        "VALUES (%s,%s,%s,'follow_up','pending', now() + make_interval(mins => %s), 2, %s, %s, now())",
        (pid, COMPANY, rep_id, due_minutes, TAG, "Follow up with customer"),
    )
    return pid


def seed_unresolved_appt(rep_id):
    aid = str(uuid4())
    db_exec(
        "INSERT INTO appointments (id, company_id, lead_id, contact_card_id, scheduled_start, "
        "assigned_rep_id, outcome, analysis_status, extra_metadata, created_at) "
        "VALUES (%s,%s,%s,%s, now() - interval '2 days', %s, 'pending', 'completed', %s, now())",
        (aid, COMPANY, LEAD, CONTACT, rep_id, json.dumps({"tag": TAG})),
    )
    return aid


def assign_lead(rep_id):
    """Point the shared synthetic LEAD at our rep so it appears in pending_leads;
    snapshot+restore the original assignment."""
    row = db_exec  # no-op alias
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute("SELECT assigned_rep_id, status FROM leads WHERE id = %s", (LEAD,))
    orig = cur.fetchone()
    cur.execute("UPDATE leads SET assigned_rep_id = %s WHERE id = %s", (rep_id, LEAD))
    c.commit(); cur.close(); c.close()
    return orig


def restore_lead(orig):
    db_exec("UPDATE leads SET assigned_rep_id = %s WHERE id = %s", (orig[0], LEAD))


def cleanup(rep_id):
    db_exec("DELETE FROM action_items WHERE owner_id = %s OR appointment_id IN (SELECT id FROM appointments WHERE extra_metadata->>'tag'=%s)", (rep_id, TAG))
    db_exec("DELETE FROM pending_actions WHERE source = %s OR owner_id = %s", (TAG, rep_id))
    db_exec("DELETE FROM appointments WHERE extra_metadata->>'tag' = %s OR assigned_rep_id = %s", (TAG, rep_id))
    db_exec("DELETE FROM users WHERE id = %s", (rep_id,))


async def _wq(rep_id):
    async with AsyncSessionLocal() as session:
        svc = WorkQueueService(session)
        wq = await svc.get_work_queue(company_id=UUID(COMPANY), owner_id=UUID(rep_id), limit=50)
        return wq


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}

    # ── Case 8: brand-new rep, empty workload ────────────────────────────
    rep = make_rep()
    lead_orig = None
    try:
        wq = await _wq(rep)
        report["evidence"]["case8_empty"] = {
            "section_counts": wq.section_counts.model_dump(),
            "next_action": wq.next_action,
        }
        report["checks"]["case8_empty_valid"] = (
            wq.section_counts.tasks == 0 and wq.section_counts.unresolved_appointments == 0
            and wq.section_counts.pending_leads == 0 and wq.next_action is None
        )

        # ── Case 1: only tasks ───────────────────────────────────────────
        seed_task(rep); seed_task(rep)
        wq = await _wq(rep)
        report["checks"]["case1_tasks_only"] = (
            wq.section_counts.tasks == 2 and wq.section_counts.unresolved_appointments == 0
            and wq.next_action is not None
        )

        # ── Case 2: + unresolved appointment ─────────────────────────────
        seed_unresolved_appt(rep)
        wq = await _wq(rep)
        report["checks"]["case2_unresolved_populated"] = (
            wq.section_counts.unresolved_appointments == 1
            and len(wq.unresolved_appointments) == 1
            and wq.unresolved_appointments[0].outcome == "pending"
        )

        # ── Case 3: + pending lead ───────────────────────────────────────
        lead_orig = assign_lead(rep)
        wq = await _wq(rep)
        report["checks"]["case3_leads_populated"] = wq.section_counts.pending_leads >= 1

        # ── Case 4: all three populated ──────────────────────────────────
        report["checks"]["case4_all_sections"] = (
            wq.section_counts.tasks == 2
            and wq.section_counts.unresolved_appointments == 1
            and wq.section_counts.pending_leads >= 1
        )

        # ── Case 5: counts match section list lengths ────────────────────
        report["evidence"]["case5_counts"] = wq.section_counts.model_dump()
        report["checks"]["case5_counts_match"] = (
            wq.section_counts.tasks == sum(len(g.items) for g in wq.tasks)
            and wq.section_counts.unresolved_appointments == len(wq.unresolved_appointments)
            and wq.section_counts.pending_leads == len(wq.pending_leads)
        )

    finally:
        if lead_orig is not None:
            restore_lead(lead_orig)
        cleanup(rep)

    # ── Cases 6/7: RBAC at the route level (TestClient, no DB writes) ────
    report["checks"].update(_rbac_checks(report))

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def _rbac_checks(report) -> dict:
    """Verify owner resolution: rep forced to self; executive may target a rep."""
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.auth import get_current_user
    from app.core.dependencies import get_db
    import app.routes.v1.sales_rep as sr
    from app.domain.enums import UserRole

    captured = {}

    async def fake_wq(self, *, company_id, owner_id, limit):
        captured["owner_id"] = str(owner_id)
        # Return a minimal valid WorkQueueResponse.
        from app.domain.schemas.sales_rep import WorkQueueResponse, WorkQueueSectionCounts
        from app.domain.schemas.tasks import ActionCenterSummary
        return WorkQueueResponse(
            generated_at=datetime.now(UTC), company_id=company_id, owner_id=owner_id,
            next_action=None, task_summary=ActionCenterSummary(), tasks=[],
            unresolved_appointments=[], pending_leads=[],
            section_counts=WorkQueueSectionCounts(),
        )

    sr.WorkQueueService.get_work_queue = fake_wq

    rep_id = uuid4()
    other_rep = uuid4()
    exec_id = uuid4()
    company = uuid4()

    async def _db():
        yield None

    out = {}
    try:
        # Case 6: SALES_REP passes someone else's owner_id → forced to self.
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=rep_id, role=UserRole.SALES_REP, company_id=company)
        with TestClient(app) as c:
            r = c.get(f"/api/v1/sales_rep/work-queue?owner_id={other_rep}")
        out["case6_rep_forced_self"] = r.status_code == 200 and captured.get("owner_id") == str(rep_id)

        # Case 7: EXECUTIVE passes owner_id → honored.
        captured.clear()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=exec_id, role=UserRole.EXECUTIVE, company_id=company)
        with TestClient(app) as c:
            r = c.get(f"/api/v1/sales_rep/work-queue?owner_id={other_rep}")
        out["case7_exec_targets_rep"] = r.status_code == 200 and captured.get("owner_id") == str(other_rep)
    finally:
        app.dependency_overrides.clear()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"work_queue_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 64)
    for k, v in sorted(report["checks"].items()):
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\nVERDICT: {report['verdict']}")
    if report["failed_checks"]:
        print(f"FAILED: {report['failed_checks']}")
    print(f"Evidence: {out_dir / 'validation.json'}")
    print("=" * 64)
    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
