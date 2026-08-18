#!/usr/bin/env python3
"""
SMS workflow consolidation validation (staging).

Validates the canonical inbound SMS pipeline:
  inbound SMS -> persist -> forward -> intent classify -> reply draft ->
  callback task (call_me) -> Action Center / Follow-up Guidance
with idempotency and full cleanup.

Usage:
    cd backend
    python dev_utils/sms_workflow_validation.py
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
from sqlalchemy import select, func

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_models_dir = ROOT / "app" / "infrastructure" / "database" / "models"
for _mod in _models_dir.glob("*.py"):
    if not _mod.stem.startswith("_"):
        importlib.import_module(f"app.infrastructure.database.models.{_mod.stem}")

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.infrastructure.database.models.proxy_number import ProxyNumberORM  # noqa: E402
from app.infrastructure.database.models.proxy_session import ProxySessionORM  # noqa: E402
from app.infrastructure.database.models.masked_communication import MaskedCommunicationORM  # noqa: E402
from app.infrastructure.database.models.pending_action import PendingActionORM  # noqa: E402
from app.services.masked_comms_service import MaskedCommsService  # noqa: E402
import app.services.masked_comms_service as masked_mod  # noqa: E402
from app.services.pending_action_service import PendingActionService  # noqa: E402

UTC = timezone.utc
EVIDENCE = Path(__file__).resolve().parent / "evidence"

# Reuse known-good IDs used by other validation scripts.
COMPANY = UUID("d481d226-2791-4652-b080-b6b2c6c4f662")
LEAD = UUID("69e4ece6-5318-4467-93b5-ab36e727b7f1")
REP = UUID("22d04d63-5151-4c18-b33f-0c60fed70f02")


def sync_url():
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


class FakeTwilio:
    def __init__(self):
        self.sent = []

    def is_available(self):
        return True

    def send_sms(self, *, from_number: str, to_number: str, body: str):
        self.sent.append({"from_number": from_number, "to_number": to_number, "body": body})
        return {"status": "queued", "message_sid": f"SM-FAKE-{len(self.sent)}"}


class FakeReplyNotification:
    def __init__(self):
        self.pushes = []

    async def notify_rep_of_inbound_sms(self, session, body, comm_id):
        self.pushes.append({"session_id": str(session.id), "body": body, "comm_id": str(comm_id)})


async def _seed_session():
    """
    Seed (or reuse) a proxy session for the fixed staging lead+rep pair.

    The schema enforces a unique constraint for (lead_id, rep_user_id) when
    status='active'. Previous validation runs may have crashed before cleanup,
    so we must tolerate and reuse existing active rows.
    """
    async with AsyncSessionLocal() as session:
        existing_res = await session.execute(
            select(ProxySessionORM).where(
                ProxySessionORM.lead_id == LEAD,
                ProxySessionORM.rep_user_id == REP,
                ProxySessionORM.status == "active",
            )
        )
        existing = existing_res.scalar_one_or_none()

        if existing:
            # Best-effort pre-clean so this run isn't polluted by prior attempts.
            db_exec(
                "DELETE FROM masked_communications WHERE session_id = %s",
                (str(existing.id),),
            )
            db_exec(
                "DELETE FROM pending_actions "
                "WHERE company_id = %s AND lead_id = %s "
                "  AND action_type = 'call_back' "
                "  AND extra_metadata::text LIKE %s",
                (str(COMPANY), str(LEAD), "%sms_intent_twilio_message_sid%"),
            )

            proxy_phone = None
            proxy_row = await session.execute(
                select(ProxyNumberORM.phone_number).where(
                    ProxyNumberORM.id == existing.proxy_number_id
                )
            )
            proxy_phone = proxy_row.scalar_one_or_none()

            return {
                "proxy_id": existing.proxy_number_id,
                "session_id": existing.id,
                "proxy_phone": proxy_phone,
                "homeowner_phone": existing.homeowner_phone,
                "rep_phone": existing.rep_phone,
            }

        proxy_id = uuid4()
        session_id = uuid4()
        proxy_phone = f"+15559{str(proxy_id.int)[-6:]}"
        homeowner_phone = f"+15558{str(session_id.int)[-6:]}"
        rep_phone = f"+15557{str(session_id.int)[-6:]}"

        session.add(
            ProxyNumberORM(
                id=proxy_id,
                company_id=COMPANY,
                phone_number=proxy_phone,
                twilio_sid=f"PN{str(proxy_id.int)[-10:]}",
                friendly_name="sms_workflow_validation",
                is_active=True,
                is_assigned=True,
            )
        )
        session.add(
            ProxySessionORM(
                id=session_id,
                company_id=COMPANY,
                lead_id=LEAD,
                rep_user_id=REP,
                proxy_number_id=proxy_id,
                homeowner_phone=homeowner_phone,
                rep_phone=rep_phone,
                status="active",
                extra_metadata={"tag": "sms_workflow_validation"},
            )
        )
        await session.commit()

        return {
            "proxy_id": proxy_id,
            "session_id": session_id,
            "proxy_phone": proxy_phone,
            "homeowner_phone": homeowner_phone,
            "rep_phone": rep_phone,
        }


async def _run_inbound(*, proxy_phone: str, homeowner_phone: str, message_sid: str, body: str):
    async with AsyncSessionLocal() as session:
        svc = MaskedCommsService(session)
        fake_twilio = FakeTwilio()
        fake_push = FakeReplyNotification()

        # Monkeypatch service dependencies so validation does not depend on external infra.
        svc.twilio = fake_twilio
        svc.reply_notification = fake_push

        # Force deterministic intent for test repeatability.
        orig_classifier = masked_mod.classify_inbound_reply
        masked_mod.classify_inbound_reply = _fake_classifier  # type: ignore[assignment]
        try:
            await svc.handle_inbound_sms(
                proxy_number=proxy_phone,
                sender=homeowner_phone,
                body=body,
                twilio_message_sid=message_sid,
            )
            await session.commit()
        finally:
            masked_mod.classify_inbound_reply = orig_classifier

        return {"sent": list(fake_twilio.sent), "pushes": list(fake_push.pushes)}


async def _fake_classifier(_: str):
    return ("call_me", 0.98)


async def _fetch_state(message_sid: str):
    async with AsyncSessionLocal() as session:
        comm_res = await session.execute(
            select(MaskedCommunicationORM).where(
                MaskedCommunicationORM.twilio_message_sid == message_sid
            )
        )
        comm_rows = comm_res.scalars().all()

        pa_res = await session.execute(
            select(PendingActionORM).where(
                func.json_extract_path_text(
                    PendingActionORM.extra_metadata, "sms_intent_twilio_message_sid"
                )
                == message_sid
            )
        )
        pa_rows = pa_res.scalars().all()

        ac_svc = PendingActionService(session)
        ac = await ac_svc.get_action_center(company_id=COMPANY, owner_id=REP, limit=200)
        ac_ids = {str(it.id) for g in ac.groups for it in g.items}

        guidance_ok = False
        if pa_rows:
            guidance = await ac_svc.get_follow_up_guidance(pa_rows[0].id)
            guidance_ok = guidance is not None

    return {
        "comm_rows": comm_rows,
        "task_rows": pa_rows,
        "action_center_ids": ac_ids,
        "guidance_ok": guidance_ok,
    }


def _cleanup(seed):
    db_exec(
        "DELETE FROM pending_actions "
        "WHERE extra_metadata::text LIKE %s",
        ("%sms_intent_twilio_message_sid%",),
    )
    db_exec(
        "DELETE FROM masked_communications WHERE session_id = %s",
        (str(seed["session_id"]),),
    )
    db_exec("DELETE FROM proxy_sessions WHERE id = %s", (str(seed["session_id"]),))
    db_exec("DELETE FROM proxy_numbers WHERE id = %s", (str(seed["proxy_id"]),))


async def run():
    report = {"generated_at": datetime.now(UTC).isoformat(), "checks": {}, "evidence": {}}
    seed = await _seed_session()
    message_sid = f"SMVAL{str(uuid4().int)[:12]}"
    body = "Hey, call me today please"

    try:
        first = await _run_inbound(
            proxy_phone=seed["proxy_phone"],
            homeowner_phone=seed["homeowner_phone"],
            message_sid=message_sid,
            body=body,
        )
        state1 = await _fetch_state(message_sid)

        comm = state1["comm_rows"][0] if state1["comm_rows"] else None
        task = state1["task_rows"][0] if state1["task_rows"] else None

        report["evidence"]["first_run"] = {
            "forwarded_sms": first["sent"],
            "push_notifications": first["pushes"],
            "comm_count": len(state1["comm_rows"]),
            "task_count": len(state1["task_rows"]),
            "intent_label": getattr(comm, "intent_label", None),
            "reply_draft": ((getattr(comm, "extra_metadata", None) or {}).get("intent_to_action") or {}).get("reply_draft") if comm else None,
            "task_id": str(task.id) if task else None,
        }

        # Cases 1-7
        report["checks"]["case1_persisted"] = len(state1["comm_rows"]) == 1
        report["checks"]["case2_forwarded_to_rep"] = (
            len(first["sent"]) == 1 and first["sent"][0]["to_number"] == seed["rep_phone"]
        )
        report["checks"]["case3_intent_visible"] = bool(comm and comm.intent_label == "call_me")
        report["checks"]["case4_reply_draft_visible"] = bool(
            comm and ((comm.extra_metadata or {}).get("intent_to_action") or {}).get("reply_draft")
        )
        report["checks"]["case5_callback_task_created"] = bool(
            task and task.action_type == "call_back"
        )
        report["checks"]["case6_in_action_center"] = bool(
            task and str(task.id) in state1["action_center_ids"]
        )
        report["checks"]["case7_in_followup_guidance"] = bool(state1["guidance_ok"])

        # Replay for cases 8-9
        replay = await _run_inbound(
            proxy_phone=seed["proxy_phone"],
            homeowner_phone=seed["homeowner_phone"],
            message_sid=message_sid,
            body=body,
        )
        state2 = await _fetch_state(message_sid)
        report["evidence"]["replay"] = {
            "forwarded_sms": replay["sent"],
            "push_notifications": replay["pushes"],
            "comm_count": len(state2["comm_rows"]),
            "task_count": len(state2["task_rows"]),
        }
        report["checks"]["case8_webhook_replay_idempotent"] = (
            len(replay["sent"]) == 0 and len(replay["pushes"]) == 0
        )
        report["checks"]["case9_no_duplicate_tasks"] = len(state2["task_rows"]) == 1

    finally:
        _cleanup(seed)

    # Case 10 cleanup
    async with AsyncSessionLocal() as session:
        rem_comm = await session.execute(
            select(MaskedCommunicationORM).where(
                MaskedCommunicationORM.twilio_message_sid == message_sid
            )
        )
        rem_tasks = await session.execute(
            select(PendingActionORM).where(
                func.json_extract_path_text(
                    PendingActionORM.extra_metadata, "sms_intent_twilio_message_sid"
                )
                == message_sid
            )
        )
        report["checks"]["case10_cleanup_no_residual_rows"] = (
            rem_comm.scalar_one_or_none() is None
            and rem_tasks.scalar_one_or_none() is None
        )

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = asyncio.run(run())
    out_dir = EVIDENCE / f"sms_workflow_{args.run_id}"
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

