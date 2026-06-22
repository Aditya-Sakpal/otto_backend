#!/usr/bin/env python3
"""Smoke-test Retell voice-agent endpoints against a running backend."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass

BASE = os.getenv("VOICE_AGENT_SMOKE_BASE", "http://127.0.0.1:8001/api/v1/voice-agent")
SECRET = os.getenv("VOICE_AGENT_SECRET", "")
COMPANY = os.getenv(
    "VOICE_AGENT_DEFAULT_COMPANY_ID", "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"
)
HEADERS = {"X-Voice-Agent-Secret": SECRET, "Content-Type": "application/json"}


def _retell_body(args: dict, call_id: str) -> dict:
    return {
        "name": "smoke",
        "args": args,
        "call": {"from_number": "+16025551234", "call_id": call_id},
    }


def run_step(name: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        result = fn()
        ms = int((time.perf_counter() - t0) * 1000)
        ok = result.get("ok", True)
        print(f"{'PASS' if ok else 'FAIL'} {name} ({ms}ms) {result.get('detail', '')}")
        return {"name": name, "ok": ok, "ms": ms, **result}
    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        print(f"FAIL {name} ({ms}ms) {exc}")
        return {"name": name, "ok": False, "ms": ms, "error": str(exc)}


def main() -> int:
    if not SECRET:
        print("VOICE_AGENT_SECRET not set", file=sys.stderr)
        return 1

    call_id = f"smoke-{uuid.uuid4().hex[:8]}"
    lead_id: str | None = None
    slot: str | None = None
    results: list[dict] = []

    with httpx.Client(timeout=60.0) as client:

        def search_lead():
            r = client.post(
                f"{BASE}/search_lead",
                headers=HEADERS,
                params={"call_id": call_id},
                json=_retell_body({"company_id": COMPANY}, call_id),
            )
            body = r.json()
            return {"status": r.status_code, "ok": r.status_code == 200, "detail": body}

        results.append(run_step("search_lead", search_lead))

        def current_date_fallback():
            r = client.get(
                f"{BASE}/get_current_date",
                headers=HEADERS,
                params={"company_id": "1"},
            )
            body = r.json()
            return {
                "status": r.status_code,
                "ok": r.status_code == 200 and "datetime" in body,
                "detail": body.get("datetime", body),
            }

        results.append(run_step("get_current_date_bad_company_id", current_date_fallback))

        def create_lead():
            nonlocal lead_id
            r = client.post(
                f"{BASE}/create_lead",
                headers=HEADERS,
                params={"call_id": call_id},
                json=_retell_body(
                    {
                        "company_id": COMPANY,
                        "customer_name": "Smoke Test User",
                        "lead_source": "voice_agent",
                        "lead_status": "qualified",
                        "property_address": "123 Main St, Phoenix AZ",
                    },
                    call_id,
                ),
            )
            body = r.json()
            lead_id = body.get("lead_id")
            return {
                "status": r.status_code,
                "ok": r.status_code == 200 and bool(lead_id),
                "detail": body,
            }

        results.append(run_step("create_lead", create_lead))

        def slots():
            nonlocal slot
            target = (date.today() + timedelta(days=7)).isoformat()
            r = client.get(
                f"{BASE}/get_available_slots",
                headers=HEADERS,
                params={"company_id": COMPANY, "date": target},
            )
            body = r.json()
            slots_list = body.get("slots") or []
            slot = slots_list[0] if slots_list else None
            return {
                "status": r.status_code,
                "ok": r.status_code == 200,
                "detail": f"{len(slots_list)} slots on {target}",
            }

        results.append(run_step("get_available_slots", slots))

        def create_appointment():
            if not slot:
                return {"ok": False, "detail": "no slot available — skipped"}
            r = client.post(
                f"{BASE}/create_appointment",
                headers=HEADERS,
                params={"call_id": call_id},
                json=_retell_body(
                    {
                        "company_id": COMPANY,
                        "customer_name": "Smoke Test User",
                        "selected_start": slot,
                        "property_address": "123 Main St, Phoenix AZ",
                        "lead_id": lead_id,
                    },
                    call_id,
                ),
            )
            body = r.json()
            return {
                "status": r.status_code,
                "ok": r.status_code == 200 and bool(body.get("appointment_id")),
                "detail": body,
            }

        results.append(run_step("create_appointment", create_appointment))

        def save_property():
            r = client.post(
                f"{BASE}/save_property_details",
                headers=HEADERS,
                json=_retell_body(
                    {
                        "company_id": COMPANY,
                        "property_address": "123 Main St, Phoenix AZ",
                        "house_type": "single-story",
                        "roof_type": "tile",
                    },
                    call_id,
                ),
            )
            return {"status": r.status_code, "ok": r.status_code == 200, "detail": r.json()}

        results.append(run_step("save_property_details", save_property))

        def webhook():
            r = client.post(
                "http://127.0.0.1:8001/api/v1/webhooks/retell/call-ended",
                json={
                    "call": {
                        "call_id": call_id,
                        "from_number": "+16025551234",
                        "transcript": "smoke test transcript",
                    },
                    "metadata": {"lead_id": lead_id},
                },
            )
            return {"status": r.status_code, "ok": r.status_code == 200, "detail": r.json()}

        results.append(run_step("retell_webhook", webhook))

    failed = [r for r in results if not r.get("ok")]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print(json.dumps(failed, indent=2, default=str))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
