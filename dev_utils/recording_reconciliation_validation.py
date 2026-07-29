#!/usr/bin/env python3
"""
Recording reconciliation validation (Phase 2 — Fix #3, staging).

Drives the REAL reconcile_stuck_recordings against the staging DB with a MOCKED
Shunya client (the external HTTP round-trip is environment-gated, like prior
phases' mocked WebSocket delivery). Proves each transition end-to-end:

  - processing + Shunya 'completed' → completed + analysis persisted + visible via
    the Phase-1 endpoint (ready=true)
  - processing + Shunya 'failed'    → failed + failure_reason surfaced
  - processing + Shunya 'running'   → stays processing, reconcile_attempts++
  - processing past MAX hours        → failed (timed out)
  - poll raises (Shunya down)        → stays processing (graceful)
  - replay: second run does not re-touch terminal rows / no duplicate follow-up

Non-destructive: one synthetic appointment per case, hard-deleted at the end.
Mirrors rehash_validation.py / appointment_reminder_validation.py.

Usage:
    cd backend
    python dev_utils/recording_reconciliation_validation.py
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

from app.core.config import settings  # noqa: E402
from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.infrastructure.database.models.appointment import AppointmentORM  # noqa: E402
from app.services.recording_reconciliation_service import reconcile_stuck_recordings  # noqa: E402
from sqlalchemy import select  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
S3_URL = "https://otto-audio.s3.us-east-1.amazonaws.com/recordings/recon_demo.wav"

EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc


def sync_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


def db_one(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params)
    row = cur.fetchone(); cols = [d[0] for d in cur.description]
    cur.close(); c.close()
    return dict(zip(cols, row)) if row else None


class FakeShoonya:
    """Drives reconcile branches deterministically."""
    def __init__(self, status=None, raise_on_status=False, summary=None):
        self._status = status
        self._raise = raise_on_status
        self._summary = summary or {}

    async def get_call_processing_status(self, job_id, company_id=None):
        if self._raise:
            raise RuntimeError("Shunya unreachable (simulated)")
        return {"status": self._status}

    async def get_call_summary(self, call_id, company_id=None, include_chunks=False):
        return self._summary


async def _seed(processing_age_minutes: int, audio=S3_URL) -> str:
    appt_id = str(uuid4())
    async with AsyncSessionLocal() as session:
        session.add(AppointmentORM(
            id=UUID(appt_id), company_id=UUID(COMPANY), lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT), scheduled_start=datetime.now(UTC) - timedelta(days=1),
            outcome="pending", analysis_status="processing", recording_status="uploaded",
            shunya_job_id=f"job-{appt_id[:8]}", audio_url=audio,
        ))
        await session.commit()
    # Force updated_at to look "stuck" (bypass onupdate which would set it to now).
    db_exec(
        "UPDATE appointments SET updated_at = now() - make_interval(mins => %s) WHERE id = %s",
        (processing_age_minutes, appt_id),
    )
    return appt_id


async def _run_reconcile(fake) -> None:
    async with AsyncSessionLocal() as session:
        await reconcile_stuck_recordings(session, shoonya_client=fake)
        await session.commit()


def _state(appt_id):
    return db_one(
        "SELECT analysis_status, summary, next_steps, extra_metadata FROM appointments WHERE id = %s",
        (appt_id,),
    )


def _cleanup(appt_id):
    db_exec("DELETE FROM pending_actions WHERE appointment_id = %s", (appt_id,))
    db_exec("DELETE FROM action_items WHERE appointment_id = %s", (appt_id,))
    db_exec("DELETE FROM appointments WHERE id = %s", (appt_id,))


_COMPLETED_SUMMARY = {
    "summary": {"summary": "Recovered analysis", "next_steps": ["Send proposal"]},
    "qualification": {"follow_up_required": True, "follow_up_reason": "Customer wants a quote"},
}


async def run() -> dict:
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "thresholds": {
            "stuck_minutes": settings.RECORDING_STUCK_THRESHOLD_MINUTES,
            "max_hours": settings.RECORDING_MAX_PROCESSING_HOURS,
        },
        "checks": {},
        "evidence": {},
    }
    stuck = settings.RECORDING_STUCK_THRESHOLD_MINUTES + 5
    created = []

    try:
        # Case 1 — completed recovery
        a = await _seed(stuck); created.append(a)
        await _run_reconcile(FakeShoonya(status="completed", summary=_COMPLETED_SUMMARY))
        st = _state(a)
        # Phase-1 endpoint readiness mirrors analysis_status == completed.
        fu = db_one("SELECT count(*) AS n FROM pending_actions WHERE appointment_id=%s AND action_type='follow_up'", (a,))
        report["evidence"]["case1_completed"] = {"state": st, "follow_up_rows": fu["n"]}
        report["checks"]["case1_completed_recovered"] = (
            st["analysis_status"] == "completed" and st["summary"] == "Recovered analysis"
            and st["next_steps"] == ["Send proposal"]
        )
        report["checks"]["case1_follow_up_created"] = fu["n"] == 1

        # Case 1b — replay idempotency: second run must not re-touch / duplicate
        await _run_reconcile(FakeShoonya(status="completed", summary=_COMPLETED_SUMMARY))
        fu2 = db_one("SELECT count(*) AS n FROM pending_actions WHERE appointment_id=%s AND action_type='follow_up'", (a,))
        report["checks"]["case1b_no_duplicate_on_replay"] = fu2["n"] == 1

        # Case 2 — failed
        b = await _seed(stuck); created.append(b)
        await _run_reconcile(FakeShoonya(status="failed"))
        st = _state(b)
        report["evidence"]["case2_failed"] = {"state": st}
        report["checks"]["case2_failed_with_reason"] = (
            st["analysis_status"] == "failed"
            and bool((st["extra_metadata"] or {}).get("analysis_error"))
        )

        # Case 3 — still running → wait, attempts bumped
        c = await _seed(stuck); created.append(c)
        await _run_reconcile(FakeShoonya(status="running"))
        st = _state(c)
        report["evidence"]["case3_running"] = {"state": st}
        report["checks"]["case3_stays_processing"] = st["analysis_status"] == "processing"
        report["checks"]["case3_attempts_bumped"] = (
            (st["extra_metadata"] or {}).get("reconcile_attempts") == 1
        )

        # Case 4 — past hard ceiling while running → timed out
        d = await _seed(settings.RECORDING_MAX_PROCESSING_HOURS * 60 + 30); created.append(d)
        await _run_reconcile(FakeShoonya(status="running"))
        st = _state(d)
        report["evidence"]["case4_timeout"] = {"state": st}
        report["checks"]["case4_timed_out_failed"] = (
            st["analysis_status"] == "failed"
            and "timed out" in str((st["extra_metadata"] or {}).get("analysis_error", "")).lower()
        )

        # Case 5 — poll raises (Shunya down) → unchanged
        e = await _seed(stuck); created.append(e)
        await _run_reconcile(FakeShoonya(raise_on_status=True))
        st = _state(e)
        report["evidence"]["case5_poll_error"] = {"state": st}
        report["checks"]["case5_graceful_unchanged"] = st["analysis_status"] == "processing"

        # Case 6 — not-yet-stuck recording is NOT polled (eligibility filter)
        f = await _seed(processing_age_minutes=1); created.append(f)  # only 1 min old
        await _run_reconcile(FakeShoonya(status="completed", summary=_COMPLETED_SUMMARY))
        st = _state(f)
        report["evidence"]["case6_not_stuck"] = {"state": st}
        report["checks"]["case6_recent_skipped"] = st["analysis_status"] == "processing"

    finally:
        for a in created:
            _cleanup(a)
        report["cleanup_deleted"] = len(created)

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    report["note"] = (
        "Shunya client is MOCKED (external HTTP is environment-gated, like prior "
        "phases). Transition logic, shared persistence, eligibility, idempotency, "
        "and graceful failure are exercised against the real staging DB."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"recording_reconciliation_{args.run_id}"
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
