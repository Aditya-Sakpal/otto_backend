#!/usr/bin/env python3
"""
Follow-up agent runtime activation validation (verification-only).

Goal:
- Prove whether follow_up_otto generation is operational end-to-end.
- Do not add features; only verify runtime/deployment readiness.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

UTC = timezone.utc
EVIDENCE = ROOT / "dev_utils" / "evidence"
TEST_LEAD_ID = "b0ae4dd6-a5d7-4802-99c6-51dd5314e91f"


def sync_url() -> str:
    return re.sub(r"^postgresql\+asyncpg", "postgresql", os.environ["DATABASE_URL"])


def db_count_for_lead(lead_id: str) -> int:
    conn = psycopg2.connect(sync_url())
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM follow_up_otto WHERE lead_id = %s::uuid", (lead_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return int(count)


def bool_env(name: str) -> bool:
    return bool(os.getenv(name))


def import_ok(module: str) -> tuple[bool, str | None]:
    try:
        importlib.import_module(module)
        return True, None
    except Exception as e:  # pragma: no cover
        return False, str(e)


def run_agent_once(lead_id: str) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "app/agents"
    proc = subprocess.run(
        [sys.executable, "-m", "contextual_follow_up_agent", "--lead-id", lead_id],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def classify(report: dict) -> tuple[str, str]:
    # A fully operational only if all runtime checks pass and at least one row is generated.
    if (
        report["checks"]["celery_importable"]
        and report["checks"]["aiosqlite_importable"]
        and report["checks"]["redis_reachable"]
        and report["checks"]["agent_importable"]
        and report["checks"]["agent_run_exit_zero"]
        and report["checks"]["follow_up_otto_created"]
    ):
        return "A", "GO"

    # B deployment-disabled if code paths exist/import, but runtime infra/deps are blockers.
    deployment_block = (
        not report["checks"]["celery_importable"]
        or not report["checks"]["aiosqlite_importable"]
        or not report["checks"]["redis_reachable"]
    )
    if deployment_block and report["checks"]["agent_importable"]:
        return "B", "NO-GO"

    # C for mixed runtime behavior without full end-to-end success.
    if report["checks"]["agent_importable"]:
        return "C", "NO-GO"

    return "D", "NO-GO"


def main() -> int:
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": {},
        "evidence": {},
    }

    # Dependency and config presence checks
    report["checks"]["env_redis_url_present"] = bool_env("REDIS_URL")
    report["checks"]["env_anthropic_present"] = bool_env("ANTHROPIC_API_KEY")
    report["checks"]["env_openai_present"] = bool_env("OPENAI_API_KEY")
    report["checks"]["env_twilio_sid_present"] = bool_env("TWILIO_ACCOUNT_SID")
    report["checks"]["env_twilio_token_present"] = bool_env("TWILIO_AUTH_TOKEN")
    report["checks"]["enable_celery_flag_true"] = str(os.getenv("ENABLE_CELERY", "")).lower() == "true"

    ok, err = import_ok("celery")
    report["checks"]["celery_importable"] = ok
    if err:
        report["evidence"]["celery_import_error"] = err

    ok, err = import_ok("aiosqlite")
    report["checks"]["aiosqlite_importable"] = ok
    if err:
        report["evidence"]["aiosqlite_import_error"] = err

    # Redis reachability
    try:
        import redis

        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        report["checks"]["redis_reachable"] = bool(r.ping())
    except Exception as e:  # pragma: no cover
        report["checks"]["redis_reachable"] = False
        report["evidence"]["redis_error"] = str(e)

    # Agent importability
    sys.path.insert(0, str(ROOT / "app" / "agents"))
    ok, err = import_ok("contextual_follow_up_agent")
    report["checks"]["agent_importable"] = ok
    if err:
        report["evidence"]["agent_import_error"] = err

    # End-to-end attempt: create follow_up_otto row for a real lead
    before = db_count_for_lead(TEST_LEAD_ID)
    code, run_output = run_agent_once(TEST_LEAD_ID)
    after = db_count_for_lead(TEST_LEAD_ID)

    report["evidence"]["test_lead_id"] = TEST_LEAD_ID
    report["evidence"]["before_count"] = before
    report["evidence"]["after_count"] = after
    report["evidence"]["agent_run_exit_code"] = code
    report["evidence"]["agent_run_output_tail"] = run_output[-3000:]

    report["checks"]["agent_run_exit_zero"] = code == 0
    report["checks"]["follow_up_otto_created"] = after > before

    classification, verdict = classify(report)
    report["classification"] = classification
    report["verdict"] = verdict
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = EVIDENCE / f"follow_up_runtime_activation_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "validation.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nEvidence written to: {out_file}")
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
