#!/usr/bin/env python3
"""
ai_briefing validation (appointment-context, staging).

Drives the REAL AppointmentService.get_appointment_context against the staging DB
with synthetic appointment + lead + calls + analyses + pending_actions and
asserts that:

  Case 1 (local data present, Ask Otto disabled) → ai_briefing is non-null
  Case 2 (no local data)                         → ai_briefing is null

Non-destructive: all synthetic rows are hard-deleted at the end.

Mirrors property_brief_validation.py / recording_reconciliation_validation.py /
post_meeting_materialization_validation.py.

Usage:
    cd backend
    python dev_utils/ai_briefing_validation.py
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
from app.infrastructure.database.models.appointment import AppointmentORM  # noqa: E402
from app.infrastructure.database.models.call import CallORM  # noqa: E402
from app.infrastructure.database.models.analysis import CallAnalysisORM  # noqa: E402
from app.infrastructure.database.models.pending_action import PendingActionORM  # noqa: E402
from app.services.appointment_service import AppointmentService  # noqa: E402

UTC = timezone.utc

# Reuse the same synthetic tenant/lead/contact used by other dev_utils scripts
COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
EVIDENCE = Path(__file__).resolve().parent / "evidence"


def sync_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url())
    cur = c.cursor()
    cur.execute(sql, params)
    n = cur.rowcount
    c.commit()
    cur.close()
    c.close()
    return n


async def _seed_scenario_with_data(session) -> UUID:
    """Create an appointment + one analysed call + one pending_action."""
    appt_id = uuid4()
    call_id = uuid4()

    # Appointment scheduled for tomorrow
    session.add(
        AppointmentORM(
            id=appt_id,
            company_id=UUID(COMPANY),
            lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT),
            scheduled_start=datetime.now(UTC) + timedelta(days=1),
            outcome="pending",
        )
    )

    # CSR call with analysis
    session.add(
        CallORM(
            id=call_id,
            company_id=UUID(COMPANY),
            lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT),
            phone_number="+15551230000",
            call_type="csr_call",
            missed_call=False,
            created_at=datetime.now(UTC) - timedelta(days=1),
            extra_metadata={"tag": "ai_brief_smoke"},
        )
    )
    session.add(
        CallAnalysisORM(
            id=uuid4(),
            call_id=call_id,
            company_id=UUID(COMPANY),
            status="completed",
            summary="Customer wants a roof inspection and written proposal.",
            property_details={"service_requested": "Roof inspection"},
            objection_texts=["Worried about price"],
            objections=["service_fee_concerns"],
        )
    )

    # Pending action for the lead
    session.add(
        PendingActionORM(
            id=uuid4(),
            company_id=UUID(COMPANY),
            lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT),
            appointment_id=appt_id,
            action_type="follow_up_call",
            status="pending",
            raw_text="Call homeowner to confirm Friday timeslot",
            source="manual_test",
        )
    )
    return appt_id


async def _seed_scenario_empty(session) -> UUID:
    """Create an appointment with no calls/analyses/pending_actions."""
    appt_id = uuid4()
    session.add(
        AppointmentORM(
            id=appt_id,
            company_id=UUID(COMPANY),
            lead_id=UUID(LEAD),
            contact_card_id=UUID(CONTACT),
            scheduled_start=datetime.now(UTC) + timedelta(days=1),
            outcome="pending",
        )
    )
    return appt_id


async def _get_ai_briefing(appt_id: UUID):
    async with AsyncSessionLocal() as session:
        svc = AppointmentService(session)

        # Force Ask Otto path to be treated as unavailable so we exercise only the
        # deterministic fallback in this validation.
        async def _fake_generate(*args, **kwargs):
            return None

        orig = svc._generate_ai_briefing
        svc._generate_ai_briefing = _fake_generate  # type: ignore[assignment]
        try:
            ctx = await svc.get_appointment_context(appt_id)
        finally:
            svc._generate_ai_briefing = orig  # restore

        return ctx.ai_briefing if ctx else None


def _cleanup():
    # delete synthetic calls/analyses/pending_actions tagged by this script,
    # plus any appointments we created for this lead with our tag.
    db_exec(
        "DELETE FROM call_analyses WHERE call_id IN (SELECT id FROM calls WHERE extra_metadata->>'tag'='ai_brief_smoke')"
    )
    db_exec("DELETE FROM calls WHERE extra_metadata->>'tag'='ai_brief_smoke'")
    # Appointments are deleted case-by-case in _scenario to avoid touching real data.


async def _scenario(seed_fn) -> dict:
    """Seed scenario, fetch ai_briefing via real service, then delete rows."""
    async with AsyncSessionLocal() as session:
        appt_id = await seed_fn(session)
        await session.commit()
    try:
        briefing = await _get_ai_briefing(appt_id)
        return briefing.model_dump() if briefing else None
    finally:
        db_exec("DELETE FROM appointments WHERE id = %s", (str(appt_id),))
        _cleanup()


async def run() -> dict:
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": {},
        "evidence": {},
    }

    try:
        # Case 1 — local data present → fallback briefing non-null
        b1 = await _scenario(_seed_scenario_with_data)
        report["evidence"]["case1"] = b1
        report["checks"]["case1_non_null_with_data"] = bool(b1) and bool(
            (b1 or {}).get("briefing_text")
        )

        # Case 2 — no local data → ai_briefing remains null
        b2 = await _scenario(_seed_scenario_empty)
        report["evidence"]["case2"] = b2
        report["checks"]["case2_null_without_data"] = b2 is None
    finally:
        _cleanup()

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"ai_briefing_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(
        json.dumps(report, indent=2, default=str)
    )

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

