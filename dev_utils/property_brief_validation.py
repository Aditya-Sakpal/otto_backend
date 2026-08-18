#!/usr/bin/env python3
"""
CSR→Rep property_brief validation (Option A, staging).

Drives the REAL AppointmentService.get_appointment_context against the staging DB
with synthetic appointment + lead + CSR calls + call_analyses (real
property_details / customer_details blobs), and asserts the consolidated
property_brief. Non-destructive: all synthetic rows hard-deleted at the end.

Mirrors recording_reconciliation_validation.py / rehash_validation.py.

Proves:
  Case 1: full property_details blob  → fully populated property_brief
  Case 2: partial blob                → partial property_brief
  Case 3: no property_details         → graceful empty brief (has_data=False)
  Case 4: customer_details present    → decision_makers surfaced
  Case 5: multiple calls              → latest CSR call selected

Usage:
    cd backend
    python dev_utils/property_brief_validation.py
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
from app.services.appointment_service import AppointmentService  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"
CONTACT = "a6cd6682-6eba-49a4-9f08-2ab7d10658d3"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
UTC = timezone.utc

FULL_BLOB = {
    "roof_type": "tile", "roof_age_years": 14, "stories": "two",
    "property_size": "2400 sqft", "hoa_status": "yes", "hoa_name": "Sunridge",
    "gated_community": True, "gate_access": "Gate code 4417", "pets": "large dog",
    "current_issues": ["Active leak over garage after monsoon"],
}


def sync_url():
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_exec(sql, params=()):
    c = psycopg2.connect(sync_url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


async def _seed_call(session, when, call_type, property_details=None, customer_details=None,
                     service_requested=None, qualification_status=None, booking_status=None,
                     summary=None, tag="brief_smoke"):
    call_id = uuid4()
    session.add(CallORM(
        id=call_id, company_id=UUID(COMPANY), lead_id=UUID(LEAD), contact_card_id=UUID(CONTACT),
        phone_number="+15551230000", call_type=call_type, missed_call=False, created_at=when,
        extra_metadata={"tag": tag},
    ))
    session.add(CallAnalysisORM(
        id=uuid4(), call_id=call_id, company_id=UUID(COMPANY), status="completed",
        summary=summary, property_details=property_details, customer_details=customer_details,
        service_requested=service_requested, qualification_status=qualification_status,
        booking_status=booking_status,
    ))
    return call_id


async def _seed_appointment(session):
    appt_id = uuid4()
    session.add(AppointmentORM(
        id=appt_id, company_id=UUID(COMPANY), lead_id=UUID(LEAD), contact_card_id=UUID(CONTACT),
        scheduled_start=datetime.now(UTC) + timedelta(days=1), outcome="pending",
    ))
    return appt_id


async def _get_brief(appt_id):
    async with AsyncSessionLocal() as session:
        svc = AppointmentService(session)
        ctx = await svc.get_appointment_context(appt_id)
        return ctx.property_brief if ctx else None


def _cleanup():
    # delete synthetic analyses+calls (by tag) and any synthetic appointments for the lead
    db_exec("DELETE FROM call_analyses WHERE call_id IN (SELECT id FROM calls WHERE extra_metadata->>'tag'='brief_smoke')")
    db_exec("DELETE FROM calls WHERE extra_metadata->>'tag'='brief_smoke'")


async def _scenario(seed_fn) -> dict:
    """Create an appointment + calls via seed_fn, fetch brief, then delete EVERYTHING
    this scenario created.

    Each scenario must be fully isolated: get_appointment_context loads ALL calls
    for the (shared) lead, so a scenario's synthetic calls must be removed before
    the next scenario runs, or they leak across cases.
    """
    async with AsyncSessionLocal() as session:
        appt_id = await _seed_appointment(session)
        await seed_fn(session)
        await session.commit()
    try:
        brief = await _get_brief(appt_id)
        return brief.model_dump() if brief else None
    finally:
        db_exec("DELETE FROM appointments WHERE id = %s", (str(appt_id),))
        _cleanup()  # remove this scenario's synthetic calls/analyses before the next


async def run() -> dict:
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    now = datetime.now(UTC)

    try:
        # Case 1 — full blob
        async def s1(session):
            await _seed_call(session, now - timedelta(days=2), "csr_call",
                             property_details=FULL_BLOB,
                             customer_details={"decision_makers": ["homeowner", "spouse"]},
                             service_requested="Roof repair", qualification_status="qualified",
                             booking_status="booked", summary="Wants quote by Friday")
        b1 = await _scenario(s1)
        report["evidence"]["case1"] = b1
        report["checks"]["case1_full_populated"] = bool(b1) and (
            b1["has_data"] and b1["roof_type"] == "tile" and b1["roof_age_years"] == 14
            and b1["property_size"] == "2400 sqft" and b1["stories"] == "two"
            and b1["hoa_name"] == "Sunridge" and b1["gate_access"] == "Gate code 4417"
            and b1["service_requested"] == "Roof repair" and b1["booking_status"] == "booked"
            and b1["current_issues"] == ["Active leak over garage after monsoon"]
        )

        # Case 2 — partial blob (+ 'unknown' sentinel)
        async def s2(session):
            await _seed_call(session, now - timedelta(days=2), "csr_call",
                             property_details={"roof_type": "shingle", "stories": "unknown"},
                             service_requested="Roof inspection")
        b2 = await _scenario(s2)
        report["evidence"]["case2"] = b2
        report["checks"]["case2_partial"] = bool(b2) and (
            b2["has_data"] and b2["roof_type"] == "shingle" and b2["stories"] is None
            and b2["property_size"] is None and b2["service_requested"] == "Roof inspection"
        )

        # Case 3 — no property_details / no customer_details
        async def s3(session):
            await _seed_call(session, now - timedelta(days=2), "csr_call",
                             property_details=None, customer_details=None, summary="Hi")
        b3 = await _scenario(s3)
        report["evidence"]["case3"] = b3
        report["checks"]["case3_empty_graceful"] = bool(b3) and b3["has_data"] is False

        # Case 4 — customer_details only → decision makers surfaced
        async def s4(session):
            await _seed_call(session, now - timedelta(days=2), "csr_call",
                             property_details=None,
                             customer_details={"decision_makers": ["homeowner", "HOA board"]})
        b4 = await _scenario(s4)
        report["evidence"]["case4"] = b4
        report["checks"]["case4_decision_makers"] = bool(b4) and (
            b4["has_data"] and b4["decision_makers"] == ["homeowner", "HOA board"]
        )

        # Case 5 — multiple calls → latest CSR selected
        async def s5(session):
            await _seed_call(session, now - timedelta(days=5), "csr_call",
                             property_details={"roof_type": "shingle"})  # older
            await _seed_call(session, now - timedelta(days=1), "csr_call",
                             property_details={"roof_type": "metal"})    # newer CSR (winner)
            await _seed_call(session, now, "sales_call",
                             property_details={"roof_type": "flat"})     # newest but sales
        b5 = await _scenario(s5)
        report["evidence"]["case5"] = b5
        report["checks"]["case5_latest_csr"] = bool(b5) and b5["roof_type"] == "metal"

    finally:
        _cleanup()

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())

    out_dir = EVIDENCE / f"property_brief_{args.run_id}"
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
