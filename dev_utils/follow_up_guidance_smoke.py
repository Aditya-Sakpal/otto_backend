#!/usr/bin/env python3
"""Non-destructive smoke test for follow-up guidance resolver against staging.

Seeds a call + call_analysis (with raw_analysis objections) + a follow_up_otto rep
nudge + a linked pending_action, calls the real
PendingActionService.get_follow_up_guidance, asserts resolver priority and
raw_analysis parsing, and deletes everything it created.
"""
from __future__ import annotations

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
from app.services.pending_action_service import PendingActionService  # noqa: E402
from app.infrastructure.database.models.call import CallORM  # noqa: E402
from app.infrastructure.database.models.analysis import CallAnalysisORM  # noqa: E402
from app.infrastructure.database.models.pending_action import PendingActionORM  # noqa: E402
from app.infrastructure.database.models.follow_up_otto import FollowUpOttoORM  # noqa: E402

COMPANY = "d481d226-2791-4652-b080-b6b2c6c4f662"
OWNER = "22d04d63-5151-4c18-b33f-0c60fed70f02"
# A real lead in COMPANY — follow_up_otto.lead_id is NOT NULL. We only reference
# it; the lead row itself is never modified or deleted.
LEAD = "69e4ece6-5318-4467-93b5-ab36e727b7f1"


def url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def ex(sql, params=()):
    c = psycopg2.connect(url()); cur = c.cursor()
    cur.execute(sql, params); n = cur.rowcount; c.commit(); cur.close(); c.close()
    return n


async def scenario(with_otto: bool) -> dict:
    call_id = str(uuid4())
    analysis_id = str(uuid4())
    pa_id = str(uuid4())
    otto_id = str(uuid4())
    tag = "guidance_smoke"

    raw_analysis = {
        "objections": {
            "objections": [
                {"objection_text": "Too expensive", "response_suggestions": ["Offer financing", "Show ROI"]},
            ]
        }
    }
    now = datetime.now(timezone.utc)
    try:
        # Seed via ORM so NOT NULL array/default columns are populated correctly.
        async with AsyncSessionLocal() as session:
            session.add(CallORM(
                id=UUID(call_id), company_id=UUID(COMPANY), phone_number="+15551230000",
                call_type="sales_call", missed_call=False, extra_metadata={"tag": tag},
            ))
            session.add(CallAnalysisORM(
                id=UUID(analysis_id), call_id=UUID(call_id), company_id=UUID(COMPANY),
                status="completed", summary="Customer interested in roof repair",
                key_points=["Wants quote by Friday"],
                next_steps=["Send written estimate", "Call to confirm"],
                follow_up_reason="Customer asked for a quote", service_requested="Roof repair",
                customer_name="Jane Doe", objections=["Too expensive"],
                objection_texts=["Too expensive"], raw_analysis=raw_analysis,
            ))
            session.add(PendingActionORM(
                id=UUID(pa_id), company_id=UUID(COMPANY), owner_id=UUID(OWNER),
                call_id=UUID(call_id), action_type="follow_up", status="pending",
                source=tag, raw_text="Follow up on roof repair quote",
            ))
            if with_otto:
                session.add(FollowUpOttoORM(
                    id=UUID(otto_id), lead_id=UUID(LEAD), company_id=UUID(COMPANY),
                    message_content="rep nudge blob", action_type="nudge_sales_rep",
                    opening_line="Hi Jane, following up on your roof repair",
                    objections=[{"objection": "Too expensive", "suggested_response": "Mention 0% financing"}],
                    key_talking_points=["Reference Friday deadline", "Offer free inspection"],
                    close_approach="Ask for the appointment directly",
                    pending_action_id=UUID(pa_id), scheduled_at=now, status="proposed",
                    queue_type="qualified_unbooked", attempt_number=1,
                ))
            await session.commit()

        async with AsyncSessionLocal() as session:
            svc = PendingActionService(session)
            g = await svc.get_follow_up_guidance(UUID(pa_id), include_sms=True)
        return {"guidance": g, "with_otto": with_otto}
    finally:
        ex("DELETE FROM follow_up_otto WHERE id = %s", (otto_id,))
        ex("DELETE FROM pending_actions WHERE id = %s", (pa_id,))
        ex("DELETE FROM call_analyses WHERE id = %s", (analysis_id,))
        ex("DELETE FROM calls WHERE id = %s", (call_id,))


async def main() -> int:
    checks = {}

    # Scenario A: follow_up_otto present → its nudge wins for say_next copy.
    a = await scenario(with_otto=True)
    g = a["guidance"]
    checks["A_sources_include_otto"] = "follow_up_otto" in g.sources
    checks["A_opening_line_from_otto"] = g.say_next.opening_line == "Hi Jane, following up on your roof repair"
    checks["A_talking_points_from_otto"] = "Reference Friday deadline" in g.say_next.talking_points
    checks["A_objection_from_otto"] = (
        bool(g.say_next.objection_responses)
        and g.say_next.objection_responses[0].suggested_response == "Mention 0% financing"
    )
    checks["A_next_steps_from_analysis"] = "Send written estimate" in g.say_next.next_steps
    checks["A_context_customer"] = g.context.customer_name == "Jane Doe"
    checks["A_context_service"] = g.context.service_requested == "Roof repair"

    # Scenario B: no otto → analysis + raw_analysis objections drive say_next.
    b = await scenario(with_otto=False)
    g = b["guidance"]
    checks["B_no_otto_source"] = "follow_up_otto" not in g.sources
    checks["B_raw_analysis_parsed"] = "raw_analysis" in g.sources
    checks["B_objection_suggestion_recovered"] = (
        bool(g.say_next.objection_responses)
        and g.say_next.objection_responses[0].suggested_response == "Offer financing"
    )
    checks["B_follow_up_reason"] = g.say_next.follow_up_reason == "Customer asked for a quote"
    checks["B_do_next_title"] = g.do_next.title == "Follow up on roof repair quote"

    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    ok = all(checks.values())
    print("\nVERDICT:", "GO" if ok else "NO-GO")

    # Final cleanup safety net.
    left = ex("DELETE FROM pending_actions WHERE source = 'guidance_smoke'")
    print(f"[cleanup] residual pending_actions removed: {left}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
