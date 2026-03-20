"""
Replay CTM webhook calls for all calls of a given company.

WARNING:
- This is mainly for local/testing.
- It fakes CTM payloads from existing `calls` rows.
- Signature handling is simplified; you may need to adjust to match
  your CTM secret / verification logic or disable signature checks.
"""

import os
import json
import time
import base64
import hmac
import hashlib
from typing import Optional

import psycopg2
import psycopg2.extras
import requests

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

# Local FastAPI server URL
API_BASE_URL = os.getenv("OTTO_API_URL", "http://127.0.0.1:8000")

CTM_WEBHOOK_URL = f"{API_BASE_URL}/api/v1/webhooks/ctm/calls"

# Database URL (same as your app)
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n",
)

# Target company ID (Synkyo Roofers)
TARGET_COMPANY_ID = "b414e9f9-7786-4a80-b746-3e63a567cb04"

# How many calls to send (None = all)
# Start with a small batch to verify behaviour.
MAX_CALLS: Optional[int] = None # test with first 10 calls


# -------------------------------------------------------------------
# CTM signature helper (simplified)
# -------------------------------------------------------------------

# Put your decrypted CTM secret here if you want real verification.
# Otherwise, set VERIFY_SIGNATURE = False and server must skip checks.
CTM_SECRET = os.getenv("CTM_TEST_SECRET", "dummy-secret")
VERIFY_SIGNATURE = False  # set True only if server expects real HMAC


def make_ctm_signature(timestamp: str, body: bytes) -> str:
    """
    CTM spec: Base64( HMAC-SHA1(secret, time + body) )
    """
    msg = (timestamp + body.decode("utf-8")).encode("utf-8")
    digest = hmac.new(CTM_SECRET.encode("utf-8"), msg, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


# -------------------------------------------------------------------
# Main script
# -------------------------------------------------------------------


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    psycopg2.extras.register_uuid()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # 1) Fetch calls for target company
    query = """
        SELECT id,
               company_id,
               phone_number,
               audio_url,
               duration_seconds,
               missed_call,
               call_type,
               handled_by_user_id,
               extra_metadata
        FROM public.calls
        WHERE company_id = %s
        ORDER BY created_at
    """
    params = [TARGET_COMPANY_ID]
    if MAX_CALLS is not None:
        query += " LIMIT %s"
        params.append(MAX_CALLS)

    cur.execute(query, params)
    rows = cur.fetchall()
    print(f"Found {len(rows)} calls for company {TARGET_COMPANY_ID}")

    # 2) Preload user emails for mapping handled_by_user_id -> agent_email
    cur.execute(
        """
        SELECT id, email
        FROM public.users
        WHERE company_id = %s
        """,
        [TARGET_COMPANY_ID],
    )
    user_rows = cur.fetchall()
    user_email_by_id = {str(r["id"]): r["email"] for r in user_rows}
    print(f"Loaded {len(user_email_by_id)} users for agent_email mapping")

    session = requests.Session()

    for idx, row in enumerate(rows, start=1):
        call_id = str(row["id"])
        phone_number = row["phone_number"]
        audio_url = row["audio_url"]
        duration = row["duration_seconds"]
        call_type = row["call_type"] or "inbound"
        missed_call = bool(row["missed_call"])
        handled_by = row["handled_by_user_id"]
        extra = row["extra_metadata"] or {}

        # Map handled_by_user_id -> agent_email, fallback to a generic one
        agent_email = None
        if handled_by is not None:
            agent_email = user_email_by_id.get(str(handled_by))

        if agent_email is None:
            agent_email = "unknown@synkyoroofers.test"

        # 3) Build a minimal CTM-like payload
        #    Matches the docstring comment in the /ctm/calls route.
        payload = {
            "id": call_id,
            "direction": "inbound" if call_type.lower() != "outbound" else "outbound",
            "status": "answered" if not missed_call else "no_answer",
            "caller_number": phone_number,
            "dialed_number": extra.get("dialed_number", phone_number),
            "tracking_number": extra.get("tracking_number", phone_number),
            "agent_email": agent_email,
            "audio": audio_url,
            "duration": duration,
            # If you know CTM account_id for this company, pass it here;
            # otherwise backend must infer or ignore in test mode.
            "account_id": "dummy-ctm-id-for-synkyo",
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        timestamp = str(int(time.time()))

        headers = {
            "Content-Type": "application/json",
            # FastAPI route expects these headers, but you might
            # disable signature verification for local testing.
            "x-ctm-time": timestamp,
        }

        if VERIFY_SIGNATURE:
            headers["x-wh-signature"] = make_ctm_signature(timestamp, body_bytes)
        else:
            headers["x-wh-signature"] = "test-signature"

        resp = session.post(CTM_WEBHOOK_URL, headers=headers, data=body_bytes)

        print(
            f"[{idx}/{len(rows)}] call_id={call_id} "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

        # Optional: small sleep to avoid hammering server
        time.sleep(0.05)

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()