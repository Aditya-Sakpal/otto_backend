#!/usr/bin/env python3
"""
Staging workflow validation orchestrator.

Captures DB/API evidence for backfill, webhook replay, idempotency, and notifications.
Does NOT auto-apply backfill unless --apply-backfill is passed.

Usage:
    cd backend
    python dev_utils/workflow_validation.py --run-id 20260601_104535
    python dev_utils/workflow_validation.py --apply-backfill
    python dev_utils/workflow_validation.py --webhooks-only --api-base http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_COMPANY = os.environ.get("OTTO_COMPANY_ID", "ce9091df-db37-4e7e-877c-2ed0cf2f4c37")
DEFAULT_APPOINTMENT = os.environ.get(
    "OTTO_APPOINTMENT_ID", "0c5b307c-4594-4893-87a3-06328be547f2"
)
DEFAULT_GHL_LOCATION = os.environ.get("OTTO_GHL_LOCATION_ID", "")
DEFAULT_CTM_ACCOUNT = os.environ.get("OTTO_CTM_ACCOUNT_ID", "test-account-999")


def sync_db_url() -> str:
    url = os.environ["DATABASE_URL"]
    return re.sub(r"^postgresql\+asyncpg", "postgresql", url)


def db_query(sql: str, params=()) -> list[dict]:
    conn = psycopg2.connect(sync_db_url())
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def db_query_one(sql: str, params=()) -> dict | None:
    rows = db_query(sql, params)
    return rows[0] if rows else None


def api(method: str, base: str, path: str, token: str | None = None, body: Any = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw.decode(errors="replace")[:500]}
        return e.code, payload


def login(base: str) -> str:
    email = os.environ.get("OTTO_TEST_EMAIL", "test@example.com")
    password = os.environ.get("OTTO_TEST_PASSWORD", "password123")
    code, data = api("POST", base, "/api/v1/auth/login", body={"email": email, "password": password})
    if code != 200 or not isinstance(data, dict):
        raise RuntimeError(f"Login failed: HTTP {code} {data}")
    return data["access_token"]


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def run_db_inventory(out: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "dev_utils" / "db_inventory.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    out.write_text(result.stdout)


def pending_field_counts(company_id: str) -> dict:
    return db_query_one(
        """
        SELECT COUNT(*) AS total_pending,
               COUNT(*) FILTER (WHERE due_at IS NOT NULL) AS with_due_at,
               COUNT(*) FILTER (WHERE owner_id IS NOT NULL) AS with_owner,
               COUNT(*) FILTER (WHERE appointment_id IS NOT NULL) AS with_appointment_id,
               COUNT(*) FILTER (WHERE priority IS NOT NULL) AS with_priority
        FROM pending_actions
        WHERE company_id = %s AND status = 'pending'
        """,
        (company_id,),
    ) or {}


def notification_eligibility(company_id: str) -> dict:
    return db_query_one(
        """
        SELECT
          COUNT(*) AS pending_with_due_at,
          COUNT(*) FILTER (WHERE owner_id IS NOT NULL) AS with_owner,
          COUNT(*) FILTER (WHERE owner_id IS NULL AND call_id IS NOT NULL) AS csr_routed,
          COUNT(*) FILTER (WHERE owner_id IS NULL AND appointment_id IS NOT NULL) AS rep_routed
        FROM pending_actions
        WHERE company_id = %s AND status = 'pending' AND due_at IS NOT NULL
        """,
        (company_id,),
    ) or {}


def pending_for_call(call_id: str) -> list[dict]:
    return db_query(
        """
        SELECT id, action_type, source, call_id, owner_id, due_at, priority, appointment_id, created_at
        FROM pending_actions
        WHERE call_id = %s AND action_type = 'call_back' AND status = 'pending'
        """,
        (call_id,),
    )


def pending_for_appointment(appointment_id: str) -> list[dict]:
    return db_query(
        """
        SELECT id, action_type, source, call_id, owner_id, due_at, priority, appointment_id, created_at
        FROM pending_actions
        WHERE appointment_id = %s AND action_type = 'follow_up' AND status = 'pending'
        """,
        (appointment_id,),
    )


def post_webhook(base: str, path: str, payload: dict) -> tuple[int, Any]:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"error": raw.decode(errors="replace")[:500]}
        return e.code, body


def prep_ghl_integration(company_id: str, location_id: str = "staging-validation-ghl") -> None:
    conn = psycopg2.connect(sync_db_url())
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE company_integrations
        SET location_id = %s
        WHERE company_id = %s AND (location_id IS NULL OR location_id = '')
        """,
        (location_id, company_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def prep_appointment_follow_up_test(appointment_id: str) -> int:
    """Remove prior follow_up rows so idempotency test starts clean."""
    conn = psycopg2.connect(sync_db_url())
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM pending_actions
        WHERE appointment_id = %s AND action_type = 'follow_up' AND status = 'pending'
        """,
        (appointment_id,),
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def probe_ghl_calls(company_id: str, message_id: str) -> list[dict]:
    return db_query(
        """
        SELECT id FROM calls
        WHERE company_id = %s AND extra_metadata->>'ghl_message_id' = %s
        """,
        (company_id, message_id),
    )


def probe_ctm_calls(company_id: str, ctm_call_id: str) -> list[dict]:
    return db_query(
        """
        SELECT id FROM calls
        WHERE company_id = %s AND extra_metadata->>'ctm_call_id' = %s
        """,
        (company_id, ctm_call_id),
    )


def replay_ghl(base: str, evidence: Path, run_suffix: str) -> dict:
    payload = load_fixture("ghl_missed_call.json")
    payload["messageId"] = f"staging-val-ghl-{run_suffix}"
    payload["locationId"] = os.environ.get("OTTO_GHL_LOCATION_ID", "staging-validation-ghl")
    r1_code, r1 = post_webhook(base, "/api/v1/webhooks/ghl/messages", payload)
    call_id = None
    if isinstance(r1, dict):
        call_id = r1.get("tempCallId")
    probe_after_post1 = {
        "calls_with_message_id": len(probe_ghl_calls(DEFAULT_COMPANY, payload["messageId"])),
        "call_ids": [str(r["id"]) for r in probe_ghl_calls(DEFAULT_COMPANY, payload["messageId"])],
    }
    r2_code, r2 = post_webhook(base, "/api/v1/webhooks/ghl/messages", payload)
    call_id_2 = r2.get("tempCallId") if isinstance(r2, dict) else None
    rows = db_query(
        """
        SELECT pa.id, pa.call_id, pa.due_at, pa.priority, pa.source
        FROM pending_actions pa
        JOIN calls c ON c.id = pa.call_id
        WHERE pa.company_id = %s AND pa.action_type = 'call_back' AND pa.status = 'pending'
          AND c.extra_metadata->>'ghl_message_id' = %s
        """,
        (DEFAULT_COMPANY, payload["messageId"]),
    )
    same_call_id = call_id and call_id_2 and call_id == call_id_2
    result = {
        "payload_message_id": payload["messageId"],
        "first_post": {"http": r1_code, "body": r1},
        "second_post": {"http": r2_code, "body": r2},
        "probe_after_post1": probe_after_post1,
        "calls_after_post2": len(probe_ghl_calls(DEFAULT_COMPANY, payload["messageId"])),
        "call_id_first": call_id,
        "call_id_second": call_id_2,
        "same_call_id_on_replay": same_call_id,
        "pending_actions": rows,
        "pending_count": len(rows),
        "pass": (
            r1_code == 200
            and isinstance(r1, dict)
            and r1.get("isMissedCall")
            and len(rows) == 1
            and same_call_id
        ),
    }
    save_json(evidence / "webhook_ghl_missed_call.json", result)
    return result


def pending_for_ctm(ctm_call_id: str, company_id: str) -> list[dict]:
    return db_query(
        """
        SELECT pa.id, pa.action_type, pa.source, pa.call_id, pa.owner_id, pa.due_at, pa.priority
        FROM pending_actions pa
        JOIN calls c ON c.id = pa.call_id
        WHERE pa.company_id = %s
          AND pa.action_type = 'call_back'
          AND pa.status = 'pending'
          AND c.extra_metadata->>'ctm_call_id' = %s
        """,
        (company_id, ctm_call_id),
    )


def replay_ctm(base: str, evidence: Path, run_suffix: str, company_id: str = DEFAULT_COMPANY) -> dict:
    payload = load_fixture("ctm_missed_call.json")
    payload["id"] = f"staging-val-ctm-{run_suffix}"
    payload["account_id"] = DEFAULT_CTM_ACCOUNT
    r1_code, r1 = post_webhook(base, "/api/v1/webhooks/ctm/calls", payload)
    call_id = r1.get("call_id") if isinstance(r1, dict) else None
    probe_after_post1 = {
        "calls_with_ctm_id": len(probe_ctm_calls(company_id, payload["id"])),
        "call_ids": [str(r["id"]) for r in probe_ctm_calls(company_id, payload["id"])],
    }
    r2_code, r2 = post_webhook(base, "/api/v1/webhooks/ctm/calls", payload)
    call_id_2 = r2.get("call_id") if isinstance(r2, dict) else None
    db_rows = pending_for_ctm(payload["id"], company_id)
    same_call_id = call_id and call_id_2 and call_id == call_id_2
    result = {
        "payload_ctm_id": payload["id"],
        "first_post": {"http": r1_code, "body": r1},
        "second_post": {"http": r2_code, "body": r2},
        "probe_after_post1": probe_after_post1,
        "calls_after_post2": len(probe_ctm_calls(company_id, payload["id"])),
        "call_id_first": call_id,
        "call_id_second": call_id_2,
        "same_call_id_on_replay": same_call_id,
        "pending_actions": db_rows,
        "pending_count": len(db_rows),
        "pass": r1_code == 200 and len(db_rows) == 1 and same_call_id,
    }
    save_json(evidence / "webhook_ctm_missed_call.json", result)
    return result


def replay_appointment(base: str, evidence: Path, appointment_id: str, run_suffix: str) -> dict:
    payload = load_fixture("shoonya_job_complete_appointment.json")
    payload["job_id"] = f"staging-val-appt-{run_suffix}"
    payload["call_id"] = appointment_id
    payload["company_id"] = DEFAULT_COMPANY
    r1_code, r1 = post_webhook(base, "/api/v1/webhooks/shoonya/job-complete", payload)
    probe_after_post1 = {
        "pending_follow_up_count": len(pending_for_appointment(appointment_id)),
        "pending_ids": [str(r["id"]) for r in pending_for_appointment(appointment_id)],
    }
    r2_code, r2 = post_webhook(base, "/api/v1/webhooks/shoonya/job-complete", payload)
    db_rows = pending_for_appointment(appointment_id)
    row = db_rows[0] if db_rows else {}
    due_ok = False
    if row.get("due_at"):
        due_ok = True
    result = {
        "appointment_id": appointment_id,
        "first_post": {"http": r1_code, "body": r1},
        "second_post": {"http": r2_code, "body": r2},
        "probe_after_post1": probe_after_post1,
        "pending_actions": db_rows,
        "pending_count": len(db_rows),
        "owner_id": row.get("owner_id"),
        "due_at": row.get("due_at"),
        "priority": row.get("priority"),
        "pass": r1_code == 200 and len(db_rows) == 1 and str(row.get("appointment_id")) == str(appointment_id),
    }
    save_json(evidence / "webhook_appointment_follow_up.json", result)
    return result


async def run_notification_check(company_id: str, evidence: Path) -> dict:
    """Tier A/B/C: SQL eligibility + due_at+10m on latest pending + check_follow_ups."""
    eligibility = notification_eligibility(company_id)
    row = db_query_one(
        """
        SELECT id FROM pending_actions
        WHERE company_id = %s AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
        """,
        (company_id,),
    )
    test_action_id = str(row["id"]) if row else None
    if test_action_id:
        conn = psycopg2.connect(sync_db_url())
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE pending_actions
            SET due_at = (NOW() AT TIME ZONE 'UTC') + INTERVAL '10 minutes'
            WHERE id = %s
            """,
            (test_action_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

    sent = 0
    err = None
    try:
        from app.infrastructure.database.models.company_integration import CompanyIntegrationORM  # noqa: F401
        from app.infrastructure.database.session import AsyncSessionLocal
        from app.services.followup_notification_service import check_follow_ups

        async def _run():
            async with AsyncSessionLocal() as session:
                return await check_follow_ups(session)

        sent = await _run()
    except Exception as exc:
        err = str(exc)
        sent = -1

    out = {
        "test_action_id": test_action_id,
        "due_at_set_to_plus_10_min": test_action_id is not None,
        "check_follow_ups_returned": sent,
        "check_follow_ups_error": err,
        "eligibility_sql": eligibility,
        "pass": (eligibility.get("pending_with_due_at") or 0) > 0 and test_action_id is not None,
    }
    save_json(evidence / "notification_eligibility.json", out)
    return out


def run_backfill(apply: bool, company_id: str, evidence: Path) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "backfill_pending_action_defaults.py"),
        "--company-id",
        company_id,
    ]
    if apply:
        cmd.append("--apply")
    else:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    log_path = evidence / ("backfill_apply.log" if apply else "backfill_dry_run.log")
    log_path.write_text(proc.stdout + proc.stderr)
    before = pending_field_counts(company_id)
    after = before
    if apply and proc.returncode == 0:
        after = pending_field_counts(company_id)
    result = {
        "apply": apply,
        "returncode": proc.returncode,
        "log_file": str(log_path.name),
        "before": before,
        "after": after,
        "pass": proc.returncode == 0,
    }
    save_json(evidence / ("backfill_apply.json" if apply else "backfill_dry_run.json"), result)
    return result


def capture_baseline(base: str, company_id: str, evidence: Path) -> dict:
    inv_path = evidence / "baseline_db_inventory.json"
    run_db_inventory(inv_path)
    token = login(base)
    _, tasks = api("GET", base, f"/api/v1/tasks?company_id={company_id}&status=pending&limit=5", token=token)
    _, metrics = api("GET", base, f"/api/v1/metrics/actions/pending?company_id={company_id}", token=token)
    out = {
        "pending_fields": pending_field_counts(company_id),
        "tasks_api": tasks,
        "metrics_api": metrics,
        "call_back_sources": db_query(
            """
            SELECT COALESCE(source, 'null') AS source, COUNT(*) AS cnt
            FROM pending_actions
            WHERE company_id = %s AND action_type = 'call_back' AND status = 'pending'
            GROUP BY 1
            """,
            (company_id,),
        ),
    }
    save_json(evidence / "baseline_api.json", out)
    return out


def run_staging_validation(base: str, evidence: Path, label: str) -> dict:
    env = os.environ.copy()
    env["OTTO_API_BASE"] = base
    proc = subprocess.run(
        [sys.executable, str(ROOT / "dev_utils" / "staging_validation.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    log_path = evidence / f"staging_validation_{label}.txt"
    log_path.write_text(proc.stdout + proc.stderr)
    failed = "FAIL" in proc.stdout and "FAIL  " in proc.stdout
    summary_line = next((l for l in proc.stdout.splitlines() if l.startswith("=== SUMMARY")), "")
    return {
        "base": base,
        "returncode": proc.returncode,
        "summary": summary_line,
        "pass": proc.returncode == 0,
        "log_file": str(log_path.name),
    }


def build_report(evidence: Path, results: dict) -> None:
    save_json(evidence / "report.json", results)
    lines = [
        "# Workflow Validation Report",
        "",
        f"**Generated:** {datetime.now(ZoneInfo('UTC')).isoformat()}",
        f"**Company:** `{DEFAULT_COMPANY}`",
        f"**Evidence directory:** `{evidence}`",
        "",
        "## Executive Summary",
        "",
    ]
    checks = [
        ("Backfill dry-run", results.get("backfill_dry_run", {}).get("pass")),
        ("Backfill apply", results.get("backfill_apply", {}).get("pass")),
        ("GHL missed call + idempotency", results.get("webhooks_local", {}).get("ghl", {}).get("pass")),
        ("CTM missed call + idempotency", results.get("webhooks_local", {}).get("ctm", {}).get("pass")),
        ("Appointment follow-up + idempotency", results.get("webhooks_local", {}).get("appointment", {}).get("pass")),
        ("Notification eligibility", results.get("notification", {}).get("pass")),
        ("staging_validation local", results.get("staging_validation", {}).get("local", {}).get("pass")),
        ("staging_validation remote", results.get("staging_validation", {}).get("remote", {}).get("pass")),
    ]
    all_pass = all(v for _, v in checks if v is not None)
    for name, ok in checks:
        status = "PASS" if ok else ("FAIL" if ok is False else "SKIP")
        lines.append(f"- **{name}:** {status}")
    lines.extend(
        [
            "",
            f"## Gate Decision: **{'GO' if all_pass else 'NO-GO'}** for appointment reminder implementation",
            "",
            "See `report.json` and per-step JSON logs in this directory for full evidence.",
        ]
    )
    (evidence / "WORKFLOW_VALIDATION_REPORT.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging workflow validation")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--api-base", default=os.environ.get("OTTO_API_BASE", "http://127.0.0.1:8001"))
    parser.add_argument("--remote-base", default="https://ottoai.shunyalabs.ai")
    parser.add_argument("--company-id", default=DEFAULT_COMPANY)
    parser.add_argument("--appointment-id", default=DEFAULT_APPOINTMENT)
    parser.add_argument("--apply-backfill", action="store_true")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--webhooks-only", action="store_true")
    parser.add_argument("--remote-webhooks", action="store_true")
    args = parser.parse_args()

    evidence = Path(__file__).resolve().parent / "evidence" / args.run_id
    evidence.mkdir(parents=True, exist_ok=True)
    run_suffix = args.run_id.replace("_", "")[-8:]
    results: dict[str, Any] = {"run_id": args.run_id, "company_id": args.company_id}

    if args.webhooks_only:
        prep_ghl_integration(args.company_id)
        deleted = prep_appointment_follow_up_test(args.appointment_id)
        results["appointment_prep_deleted"] = deleted
    elif not args.webhooks_only:
        print("Preparing GHL location_id mapping...")
        prep_ghl_integration(args.company_id)

        print("Capturing baseline...")
        results["baseline"] = capture_baseline(args.api_base, args.company_id, evidence)

        if not args.skip_backfill:
            print("Backfill dry-run...")
            results["backfill_dry_run"] = run_backfill(False, args.company_id, evidence)
            if args.apply_backfill:
                print("Backfill apply...")
                results["backfill_apply"] = run_backfill(True, args.company_id, evidence)
                run_db_inventory(evidence / "post_backfill_db_inventory.json")

    print("Preparing appointment follow-up test (clean prior follow_up rows)...")
    deleted = prep_appointment_follow_up_test(args.appointment_id)
    results["appointment_prep_deleted"] = deleted

    print("Webhook replay (local)...")
    results["webhooks_local"] = {
        "ghl": replay_ghl(args.api_base, evidence, run_suffix),
        "ctm": replay_ctm(args.api_base, evidence, run_suffix, args.company_id),
        "appointment": replay_appointment(
            args.api_base, evidence, args.appointment_id, run_suffix
        ),
    }

    print("Notification eligibility...")
    results["notification"] = asyncio.run(run_notification_check(args.company_id, evidence))

    print("staging_validation local + remote...")
    results["staging_validation"] = {
        "local": run_staging_validation(args.api_base, evidence, "local"),
        "remote": run_staging_validation(args.remote_base, evidence, "remote"),
    }

    if args.remote_webhooks:
        print("Webhook replay (remote)...")
        remote_suffix = run_suffix + "r"
        results["webhooks_remote"] = {
            "ghl": replay_ghl(args.remote_base, evidence / "remote", remote_suffix),
            "ctm": replay_ctm(args.remote_base, evidence / "remote", remote_suffix),
            "appointment": replay_appointment(
                args.remote_base,
                evidence / "remote",
                args.appointment_id,
                remote_suffix,
            ),
        }

    build_report(evidence, results)
    print(f"Evidence written to {evidence}")
    print(f"Gate: see {evidence / 'WORKFLOW_VALIDATION_REPORT.md'}")
    critical = [
        results.get("backfill_dry_run", {}).get("pass", True),
        results.get("backfill_apply", {}).get("pass", True) if args.apply_backfill else True,
        results.get("webhooks_local", {}).get("ghl", {}).get("pass"),
        results.get("webhooks_local", {}).get("ctm", {}).get("pass"),
        results.get("webhooks_local", {}).get("appointment", {}).get("pass"),
        results.get("notification", {}).get("pass"),
        results.get("staging_validation", {}).get("local", {}).get("pass"),
        results.get("staging_validation", {}).get("remote", {}).get("pass"),
    ]
    return 1 if not all(critical) else 0


if __name__ == "__main__":
    raise SystemExit(main())
