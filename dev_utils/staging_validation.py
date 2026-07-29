"""
Staging validation harness for Otto Direct Fixes + closure work.

Usage:
    cd backend
    python dev_utils/staging_validation.py

Environment (optional):
    OTTO_API_BASE=http://127.0.0.1:8001
    OTTO_COMPANY_ID=<uuid>
    OTTO_TEST_EMAIL=test@example.com
    OTTO_TEST_PASSWORD=password123
    OTTO_APPOINTMENT_WITH_AUDIO=<uuid>  # for presign check
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.pending_action_metrics import classify_pending_action_type

BASE = os.environ.get("OTTO_API_BASE", "http://127.0.0.1:8001")
COMPANY_ID = os.environ.get(
    "OTTO_COMPANY_ID",
    "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
)
EMAIL = os.environ.get("OTTO_TEST_EMAIL", "test@example.com")
PASSWORD = os.environ.get("OTTO_TEST_PASSWORD", "password123")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

passed = 0
failed = 0
warned = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"FAIL  {name}" + (f" — {detail}" if detail else ""))


def warn(name: str, detail: str = "") -> None:
    global warned
    warned += 1
    print(f"WARN  {name}" + (f" — {detail}" if detail else ""))


def api(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.getcode(), json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else {"error": str(e.reason)}
        except json.JSONDecodeError:
            payload = {"error": raw.decode(errors="replace")[:300]}
        return e.code, payload


def login() -> str | None:
    code, data = api("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD})
    if code != 200 or not isinstance(data, dict):
        check("auth/login", False, f"HTTP {code}")
        return None
    check("auth/login", True)
    return data.get("access_token")


def validate_metrics(token: str) -> None:
    code, data = api(
        "GET",
        f"/api/v1/metrics/actions/pending?company_id={COMPANY_ID}",
        token=token,
    )
    if code != 200 or not isinstance(data, dict):
        check("metrics/actions/pending", False, f"HTTP {code}")
        return
    required = {
        "total_pending",
        "follow_ups_needed",
        "calls_to_make",
        "appointments_to_schedule",
        "start_date",
        "end_date",
    }
    missing = required - set(data.keys())
    check("metrics/actions/pending schema", not missing, f"missing {missing}" if missing else "")
    total = data.get("total_pending") or 0
    bucket_sum = (
        (data.get("follow_ups_needed") or 0)
        + (data.get("calls_to_make") or 0)
        + (data.get("appointments_to_schedule") or 0)
    )
    check(
        "metrics bucket sum <= total_pending",
        bucket_sum <= total,
        f"total={total} buckets={bucket_sum}",
    )


def validate_property_surfacing(token: str) -> None:
    code, appts = api("GET", f"/api/v1/appointments?company_id={COMPANY_ID}&limit=5", token=token)
    if code != 200 or not isinstance(appts, list) or not appts:
        warn("appointment context property fields", "no appointments to test")
        return
    aid = appts[0]["id"]
    code, ctx = api("GET", f"/api/v1/appointments/{aid}/context", token=token)
    if code != 200:
        check("appointment context", False, f"HTTP {code}")
        return
    hist = ctx.get("conversation_history") or []
    has_fields = bool(hist) and all(
        "service_requested" in h and "property_details" in h for h in hist[:1]
    )
    check("appointment context schema fields", has_fields or not hist, f"history={len(hist)}")
    populated = any((h.get("property_details") or h.get("service_requested")) for h in hist)
    if populated:
        check("appointment context property data", True)
    else:
        warn("appointment context property data", "fields present but empty on sample")


def validate_presign(token: str) -> None:
    appt_id = os.environ.get("OTTO_APPOINTMENT_WITH_AUDIO")
    if not appt_id:
        code, appts = api("GET", f"/api/v1/appointments?company_id={COMPANY_ID}&limit=20", token=token)
        if code == 200 and isinstance(appts, list):
            for a in appts:
                if a.get("audio_url"):
                    appt_id = a["id"]
                    break
    if not appt_id:
        warn("presigned playback", "no appointment with audio_url found")
        return
    code, ctx = api("GET", f"/api/v1/appointments/{appt_id}/context", token=token)
    audio = (ctx or {}).get("audio_url") or ""
    is_presigned = "X-Amz-Signature=" in audio or "X-Amz-Credential=" in audio
    if is_presigned:
        check("presigned appointment audio_url", True)
        try:
            head = urllib.request.Request(audio, method="HEAD")
            with urllib.request.urlopen(head, timeout=30) as resp:
                check("presigned URL reachable", resp.status in (200, 206), f"HTTP {resp.status}")
        except Exception as e:
            check("presigned URL reachable", False, str(e))
    else:
        warn(
            "presigned appointment audio_url",
            "URL not presigned — check AWS credentials / private bucket config",
        )


def validate_classification_unit() -> None:
    cases = [
        ("call_back", "calls_to_make"),
        ("send_quote", "follow_ups_needed"),
        ("schedule_appointment", "appointments_to_schedule"),
    ]
    for action_type, bucket in cases:
        check(
            f"classify {action_type}",
            classify_pending_action_type(action_type) == bucket,
        )


def validate_fixtures_present() -> None:
    for name in ("ghl_missed_call.json", "ctm_missed_call.json", "shoonya_job_complete_appointment.json"):
        path = FIXTURES / name
        check(f"fixture {name}", path.is_file())


def print_webhook_manual_steps() -> None:
    print("\n--- Manual webhook replay (staging) ---")
    print(f"GHL missed call fixture: {FIXTURES / 'ghl_missed_call.json'}")
    print("  POST to your GHL webhook route; replay twice -> expect one call_back pending action")
    print(f"CTM missed call fixture: {FIXTURES / 'ctm_missed_call.json'}")
    print(f"Shunya job-complete fixture: {FIXTURES / 'shoonya_job_complete_appointment.json'}")
    print("  Set appointment_id; replay twice -> expect one follow_up row with appointment_id FK")


def main() -> int:
    print(f"Staging validation against {BASE}\n")
    validate_classification_unit()
    validate_fixtures_present()

    token = login()
    if token:
        validate_metrics(token)
        validate_property_surfacing(token)
        validate_presign(token)

    print_webhook_manual_steps()
    print(f"\n=== SUMMARY: PASS={passed} FAIL={failed} WARN={warned} ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
