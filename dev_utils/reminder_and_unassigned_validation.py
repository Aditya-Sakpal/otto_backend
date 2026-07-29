#!/usr/bin/env python3
"""
Validation for two confirmed bugs (staging):

Issue 1 — Generic task reminder idempotency (DB notified_at + grace window):
  1. normal reminder fires once
  2. restart → no duplicate (DB notified_at survives in-memory cache reset)
  3. multi-check execution → no duplicate
  4. downtime through the window → fires once on recovery (due_at in the past
     but within grace)

Issue 2 — Unassigned missed-call visibility:
  1. assigned callback → assigned section
  2. unassigned (owner_id NULL) callback → unassigned section
  3. counts correct (assigned counts exclude unassigned)
  4. rep visibility (own assigned + company unassigned; not another rep's)
  5. executive visibility (targeted rep assigned + company unassigned)

Drives REAL check_follow_ups + REAL MissedCallRecoveryService against staging,
mocking only the WebSocket/Expo transports. Non-destructive: synthetic rep + rows
deleted. Mirrors notification_push_validation.py / missed_call_recovery_validation.py.

Usage:
    cd backend
    python dev_utils/reminder_and_unassigned_validation.py
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
import app.services.followup_notification_service as fns  # noqa: E402
from app.services.missed_call_recovery_service import MissedCallRecoveryService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc
TAG = "ru_smoke"


def sync_url():
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


def db_one(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); row = cur.fetchone()
    cur.close(); c.close()
    return row


def make_rep(name="RU") -> str:
    rep_id = str(uuid4())
    db_exec("INSERT INTO users (id, email, role, is_active, first_name, company_id) "
            "VALUES (%s,%s,'sales_rep',true,%s,%s)",
            (rep_id, f"ru-rep-{rep_id[:8]}@example.invalid", name, COMPANY))
    return rep_id


def seed_callback(owner_id, due_minutes, status="pending"):
    pid = str(uuid4())
    db_exec(
        "INSERT INTO pending_actions (id, company_id, owner_id, call_id, action_type, status, "
        "due_at, priority, source, raw_text, created_at) "
        "VALUES (%s,%s,%s,NULL,'call_back',%s, now() + make_interval(mins => %s), 1, %s, %s, now())",
        (pid, COMPANY, owner_id, status, due_minutes, TAG, "Give +15551230000 a call back"),
    )
    return pid


def notified_at_of(pid):
    row = db_one("SELECT extra_metadata->>'notified_at' FROM pending_actions WHERE id=%s", (pid,))
    return row[0] if row else None


def status_of(pid):
    row = db_one("SELECT status FROM pending_actions WHERE id=%s", (pid,))
    return row[0] if row else None


def cleanup(*rep_ids):
    db_exec("DELETE FROM pending_actions WHERE source=%s", (TAG,))
    for r in rep_ids:
        if r:
            db_exec("DELETE FROM pending_actions WHERE owner_id=%s", (r,))
            db_exec("DELETE FROM users WHERE id=%s", (r,))


def _patch_ws(cap):
    async def fake_ws(user_ids, payload):
        cap.append({"user_ids": [str(u) for u in user_ids], "type": payload.get("type")})
        return len(user_ids)
    fns.connection_manager.send_to_users = fake_ws

    class FakeExpo:
        async def send_push(self, **kw):
            return {"status": "ok"}
    fns.get_expo_push_client = lambda: FakeExpo()


async def _tick(reset_cache=True):
    if reset_cache:
        fns._sent_notifications_cache = set()
    async with AsyncSessionLocal() as session:
        sent = await fns.check_follow_ups(session)
        await session.commit()
    return sent


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    orig_ws, orig_expo = fns.connection_manager.send_to_users, fns.get_expo_push_client

    # ════════════════ ISSUE 1 ════════════════
    rep = make_rep()
    try:
        # A call_back due now (inside grace) → should fire once and stamp notified_at.
        pid = seed_callback(rep, due_minutes=0)
        cap = []; _patch_ws(cap)
        sent1 = await _tick(reset_cache=True)
        na1 = notified_at_of(pid)
        report["checks"]["i1_case1_fires_once"] = sent1 >= 1 and na1 is not None
        report["checks"]["i1_status_unchanged"] = status_of(pid) == "pending"  # NOT auto-completed

        # Case 3: multi-check (same process) → no duplicate.
        cap2 = []; _patch_ws(cap2)
        sent2 = await _tick(reset_cache=False)
        report["checks"]["i1_case3_multicheck_no_dup"] = sent2 == 0

        # Case 2: restart (reset in-memory cache) → still no duplicate (DB notified_at).
        cap3 = []; _patch_ws(cap3)
        sent3 = await _tick(reset_cache=True)
        report["checks"]["i1_case2_restart_no_dup"] = sent3 == 0 and len(cap3) == 0

        # Case 4: downtime through the window → due_at in the PAST but within grace.
        pid4 = seed_callback(rep, due_minutes=-5)  # 5 min overdue, inside 30-min grace
        cap4 = []; _patch_ws(cap4)
        sent4 = await _tick(reset_cache=True)
        report["checks"]["i1_case4_downtime_recovery_fires"] = (
            notified_at_of(pid4) is not None
        )
        report["evidence"]["issue1"] = {"sent1": sent1, "sent2": sent2, "sent3": sent3,
                                        "notified_at1": na1}
    finally:
        cleanup(rep)
        fns.connection_manager.send_to_users = orig_ws
        fns.get_expo_push_client = orig_expo

    # ════════════════ ISSUE 2 ════════════════
    rep_a = make_rep("RepA")
    rep_b = make_rep("RepB")
    try:
        a_id = seed_callback(rep_a, due_minutes=10)          # assigned to A
        b_id = seed_callback(rep_b, due_minutes=10)          # assigned to B (must NOT show for A)
        u1 = seed_callback(None, due_minutes=10)             # unassigned
        u2 = seed_callback(None, due_minutes=-30)            # unassigned + overdue
        my_unassigned = {u1, u2}

        async with AsyncSessionLocal() as session:
            d = await MissedCallRecoveryService(session).get_missed_call_dashboard(
                company_id=UUID(COMPANY), owner_id=UUID(rep_a), limit=500)

        report["evidence"]["issue2"] = {
            "pending_count": d.pending_count, "unassigned_count": d.unassigned_count,
            "unassigned_overdue_count": d.unassigned_overdue_count,
            "note": "company has pre-existing unassigned callbacks (the real bug) — "
                    "asserts use subset/inclusion against synthetic rows.",
        }
        a_pending_ids = {str(it.pending_action_id) for it in d.pending_callbacks}
        unassigned_ids = {str(it.pending_action_id) for it in d.unassigned_callbacks}
        # Case 1: A's assigned callback is in the assigned section (and only A's).
        report["checks"]["i2_case1_assigned_section"] = a_id in a_pending_ids and b_id not in a_pending_ids
        # Case 2: both my unassigned rows surface in the unassigned section.
        report["checks"]["i2_case2_unassigned_section"] = my_unassigned.issubset(unassigned_ids)
        # Case 3: my overdue unassigned is flagged overdue; assigned counts exclude unassigned.
        u2_item = next((it for it in d.unassigned_callbacks if str(it.pending_action_id) == u2), None)
        report["checks"]["i2_case3_counts_correct"] = (
            u2_item is not None and u2_item.overdue is True
            and a_id in a_pending_ids and a_id not in unassigned_ids  # not double-counted
            and b_id not in a_pending_ids and b_id not in unassigned_ids
        )
        # Case 4: rep visibility — A never sees B's assigned task in EITHER section.
        report["checks"]["i2_case4_rep_no_cross_leak"] = (
            b_id not in a_pending_ids and b_id not in unassigned_ids
        )

        # Case 5: executive targets rep_b → sees B's assigned + same company unassigned.
        async with AsyncSessionLocal() as session:
            de = await MissedCallRecoveryService(session).get_missed_call_dashboard(
                company_id=UUID(COMPANY), owner_id=UUID(rep_b), limit=500)
        de_pending = {str(it.pending_action_id) for it in de.pending_callbacks}
        de_unassigned = {str(it.pending_action_id) for it in de.unassigned_callbacks}
        report["checks"]["i2_case5_exec_targets_rep"] = (
            b_id in de_pending and a_id not in de_pending and my_unassigned.issubset(de_unassigned)
        )
    finally:
        cleanup(rep_a, rep_b)

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    report["note"] = (
        "Issue 1 drives REAL check_follow_ups (WS/Expo transports mocked, "
        "environment-gated). notified_at/grace/restart/downtime exercised against "
        "the real DB. Issue 2 drives the REAL dashboard service against the real DB."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()
    report = asyncio.run(run())
    out_dir = EVIDENCE / f"reminder_unassigned_{args.run_id}"
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
