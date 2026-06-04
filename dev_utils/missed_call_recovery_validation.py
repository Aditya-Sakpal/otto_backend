#!/usr/bin/env python3
"""
Missed-call recovery dashboard validation (Option A, staging).

Drives the REAL MissedCallRecoveryService.get_missed_call_dashboard against the
staging DB with a SYNTHETIC rep + synthetic call_back tasks (pending, overdue,
completed). RBAC (Cases 5/6) verified at the route via TestClient. Non-destructive:
synthetic rep + tasks hard-deleted at the end.

Mirrors work_queue_validation.py.

Cases:
  1. pending callback → pending section
  2. completed callback → completed section
  3. overdue callback → overdue_count increments
  4. counts match underlying data
  5. rep cannot access another rep's dashboard (route forces self)
  6. executive can target a rep
  7. empty dashboard → valid response

Usage:
    cd backend
    python dev_utils/missed_call_recovery_validation.py
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import re
import sys
from datetime import datetime, timezone
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
from app.services.missed_call_recovery_service import MissedCallRecoveryService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc
TAG = "mcr_smoke"


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
        "VALUES (%s,%s,'sales_rep',true,'MCR','Rep',%s)",
        (rep_id, f"mcr-rep-{rep_id[:8]}@example.invalid", COMPANY),
    )
    return rep_id


def seed_callback(rep_id, status="pending", due_minutes=10, completed_mins_ago=None):
    pid = str(uuid4())
    db_exec(
        "INSERT INTO pending_actions (id, company_id, owner_id, action_type, status, due_at, "
        "priority, source, raw_text, created_at) "
        "VALUES (%s,%s,%s,'call_back',%s, now() + make_interval(mins => %s), 1, %s, %s, now())",
        (pid, COMPANY, rep_id, status, due_minutes, TAG, "Give +15551230000 a call back"),
    )
    if status == "completed" and completed_mins_ago is not None:
        db_exec(
            "UPDATE pending_actions SET updated_at = now() - make_interval(mins => %s) WHERE id = %s",
            (completed_mins_ago, pid),
        )
    return pid


def cleanup(rep_id):
    db_exec("DELETE FROM action_items WHERE owner_id = %s", (rep_id,))
    db_exec("DELETE FROM pending_actions WHERE owner_id = %s", (rep_id,))
    db_exec("DELETE FROM users WHERE id = %s", (rep_id,))


async def _dash(rep_id):
    async with AsyncSessionLocal() as session:
        svc = MissedCallRecoveryService(session)
        return await svc.get_missed_call_dashboard(
            company_id=UUID(COMPANY), owner_id=UUID(rep_id), limit=100, completed_window_hours=24
        )


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    rep = make_rep()

    try:
        # ── Case 7: empty ────────────────────────────────────────────────
        d = await _dash(rep)
        report["checks"]["case7_empty_valid"] = (
            d.pending_count == 0 and d.overdue_count == 0
            and d.completed_today_count == 0 and d.pending_callbacks == []
        )

        # Seed: 2 pending (one overdue), 1 completed-today
        seed_callback(rep, status="pending", due_minutes=10)     # due_now
        seed_callback(rep, status="pending", due_minutes=-30)    # overdue
        seed_callback(rep, status="completed", due_minutes=-60, completed_mins_ago=30)

        d = await _dash(rep)
        report["evidence"]["dashboard"] = {
            "pending_count": d.pending_count,
            "overdue_count": d.overdue_count,
            "completed_today_count": d.completed_today_count,
            "pending": len(d.pending_callbacks),
            "completed": len(d.completed_callbacks),
        }

        # ── Case 1: pending in pending section ───────────────────────────
        report["checks"]["case1_pending_section"] = d.pending_count == 2 and len(d.pending_callbacks) == 2
        # ── Case 2: completed in completed section ───────────────────────
        report["checks"]["case2_completed_section"] = (
            len(d.completed_callbacks) == 1 and d.completed_callbacks[0].completed_at is not None
        )
        # ── Case 3: overdue count ────────────────────────────────────────
        report["checks"]["case3_overdue_count"] = d.overdue_count == 1
        # ── Case 4: counts match ─────────────────────────────────────────
        report["checks"]["case4_counts_match"] = (
            d.pending_count == len(d.pending_callbacks)
            and d.overdue_count == sum(1 for it in d.pending_callbacks if it.overdue)
            and d.completed_today_count == 1
        )

    finally:
        cleanup(rep)

    # ── Cases 5/6: RBAC at the route level ───────────────────────────────
    report["checks"].update(_rbac_checks())

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def _rbac_checks() -> dict:
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.auth import get_current_user
    from app.core.dependencies import get_db
    import app.routes.v1.sales_rep as sr
    from app.domain.enums import UserRole
    from app.domain.schemas.sales_rep import MissedCallRecoveryResponse

    captured = {}

    async def fake_dash(self, *, company_id, owner_id, limit, completed_window_hours):
        captured["owner_id"] = str(owner_id)
        return MissedCallRecoveryResponse(
            generated_at=datetime.now(UTC), company_id=company_id, owner_id=owner_id,
            pending_callbacks=[], completed_callbacks=[],
            pending_count=0, overdue_count=0, completed_today_count=0,
        )

    sr.MissedCallRecoveryService.get_missed_call_dashboard = fake_dash

    rep_id, other_rep, exec_id, company = uuid4(), uuid4(), uuid4(), uuid4()

    async def _db():
        yield None

    out = {}
    try:
        app.dependency_overrides[get_db] = _db
        # Case 5: rep passes another owner_id → forced to self
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=rep_id, role=UserRole.SALES_REP, company_id=company)
        with TestClient(app) as c:
            r = c.get(f"/api/v1/sales_rep/missed-calls?owner_id={other_rep}")
        out["case5_rep_forced_self"] = r.status_code == 200 and captured.get("owner_id") == str(rep_id)

        # Case 6: executive targets a rep
        captured.clear()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=exec_id, role=UserRole.EXECUTIVE, company_id=company)
        with TestClient(app) as c:
            r = c.get(f"/api/v1/sales_rep/missed-calls?owner_id={other_rep}")
        out["case6_exec_targets_rep"] = r.status_code == 200 and captured.get("owner_id") == str(other_rep)
    finally:
        app.dependency_overrides.clear()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"missed_call_recovery_{args.run_id}"
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
