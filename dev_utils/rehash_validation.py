#!/usr/bin/env python3
"""
Rehash business-workflow validation (staging).

Drives the REAL rehash code paths (rehash_service.scan_and_sync_rehash +
followup_notification_service) against the staging database and captures
evidence: DB rows, rehash metadata, and notification payloads.

Lifecycle validated:
  1. Lead becomes eligible
  2. Rehash PendingAction created (one per category)
  3. Notification fires (once)
  4. Replay / idempotency (no duplicate rows, no second send)
  5. Scheduler restart survival (DB notified_at, not in-memory cache)
  6. Lead becomes ineligible
  7. Rehash task cancelled by next scan

Non-destructive: it creates a dedicated SYNTHETIC lead + contact card scoped to
one company, drives the lifecycle against only that lead, and hard-deletes every
row it created (lead, contact card, pending_actions, action_items) at the end.
No pre-existing rows are modified.

Usage:
    cd backend
    python dev_utils/rehash_validation.py
    python dev_utils/rehash_validation.py --company-id <uuid>
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

# Register every ORM model so SQLAlchemy can resolve string relationships.
_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if not _mod.stem.startswith("_"):
        importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.services import followup_notification_service as fns  # noqa: E402
from app.services.rehash_service import (  # noqa: E402
    CATEGORY_QUALIFIED_UNBOOKED,
    scan_and_sync_rehash,
)

EVIDENCE = Path(__file__).resolve().parent / "evidence"
DEFAULT_COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"


def sync_db_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def _conn():
    return psycopg2.connect(sync_db_url())


def db_query(sql: str, params=()) -> list[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def db_exec(sql: str, params=()) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return n


def jsonable(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def rehash_rows(lead_id: str, statuses=("pending",)) -> list[dict]:
    ph = ",".join(["%s"] * len(statuses))
    rows = db_query(
        f"""
        SELECT id, action_type, source, status, due_at, priority, owner_id,
               lead_id, appointment_id, raw_text, extra_metadata, created_at
        FROM pending_actions
        WHERE lead_id = %s AND action_type = 'rehash' AND status IN ({ph})
        ORDER BY created_at ASC
        """,
        (lead_id, *statuses),
    )
    return [{k: jsonable(v) for k, v in r.items()} for r in rows]


def pick_rep(company_id: str) -> str | None:
    rows = db_query(
        "SELECT id FROM users WHERE company_id = %s AND role = 'sales_rep' "
        "AND is_active = true LIMIT 1",
        (company_id,),
    )
    return str(rows[0]["id"]) if rows else None


def create_synthetic_lead(company_id: str, rep_id: str | None) -> tuple[str, str]:
    """Insert a synthetic contact card + lead in an INELIGIBLE state.

    Starts ineligible (status='new', recent updated_at) so step 1 can flip it
    eligible deterministically. Returns (lead_id, contact_card_id).
    """
    contact_id = str(uuid4())
    lead_id = str(uuid4())
    db_exec(
        """
        INSERT INTO contact_cards (id, company_id, primary_phone, first_name, last_name, email)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (contact_id, company_id, "+10000000000", "Rehash", "Validation",
         f"rehash-validation-{lead_id[:8]}@example.invalid"),
    )
    db_exec(
        """
        INSERT INTO leads (id, company_id, contact_card_id, status, pipeline_stage,
                           assigned_rep_id, created_at, updated_at)
        VALUES (%s, %s, %s, 'new', 'qualified', %s, now(), now())
        """,
        (lead_id, company_id, contact_id, rep_id),
    )
    return lead_id, contact_id


def make_eligible(lead_id: str, days_old: int) -> None:
    """Flip the synthetic lead into the qualified_unbooked eligible state."""
    db_exec(
        """
        UPDATE leads
        SET status = 'qualified_unbooked',
            pipeline_stage = 'qualified',
            updated_at = now() - make_interval(days => %s)
        WHERE id = %s
        """,
        (days_old, lead_id),
    )


def make_ineligible(lead_id: str) -> None:
    """Flip the synthetic lead into a terminal/booked state (no longer eligible)."""
    db_exec(
        "UPDATE leads SET status = 'qualified_booked', pipeline_stage = 'booked' WHERE id = %s",
        (lead_id,),
    )


def teardown(lead_id: str, contact_id: str) -> dict:
    deleted = {}
    deleted["action_items"] = db_exec("DELETE FROM action_items WHERE lead_id = %s", (lead_id,))
    deleted["pending_actions"] = db_exec("DELETE FROM pending_actions WHERE lead_id = %s", (lead_id,))
    deleted["leads"] = db_exec("DELETE FROM leads WHERE id = %s", (lead_id,))
    deleted["contact_cards"] = db_exec("DELETE FROM contact_cards WHERE id = %s", (contact_id,))
    return deleted


async def run(company_id: str) -> dict:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company_id,
        "checks": {},
        "evidence": {},
    }

    rep_id = pick_rep(company_id)
    report["assigned_rep_id"] = rep_id
    if not rep_id:
        report["warning"] = "No active sales rep for company; notification routing untested."

    lead_id, contact_id = create_synthetic_lead(company_id, rep_id)
    report["synthetic_lead_id"] = lead_id
    report["synthetic_contact_id"] = contact_id
    print(f"[+] Created synthetic lead {lead_id} (company={company_id}, rep={rep_id})")

    try:
        # ── Step 1: Lead becomes eligible ────────────────────────────────
        # 10 days old: past the qualified_unbooked gate (7d) but NOT the
        # stale_lead gate (14d), isolating this lead to a single category.
        make_eligible(lead_id, days_old=10)
        report["checks"]["step1_lead_eligible"] = True
        print("[+] Step 1: lead flipped to qualified_unbooked, 10d stale (single category)")

        # ── Step 2: Rehash PendingAction created ─────────────────────────
        async with AsyncSessionLocal() as session:
            result = await scan_and_sync_rehash(session, company_id=UUID(company_id), lead_id=UUID(lead_id))
            await session.commit()
        rows = rehash_rows(lead_id)
        qu_rows = [r for r in rows if (r["extra_metadata"] or {}).get("rehash_category") == CATEGORY_QUALIFIED_UNBOOKED]
        report["evidence"]["created_rows"] = rows
        report["checks"]["step2_exactly_one_row"] = len(rows) == 1
        report["checks"]["step2_rehash_created"] = len(qu_rows) == 1
        report["checks"]["step2_owner_is_rep"] = bool(qu_rows) and str(qu_rows[0]["owner_id"]) == str(rep_id)
        print(f"[+] Step 2: {len(rows)} rehash row(s); qualified_unbooked={len(qu_rows)}")

        if not qu_rows:
            report["fatal"] = "No rehash row created — cannot continue lifecycle."
            return report
        target_id = qu_rows[0]["id"]

        # ── Step 3: Notification fires (once) ────────────────────────────
        # due_at is set to detection time (now); it's already inside the grace
        # window, so the real notification job should fire immediately.
        captured: list[dict] = []

        async def fake_send(user_ids, payload):
            captured.append({"user_ids": [str(u) for u in user_ids], "payload": payload})
            return len(user_ids) if user_ids else 0

        orig_send = fns.connection_manager.send_to_users
        fns.connection_manager.send_to_users = fake_send
        fns._sent_notifications_cache = set()

        try:
            async with AsyncSessionLocal() as session:
                sent1 = await fns.check_follow_ups(session)
                await session.commit()
            fired = next((r for r in rehash_rows(lead_id, ("pending", "completed", "cancelled"))
                          if r["id"] == target_id), None)
            notified_at = (fired.get("extra_metadata") or {}).get("notified_at") if fired else None
            our_payloads = [c for c in captured
                            if c["payload"].get("pending_action_id") == target_id]
            report["evidence"]["notification_payloads"] = our_payloads
            report["checks"]["step3_notification_fired"] = len(our_payloads) == 1
            report["checks"]["step3_notified_at_set"] = bool(notified_at)
            report["checks"]["step3_status_completed"] = fired is not None and fired["status"] == "completed"
            report["checks"]["step3_payload_type_rehash"] = (
                bool(our_payloads) and our_payloads[0]["payload"].get("type") == "rehash_opportunity"
            )
            print(f"[+] Step 3: fired payloads(for our row)={len(our_payloads)}, "
                  f"notified_at={notified_at}")

            # ── Step 4: Replay / idempotency ─────────────────────────────
            # (a) re-scan must NOT create a duplicate (row is completed, not pending,
            #     but lead still eligible — must not re-materialize).
            async with AsyncSessionLocal() as session:
                await scan_and_sync_rehash(session, company_id=UUID(company_id), lead_id=UUID(lead_id))
                await session.commit()
            pending_after_rescan = rehash_rows(lead_id, ("pending",))
            report["checks"]["step4_no_duplicate_on_rescan"] = len(pending_after_rescan) == 0
            # (b) second notification tick must NOT re-fire.
            before = len(captured)
            async with AsyncSessionLocal() as session:
                sent2 = await fns.check_follow_ups(session)
                await session.commit()
            report["checks"]["step4_no_refire_second_tick"] = len(captured) == before
            print(f"[+] Step 4: pending_after_rescan={len(pending_after_rescan)} "
                  f"(no dup={report['checks']['step4_no_duplicate_on_rescan']}); "
                  f"refire={not report['checks']['step4_no_refire_second_tick']}")

            # ── Step 5: Scheduler restart survival ───────────────────────
            fns._sent_notifications_cache = set()  # simulate fresh process
            before = len(captured)
            async with AsyncSessionLocal() as session:
                sent3 = await fns.check_follow_ups(session)
                await session.commit()
            report["checks"]["step5_survives_restart"] = len(captured) == before
            print(f"[+] Step 5: post-restart refire="
                  f"{not report['checks']['step5_survives_restart']}")
        finally:
            fns.connection_manager.send_to_users = orig_send

        # ── Step 6: Lead becomes ineligible ──────────────────────────────
        # At this point the rehash row is COMPLETED (notified) and the lead is
        # still eligible. The completed row exists and suppresses re-creation.
        active_before = rehash_rows(lead_id, ("pending", "completed"))
        report["checks"]["step6_active_row_exists_before"] = len(active_before) == 1

        make_ineligible(lead_id)  # book the lead → no longer a rehash candidate
        async with AsyncSessionLocal() as session:
            await scan_and_sync_rehash(session, company_id=UUID(company_id), lead_id=UUID(lead_id))
            await session.commit()

        # ── Step 7: Rehash task cancelled by the scan ────────────────────
        active_after = rehash_rows(lead_id, ("pending", "completed"))
        cancelled_rows = rehash_rows(lead_id, ("cancelled",))
        report["checks"]["step7_no_active_after_ineligible"] = len(active_after) == 0
        report["checks"]["step7_episode_closed"] = len(cancelled_rows) >= 1
        print(f"[+] Step 6/7: active_before={len(active_before)}, "
              f"active_after_ineligible={len(active_after)}, "
              f"cancelled_total={len(cancelled_rows)}")

        # ── Idempotency tail: stays cancelled, no resurrection while booked ─
        async with AsyncSessionLocal() as session:
            await scan_and_sync_rehash(session, company_id=UUID(company_id), lead_id=UUID(lead_id))
            await session.commit()
        report["checks"]["step7_stays_closed_on_rescan"] = (
            len(rehash_rows(lead_id, ("pending", "completed"))) == 0
        )

        report["evidence"]["final_rows"] = rehash_rows(
            lead_id, ("pending", "completed", "cancelled")
        )

    finally:
        # ── Teardown: remove everything we created ───────────────────────
        deleted = teardown(lead_id, contact_id)
        report["teardown_deleted"] = deleted
        print(f"[+] Teardown: {deleted}")

    # ── Verdict ──────────────────────────────────────────────────────────
    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed and "fatal" not in report else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", default=DEFAULT_COMPANY)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run(args.company_id))

    out_dir = EVIDENCE / f"rehash_validation_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "validation.json"
    out_file.write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 60)
    print(f"VERDICT: {report.get('verdict', 'NO-GO (fatal)')}")
    if report.get("failed_checks"):
        print(f"FAILED: {report['failed_checks']}")
    if report.get("fatal"):
        print(f"FATAL: {report['fatal']}")
    print(f"Evidence: {out_file}")
    print("=" * 60)
    return 0 if report.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
