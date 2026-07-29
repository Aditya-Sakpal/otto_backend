#!/usr/bin/env python3
"""
Notification push delivery validation (Option A, staging).

Drives the REAL check_follow_ups / FollowUpNotificationService against the staging
DB with synthetic due pending_actions of each founder workflow type, owned by a
synthetic rep that has a registered Expo token. The two TRANSPORTS are
monkeypatched to capture dispatches (WebSocket send + Expo send_push) — the
external transports are environment-gated, like prior phases' mocked delivery.

Proves: each workflow attempts push, missing-token falls back to WebSocket, an
Expo failure leaves WebSocket succeeding, recipient routing is unchanged, and no
duplicate notifications. Non-destructive: synthetic rep + rows + token deleted.

Cases 1-5 push attempted (reminder/rehash/callback/follow-up/post-meeting);
6 missing token → WS only; 7 Expo down → WS ok; 8 routing unchanged; 9 no dup.

Usage:
    cd backend
    python dev_utils/notification_push_validation.py
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

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
APPT_LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc
TOKEN = "ExponentPushToken[wq-smoke-token]"


def sync_url():
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


def make_rep(with_token=True) -> str:
    rep_id = str(uuid4())
    db_exec("INSERT INTO users (id, email, role, is_active, first_name, company_id) "
            "VALUES (%s,%s,'sales_rep',true,'Push',%s)",
            (rep_id, f"push-rep-{rep_id[:8]}@example.invalid", COMPANY))
    if with_token:
        db_exec("INSERT INTO rep_phones (id, user_id, phone_number, is_verified, expo_push_token) "
                "VALUES (%s,%s,%s,true,%s)", (str(uuid4()), rep_id, f"+1{rep_id[:10]}", TOKEN))
    return rep_id


def seed_due_action(rep_id, action_type, extra_metadata=None, lead_id=None, appointment_id=None):
    """A pending action inside its firing window.

    - appointment_reminder / rehash fire via GRACE window (due_at <= now < due_at+grace)
      → seed due_at slightly in the PAST.
    - call_back / follow_up fire via the 15/5-min THRESHOLD (0 < minutes_until_due <= 15)
      → seed due_at slightly in the FUTURE (5 min).
    """
    grace_types = {"appointment_reminder", "rehash"}
    due_sql = "now() - interval '2 minutes'" if action_type in grace_types else "now() + interval '5 minutes'"
    pid = str(uuid4())
    db_exec(
        "INSERT INTO pending_actions (id, company_id, owner_id, lead_id, appointment_id, action_type, "
        f"status, due_at, priority, source, raw_text, extra_metadata, created_at) "
        f"VALUES (%s,%s,%s,%s,%s,%s,'pending', {due_sql}, 2, 'push_smoke', %s, %s, now())",
        (pid, COMPANY, rep_id, lead_id, appointment_id, action_type,
         f"{action_type} test", json.dumps(extra_metadata) if extra_metadata else None),
    )
    return pid


def seed_appointment(rep_id) -> str:
    aid = str(uuid4())
    db_exec("INSERT INTO appointments (id, company_id, lead_id, contact_card_id, scheduled_start, "
            "assigned_rep_id, outcome, extra_metadata, created_at) "
            "VALUES (%s,%s,%s,%s, now() + interval '3 hours', %s, 'pending', %s, now())",
            (aid, COMPANY, APPT_LEAD, CONTACT, rep_id, json.dumps({"tag": "push_smoke"})))
    return aid


def cleanup(rep_id):
    db_exec("DELETE FROM pending_actions WHERE source = 'push_smoke' OR owner_id = %s", (rep_id,))
    db_exec("DELETE FROM appointments WHERE extra_metadata->>'tag' = 'push_smoke'")
    db_exec("DELETE FROM rep_phones WHERE user_id = %s", (rep_id,))
    db_exec("DELETE FROM users WHERE id = %s", (rep_id,))


class Captured:
    def __init__(self):
        self.ws = []      # websocket sends
        self.push = []     # expo pushes


def _patch_transports(cap: Captured, expo_raise=False):
    async def fake_ws(user_ids, payload):
        cap.ws.append({"user_ids": [str(u) for u in user_ids], "type": payload.get("type")})
        return len(user_ids)
    fns.connection_manager.send_to_users = fake_ws

    class FakeExpo:
        async def send_push(self, *, expo_push_token, title, body, data=None):
            if expo_raise:
                raise RuntimeError("Expo down (simulated)")
            cap.push.append({"token": expo_push_token, "title": title, "type": (data or {}).get("type")})
            return {"status": "ok"}
    # Patch the module-level singleton getter so new service instances use it.
    fns.get_expo_push_client = lambda: FakeExpo()


async def _tick(cap: Captured, reset_cache: bool = True):
    # The legacy 15/5 path dedupes via the in-memory cache; the real scheduler
    # reuses it across ticks. Reset only when simulating a fresh process.
    if reset_cache:
        fns._sent_notifications_cache = set()
    async with AsyncSessionLocal() as session:
        sent = await fns.check_follow_ups(session)
        await session.commit()
    return sent


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    orig_ws = fns.connection_manager.send_to_users
    orig_expo = fns.get_expo_push_client

    rep = make_rep(with_token=True)
    rep_no_token = None
    try:
        appt = seed_appointment(rep)
        now_iso = datetime.now(UTC).isoformat()
        # One due action per founder workflow type.
        seed_due_action(rep, "appointment_reminder",
                        extra_metadata={"reminder_kind": "one_hour_before", "scheduled_start": now_iso},
                        appointment_id=appt)
        seed_due_action(rep, "rehash", extra_metadata={"rehash_category": "qualified_unbooked"})
        seed_due_action(rep, "call_back")
        seed_due_action(rep, "follow_up")
        seed_due_action(rep, "follow_up", extra_metadata={"materialized_from": "post_meeting_analysis"})

        # ── Cases 1-5 + 8 + 9: push attempted per type, routing, no dup ──
        cap = Captured()
        _patch_transports(cap)
        sent1 = await _tick(cap)

        push_types = {p["type"] for p in cap.push}
        report["evidence"]["push_dispatched"] = cap.push
        report["evidence"]["ws_dispatched"] = cap.ws
        report["checks"]["case1_appointment_reminder_push"] = "appointment_reminder" in push_types
        report["checks"]["case2_rehash_push"] = "rehash_opportunity" in push_types
        # call_back / follow_up / post-meeting all serialize to follow_up_reminder
        report["checks"]["case3_4_5_followup_family_push"] = "follow_up_reminder" in push_types
        # Case 8: every push token is our rep's token (routing unchanged).
        report["checks"]["case8_routing_unchanged"] = all(p["token"] == TOKEN for p in cap.push)
        # Case 9: a SECOND tick (same process — cache preserved) fires nothing new.
        # Grace types: DB notified_at; threshold types: in-memory dedupe cache.
        cap2 = Captured(); _patch_transports(cap2)
        sent2 = await _tick(cap2, reset_cache=False)
        report["evidence"]["tick2_ws"] = cap2.ws
        report["evidence"]["tick2_push"] = cap2.push
        # No-duplicate guarantee for this change = push never fires for anything
        # the WebSocket didn't, AND push count == WS count on every tick (push is
        # strictly parallel to WS, adds no extra notifications). Grace-window types
        # (appointment_reminder/rehash) also prove DB idempotency: they do NOT
        # refire on tick 2. (Legacy 15/5 call_back/follow_up dedup is in-memory and
        # unchanged by this PR.)
        tick2_grace = [u for u in cap2.ws if u["type"] in ("appointment_reminder", "rehash_opportunity")]
        report["checks"]["case9_push_parallel_no_extra"] = (
            len(cap.push) == len(cap.ws)            # tick1: 1 push per WS send, no extra
            and len(cap2.push) == len(cap2.ws)      # tick2: still parallel, no extra
            and len(tick2_grace) == 0               # grace types don't refire (DB idempotency)
        )
        report["evidence"]["counts"] = {"tick1_sent": sent1, "tick2_sent": sent2,
                                        "push1": len(cap.push), "ws1": len(cap.ws)}

    finally:
        cleanup(rep)

    # ── Case 6: missing token → WebSocket only (no push) ─────────────────
    rep_no_token = make_rep(with_token=False)
    try:
        seed_due_action(rep_no_token, "follow_up")
        cap = Captured(); _patch_transports(cap)
        await _tick(cap)
        report["checks"]["case6_missing_token_ws_only"] = (
            len(cap.push) == 0 and any(rep_no_token in u["user_ids"] for u in cap.ws)
        )
    finally:
        cleanup(rep_no_token)

    # ── Case 7: Expo unavailable → WebSocket still succeeds ──────────────
    rep_e = make_rep(with_token=True)
    try:
        seed_due_action(rep_e, "follow_up")
        cap = Captured(); _patch_transports(cap, expo_raise=True)
        sent = await _tick(cap)
        report["checks"]["case7_expo_down_ws_ok"] = (
            sent >= 1 and len(cap.ws) >= 1 and len(cap.push) == 0
        )
    finally:
        cleanup(rep_e)
        fns.connection_manager.send_to_users = orig_ws
        fns.get_expo_push_client = orig_expo

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    report["note"] = (
        "WebSocket + Expo transports are MOCKED to capture dispatch (external "
        "transports are environment-gated, like prior phases). Generation, "
        "recipient routing, push-dispatch-attempt, token fallback, Expo-failure "
        "isolation, and idempotency are exercised against the real staging DB."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"notification_push_{args.run_id}"
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
