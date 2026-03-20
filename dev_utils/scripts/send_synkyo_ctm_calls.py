#!/usr/bin/env python3
"""
Fire CTM-style webhooks to the local backend for all calls
belonging to the Synkyo Roofers company.

This script:
- Connects directly to the Postgres DB using DATABASE_URL
- Selects all calls for company_id = SYNKYO_COMPANY_ID
- For each call, builds a minimal CTM-like JSON payload
- POSTs it to the local CTM webhook:
      POST http://127.0.0.1:8000/api/v1/webhooks/ctm/calls

Notes:
- The CTM webhook in our app does not require x-wh-signature / x-ctm-time
  when we call it in dev; migrate_calls.py also sends only JSON.
- This script is for local/testing only.
"""

import os
import time
import uuid
import json
from typing import Any, Dict

import httpx
import psycopg2
import psycopg2.extras


# Company we want to replay calls for (Synkyo Roofers)
SYNKYO_COMPANY_ID = "b414e9f9-7786-4a80-b746-3e63a567cb04"

# Local backend URL (adjust if your dev server differs)
BASE_URL = os.environ.get("OTTO_BASE_URL", "http://127.0.0.1:8000")
WEBHOOK_URL = f"{BASE_URL}/api/v1/webhooks/ctm/calls"

# How many calls to send (None = all)
MAX_CALLS: int | None = None

# Delay between webhook calls in seconds
DELAY_BETWEEN_CALLS = 0.5


def get_db_url() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    # psycopg2 expects postgresql://, not postgres://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url


def fetch_calls() -> list[Dict[str, Any]]:
    db_url = get_db_url()
    conn = psycopg2.connect(db_url)
    try:
        psycopg2.extras.register_uuid()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sql = """
                SELECT
                    id,
                    company_id,
                    phone_number,
                    audio_url,
                    call_type,
                    missed_call,
                    duration_seconds,
                    extra_metadata
                FROM public.calls
                WHERE company_id = %s
                  AND audio_url IS NOT NULL
                  AND audio_url <> ''
                ORDER BY created_at ASC
            """
            cur.execute(sql, (uuid.UUID(SYNKYO_COMPANY_ID),))
            rows = cur.fetchall()
            if MAX_CALLS is not None:
                rows = rows[:MAX_CALLS]
            return rows
    finally:
        conn.close()


def build_ctm_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a minimal CTM-style payload from an internal call row.
    This is not exactly what CTM sends, but enough for our webhook
    to treat it like a completed call with a recording.
    """
    call_id = str(row["id"])
    phone_number = row.get("phone_number") or ""
    audio_url = row.get("audio_url") or ""
    missed = bool(row.get("missed_call"))
    duration = row.get("duration_seconds") or 0

    status = "no_answer" if missed else "completed"
    direction = "inbound"

    payload: Dict[str, Any] = {
        "id": call_id,  # CTM call id
        "direction": direction,
        "status": status,
        "caller_number": phone_number,
        "caller_number_bare": phone_number,
        "audio": audio_url,
        "duration": duration,
        # Provide some minimal account/company hint; your webhook
        # will map account_id to a company via company_integrations.
        # For local testing, we can pass the company id here and let
        # CTMService fall back to it if needed.
        "account_id": str(row["company_id"]),
    }

    extra = row.get("extra_metadata") or {}
    if isinstance(extra, dict):
        payload["custom_fields"] = extra

    return payload


def send_webhook(payload: Dict[str, Any]) -> tuple[bool, str]:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            try:
                body = resp.json()
                return True, json.dumps(body)
            except Exception:
                return True, resp.text
        else:
            return False, f"{resp.status_code}: {resp.text[:200]}"


def main() -> None:
    rows = fetch_calls()
    total = len(rows)
    print(f"Found {total} calls for company {SYNKYO_COMPANY_ID}")

    success = 0
    failed = 0

    for idx, row in enumerate(rows, start=1):
        payload = build_ctm_payload(row)
        print(f"[{idx}/{total}] Sending CTM webhook for call {row['id']}...", end=" ", flush=True)
        ok, msg = send_webhook(payload)
        if ok:
            print(f"OK -> {msg}")
            success += 1
        else:
            print(f"FAIL -> {msg}")
            failed += 1

        if idx < total:
            time.sleep(DELAY_BETWEEN_CALLS)

    print("\n=== Done ===")
    print(f"Success: {success}")
    print(f"Failed:  {failed}")


if __name__ == "__main__":
    main()

