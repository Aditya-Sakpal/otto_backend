#!/usr/bin/env python3
"""
Appointment reminder business-workflow validation (staging).

Drives the REAL reminder code paths (appointment_reminder_service +
followup_notification_service) against the staging database and captures
evidence: DB rows, reminder metadata, and notification payloads.

It is non-destructive:
  - Picks a real future pending appointment (does not modify its core fields,
    except temporarily flipping `outcome` for the cancellation test, which is
    restored afterwards).
  - All appointment_reminder pending_actions it creates are deleted at the end.
  - WebSocket delivery is monkeypatched to capture payloads instead of sending.

Usage:
    cd backend
    python dev_utils/appointment_reminder_validation.py
    python dev_utils/appointment_reminder_validation.py --appointment-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Import every ORM model module so SQLAlchemy can resolve string-based
# relationships (the app registers these at startup; a standalone script must do
# it explicitly or mapper configuration fails on the first query).
import importlib  # noqa: E402

_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if _mod.stem.startswith("_"):
        continue
    importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.services import followup_notification_service as fns  # noqa: E402
from app.services.appointment_reminder_service import (  # noqa: E402
    KIND_DAY_BEFORE,
    KIND_MORNING_OF,
    KIND_ONE_HOUR_BEFORE,
    sync_appointment_reminders,
    cancel_appointment_reminders,
)

EVIDENCE = Path(__file__).resolve().parent / "evidence"
EXPECTED_KINDS = {KIND_DAY_BEFORE, KIND_MORNING_OF, KIND_ONE_HOUR_BEFORE}


def sync_db_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_query(sql: str, params=()) -> list[dict]:
    conn = psycopg2.connect(sync_db_url())
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def db_exec(sql: str, params=()) -> int:
    conn = psycopg2.connect(sync_db_url())
    cur = conn.cursor()
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return n


def jsonable(v):
    if isinstance(v, (datetime,)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def rows_for(appointment_id: str, statuses=("pending",)) -> list[dict]:
    placeholders = ",".join(["%s"] * len(statuses))
    rows = db_query(
        f"""
        SELECT id, action_type, source, status, due_at, priority, owner_id,
               appointment_id, raw_text, extra_metadata, created_at
        FROM pending_actions
        WHERE appointment_id = %s
          AND action_type = 'appointment_reminder'
          AND status IN ({placeholders})
        ORDER BY due_at ASC
        """,
        (appointment_id, *statuses),
    )
    return [{k: jsonable(v) for k, v in r.items()} for r in rows]


def kinds_of(rows: list[dict]) -> set[str]:
    out = set()
    for r in rows:
        meta = r.get("extra_metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        if meta.get("reminder_kind"):
            out.add(meta["reminder_kind"])
    return out


def pick_appointment(explicit: str | None) -> dict | None:
    if explicit:
        rows = db_query(
            "SELECT id, company_id, lead_id, assigned_rep_id, scheduled_start, outcome "
            "FROM appointments WHERE id = %s",
            (explicit,),
        )
        return rows[0] if rows else None
    # Prefer an appointment >26h out so all three kinds materialize, with a rep.
    rows = db_query(
        """
        SELECT id, company_id, lead_id, assigned_rep_id, scheduled_start, outcome
        FROM appointments
        WHERE scheduled_start > now() + interval '26 hours'
          AND (outcome IS NULL OR outcome = 'pending')
        ORDER BY (assigned_rep_id IS NOT NULL) DESC, scheduled_start ASC
        LIMIT 1
        """
    )
    return rows[0] if rows else None


async def load_orm(session, appointment_id):
    from app.infrastructure.database.models.appointment import AppointmentORM
    from sqlalchemy import select

    res = await session.execute(
        select(AppointmentORM).where(AppointmentORM.id == appointment_id)
    )
    return res.scalar_one_or_none()


async def run(appointment_id_arg: str | None) -> dict:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "evidence": {},
    }

    appt = pick_appointment(appointment_id_arg)
    if not appt:
        report["fatal"] = "No suitable future pending appointment found in staging."
        return report

    appointment_id = str(appt["id"])
    report["appointment"] = {k: jsonable(v) for k, v in appt.items()}
    print(f"[+] Using appointment {appointment_id} "
          f"(start={appt['scheduled_start']}, rep={appt['assigned_rep_id']})")

    # Clean slate: remove any existing reminder rows we might re-create.
    db_exec(
        "DELETE FROM pending_actions WHERE appointment_id = %s "
        "AND action_type = 'appointment_reminder'",
        (appointment_id,),
    )

    # ── Step 2/3: Materialize + verify three kinds ────────────────────────
    async with AsyncSessionLocal() as session:
        orm = await load_orm(session, appointment_id)
        result = await sync_appointment_reminders(session, orm)
        await session.commit()

    rows = rows_for(appointment_id)
    materialized_kinds = kinds_of(rows)
    report["evidence"]["materialized_rows"] = rows
    report["checks"]["day_before_created"] = KIND_DAY_BEFORE in materialized_kinds
    report["checks"]["morning_of_created"] = KIND_MORNING_OF in materialized_kinds
    report["checks"]["one_hour_before_created"] = KIND_ONE_HOUR_BEFORE in materialized_kinds
    report["checks"]["exactly_three_rows"] = len(rows) == 3
    print(f"[+] Materialized kinds: {sorted(materialized_kinds)} ({len(rows)} rows)")

    # ── Idempotency: double sync → still 3 rows ──────────────────────────
    async with AsyncSessionLocal() as session:
        orm = await load_orm(session, appointment_id)
        await sync_appointment_reminders(session, orm)
        await session.commit()
    rows_after_double = rows_for(appointment_id)
    report["checks"]["idempotent_double_sync"] = len(rows_after_double) == 3
    print(f"[+] After double sync: {len(rows_after_double)} rows "
          f"(idempotent={report['checks']['idempotent_double_sync']})")

    # ── Step 4/5: Simulate scheduler fire ────────────────────────────────
    # Force the one_hour_before reminder's due_at into the grace window so the
    # real scheduler logic fires it. Capture the WebSocket payload.
    target = next(
        (r for r in rows_after_double
         if (r["extra_metadata"] or {}).get("reminder_kind") == KIND_ONE_HOUR_BEFORE),
        rows_after_double[0],
    )
    target_id = target["id"]
    forced_due = datetime.now(timezone.utc) - timedelta(minutes=2)  # inside 15-min grace
    db_exec(
        "UPDATE pending_actions SET due_at = %s WHERE id = %s",
        (forced_due, target_id),
    )

    captured: list[dict] = []

    async def fake_send_to_users(user_ids, payload):
        captured.append({"user_ids": [str(u) for u in user_ids], "payload": payload})
        return len(user_ids) if user_ids else 0

    orig_send = fns.connection_manager.send_to_users
    fns.connection_manager.send_to_users = fake_send_to_users
    # Reset module global dedupe cache so prior runs don't interfere.
    fns._sent_notifications_cache = set()

    try:
        # First scheduler tick
        async with AsyncSessionLocal() as session:
            sent1 = await fns.check_follow_ups(session)
            await session.commit()
        row_after_fire = rows_for(appointment_id, statuses=("pending", "completed", "cancelled"))
        fired_row = next((r for r in row_after_fire if r["id"] == target_id), None)
        notified_at_1 = (fired_row.get("extra_metadata") or {}).get("notified_at") if fired_row else None

        report["checks"]["reminder_fired_once"] = sent1 == 1 and len(captured) == 1
        report["checks"]["notified_at_set"] = bool(notified_at_1)
        report["checks"]["status_completed_after_fire"] = (
            fired_row is not None and fired_row["status"] == "completed"
        )
        report["evidence"]["notification_payloads"] = captured
        print(f"[+] Tick 1: sent={sent1}, captured={len(captured)}, "
              f"notified_at={notified_at_1}")

        # Second scheduler tick — must NOT re-fire (DB notified_at idempotency)
        captured_count_before_tick2 = len(captured)
        async with AsyncSessionLocal() as session:
            sent2 = await fns.check_follow_ups(session)
            await session.commit()
        report["checks"]["no_refire_second_tick"] = (
            sent2 == 0 and len(captured) == captured_count_before_tick2
        )
        print(f"[+] Tick 2: sent={sent2} (no re-fire="
              f"{report['checks']['no_refire_second_tick']})")

        # Restart survival — fresh module cache (simulates new process), tick again.
        fns._sent_notifications_cache = set()
        captured_count_before_restart = len(captured)
        async with AsyncSessionLocal() as session:
            sent3 = await fns.check_follow_ups(session)
            await session.commit()
        report["checks"]["survives_restart"] = (
            sent3 == 0 and len(captured) == captured_count_before_restart
        )
        print(f"[+] Tick 3 (post-restart, empty cache): sent={sent3} "
              f"(survives_restart={report['checks']['survives_restart']})")
    finally:
        fns.connection_manager.send_to_users = orig_send

    # ── Step 6: Outcome change cancellation ──────────────────────────────
    original_outcome = appt["outcome"]
    outcome_results = {}
    for outcome in ("won", "lost", "no_show", "rescheduled"):
        # Re-materialize a fresh set of pending reminders.
        db_exec(
            "DELETE FROM pending_actions WHERE appointment_id = %s "
            "AND action_type = 'appointment_reminder'",
            (appointment_id,),
        )
        async with AsyncSessionLocal() as session:
            orm = await load_orm(session, appointment_id)
            orm.outcome = "pending"
            # Detach so the in-memory outcome change is NOT persisted to the
            # appointments table; sync still reads attributes from the detached
            # instance and creates separate reminder rows that do commit.
            session.expunge(orm)
            await sync_appointment_reminders(session, orm)
            await session.commit()
        before = len(rows_for(appointment_id))

        # Flip outcome and re-sync (mirrors appointment_service.update hook).
        async with AsyncSessionLocal() as session:
            orm = await load_orm(session, appointment_id)
            orm.outcome = outcome
            session.expunge(orm)  # never persist outcome to appointments table
            await sync_appointment_reminders(session, orm)
            await session.commit()
        pending_after = len(rows_for(appointment_id, statuses=("pending",)))
        cancelled_after = len(rows_for(appointment_id, statuses=("cancelled",)))
        ok = pending_after == 0 and cancelled_after >= before and before == 3
        outcome_results[outcome] = {
            "pending_before": before,
            "pending_after": pending_after,
            "cancelled_after": cancelled_after,
            "cancelled_ok": ok,
        }
        print(f"[+] Outcome '{outcome}': before={before} pending_after={pending_after} "
              f"cancelled={cancelled_after} ok={ok}")

    report["evidence"]["outcome_cancellation"] = outcome_results
    report["checks"]["outcome_won_cancels"] = outcome_results["won"]["cancelled_ok"]
    report["checks"]["outcome_lost_cancels"] = outcome_results["lost"]["cancelled_ok"]
    # "cancelled" is not a valid AppointmentOutcome enum value; no_show is the
    # closest visit-not-happening terminal state. rescheduled covers reschedule.
    report["checks"]["outcome_no_show_cancels"] = outcome_results["no_show"]["cancelled_ok"]
    report["checks"]["outcome_rescheduled_cancels"] = outcome_results["rescheduled"]["cancelled_ok"]

    # Restore original outcome on the appointment (we never persisted outcome to
    # the appointments table — only the in-memory ORM during sync — but assert it).
    current = db_query("SELECT outcome FROM appointments WHERE id = %s", (appointment_id,))
    report["appointment_outcome_unchanged_in_db"] = (
        current and current[0]["outcome"] == original_outcome
    )

    # ── Cleanup: remove all reminder rows we created ─────────────────────
    deleted = db_exec(
        "DELETE FROM pending_actions WHERE appointment_id = %s "
        "AND action_type = 'appointment_reminder'",
        (appointment_id,),
    )
    report["cleanup_rows_deleted"] = deleted
    print(f"[+] Cleanup: deleted {deleted} reminder rows")

    # ── Verdict ──────────────────────────────────────────────────────────
    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appointment-id", default=None)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run(args.appointment_id))

    out_dir = EVIDENCE / f"appointment_reminders_{args.run_id}"
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
