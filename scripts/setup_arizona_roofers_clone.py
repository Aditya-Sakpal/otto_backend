"""
Full setup script: Clone Arizona Roofers company, add users, then re-run
100 calls (with real S3 audio URLs) from Feb 2 2026 through the Shunya
AI pipeline.

Run:
    python scripts/setup_arizona_roofers_clone.py

Outputs final login credentials at the end.
"""

import uuid
import hashlib
import base64
import json
import asyncio
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import bcrypt
import httpx

# ─── DB & API CONFIG ────────────────────────────────────────────────────────
DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
SOURCE_COMPANY_ID = "6d40b509-82bc-4d21-9614-de91cc25dc1b"

SHUNYA_BASE_URL = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY  = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"

# ─── NEW COMPANY ─────────────────────────────────────────────────────────────
NEW_COMPANY_ID   = str(uuid.uuid4())
NEW_COMPANY_NAME = "Arizona Roofers Clone"

# Credentials
EXEC_PASSWORD   = "AZRoofers@Admin2026"
MEMBER_PASSWORD = "AZRoofers@Demo2026"

# ─── USERS ───────────────────────────────────────────────────────────────────
USERS = [
    # (first, last, email, role)
    ("Anthony", "Rivera",   "admin@arizonaroofers-clone.com",       "executive"),
    ("Maria",   "Gonzalez", "maria.gonzalez@arizonaroofers-clone.com", "csr"),
    ("James",   "Parker",   "james.parker@arizonaroofers-clone.com",   "csr"),
    ("Tyler",   "Brooks",   "tyler.brooks@arizonaroofers-clone.com",   "sales_rep"),
    ("Ashley",  "Chen",     "ashley.chen@arizonaroofers-clone.com",    "sales_rep"),
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    pre = base64.b64encode(hashlib.sha256(plain.encode()).digest()).decode()
    return bcrypt.hashpw(pre.encode(), bcrypt.gensalt()).decode()


# ─── PHASE 1: Create company + users ─────────────────────────────────────────
def phase1_create_company_and_users(conn):
    cur = conn.cursor()
    psycopg2.extras.register_uuid()

    # Fetch source company config
    cur.execute("SELECT * FROM companies WHERE id=%s", (SOURCE_COMPANY_ID,))
    src = cur.fetchone()
    col_names = [d[0] for d in cur.description]
    src_row = dict(zip(col_names, src))

    print(f"\n[Source] {src_row['name']} -> cloning config…")
    print(f"  reference_doc_url : {src_row['reference_doc_url']}")
    print(f"  sop_doc_url       : {src_row['sop_doc_url']}")
    print(f"  csr_sop_doc_url   : {src_row['csr_sop_doc_url']}")
    print(f"  sales_sop_doc_url : {src_row['sales_sop_doc_url']}")

    # Create new company
    cur.execute("""
        INSERT INTO companies
          (id, name, phone_number, address, extra_metadata,
           reference_doc_url, sop_doc_url, csr_sop_doc_url, sales_sop_doc_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO NOTHING
    """, (
        NEW_COMPANY_ID,
        NEW_COMPANY_NAME,
        src_row["phone_number"],
        src_row["address"],
        json.dumps(src_row["extra_metadata"] or {"ghost_mode_enabled": True}),
        src_row["reference_doc_url"],
        src_row["sop_doc_url"],
        src_row["csr_sop_doc_url"],
        src_row["sales_sop_doc_url"],
    ))
    print(f"\n[Company] {NEW_COMPANY_NAME}  id={NEW_COMPANY_ID}")

    # Create users
    user_ids = {}
    for first, last, email, role in USERS:
        uid  = str(uuid.uuid4())
        pw   = EXEC_PASSWORD if role == "executive" else MEMBER_PASSWORD
        h    = hash_password(pw)
        cur.execute("""
            INSERT INTO users
              (id, email, password_hash, role, is_active,
               first_name, last_name, company_id, extra_metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (email) DO UPDATE SET company_id=EXCLUDED.company_id
            RETURNING id
        """, (uid, email, h, role, True, first, last, NEW_COMPANY_ID,
               psycopg2.extras.Json({})))
        row = cur.fetchone()
        actual_id = str(row[0]) if row else uid
        user_ids[email] = {"id": actual_id, "role": role, "name": f"{first} {last}"}
        print(f"  [{role}] {first} {last} <{email}>  id={actual_id}")

    conn.commit()
    cur.close()
    return user_ids


# ─── PHASE 2: Fetch 100 source calls ─────────────────────────────────────────
def phase2_fetch_source_calls(conn) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, audio_url, phone_number, created_at, duration_seconds,
               extra_metadata
        FROM calls
        WHERE company_id = %s
          AND audio_url LIKE 'https://ottoaudio.s3%%'
          AND created_at >= '2026-02-02'
        ORDER BY created_at
        LIMIT 100
    """, (SOURCE_COMPANY_ID,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    result = [dict(zip(cols, r)) for r in rows]
    cur.close()
    print(f"\n[Calls] Fetched {len(result)} calls with real S3 audio URLs from Feb 2+")
    return result


# ─── PHASE 3: Create contact cards + call records in new company ───────────
def phase3_seed_calls(conn, source_calls: list, user_ids: dict) -> list:
    """Insert contact_cards and call rows for the new company.
    Returns list of new call dicts (new_call_id, audio_url, phone_number, etc.)
    """
    cur = conn.cursor()
    psycopg2.extras.register_uuid()

    # Pick a default CSR to handle calls
    csrs = [v for v in user_ids.values() if v["role"] == "csr"]
    default_csr = csrs[0] if csrs else None

    new_calls = []
    phone_to_cc = {}  # phone -> contact_card_id

    for i, call in enumerate(source_calls):
        phone = call["phone_number"] or f"0000000{i:04d}"

        # Create/reuse contact card
        if phone not in phone_to_cc:
            cc_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO contact_cards
                  (id, company_id, primary_phone)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (cc_id, NEW_COMPANY_ID, phone))
            row = cur.fetchone()
            cc_id = str(row[0]) if row else cc_id
            phone_to_cc[phone] = cc_id
        else:
            cc_id = phone_to_cc[phone]

        new_call_id = str(uuid.uuid4())
        duration = call["duration_seconds"] or 0
        answered_at = call["created_at"]

        cur.execute("""
            INSERT INTO calls
              (id, company_id, contact_card_id, phone_number, missed_call,
               audio_url, duration_seconds, handled_by_user_id,
               answered_at, call_type, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            new_call_id,
            NEW_COMPANY_ID,
            cc_id,
            phone,
            False,
            call["audio_url"],
            duration,
            default_csr["id"] if default_csr else None,
            answered_at,
            "csr_call",
            "pending",
        ))

        new_calls.append({
            "new_call_id":  new_call_id,
            "audio_url":    call["audio_url"],
            "phone_number": phone,
            "call_date":    answered_at.isoformat() if hasattr(answered_at, "isoformat") else str(answered_at),
            "duration":     duration,
        })

        if (i + 1) % 10 == 0:
            conn.commit()
            print(f"  Inserted {i+1} call records…")

    conn.commit()
    cur.close()
    print(f"[Calls] Inserted {len(new_calls)} call records into new company")
    return new_calls


# ─── PHASE 4: Submit calls to Shunya API ─────────────────────────────────────
async def phase4_submit_to_shunya(new_calls: list, user_ids: dict):
    csrs = [v for v in user_ids.values() if v["role"] == "csr"]
    csr_cycle = csrs * (len(new_calls) // len(csrs) + 1) if csrs else [{"id": "unknown", "name": "Agent"}]

    headers = {
        "X-API-Key": SHUNYA_API_KEY,
        "Content-Type": "application/json",
        "X-Company-Id": NEW_COMPANY_ID,
    }

    submitted, failed = 0, 0
    BATCH = 5  # concurrent
    DELAY = 0.5  # seconds between batches

    async with httpx.AsyncClient(timeout=30.0) as client:
        for batch_start in range(0, len(new_calls), BATCH):
            batch = new_calls[batch_start:batch_start + BATCH]
            tasks = []
            for j, call in enumerate(batch):
                csr = csr_cycle[(batch_start + j) % len(csr_cycle)]
                payload = {
                    "call_id":      call["new_call_id"],
                    "company_id":   NEW_COMPANY_ID,
                    "audio_url":    call["audio_url"],
                    "phone_number": call["phone_number"],
                    "duration":     call["duration"] or 60,
                    "call_date":    call["call_date"],
                    "metadata": {
                        "agent": {
                            "id":   csr["id"],
                            "name": csr["name"],
                        },
                        "call_type": "csr_call",
                        "allow_reprocess": True,
                    },
                    "options": {
                        "priority": "normal",
                    },
                }
                tasks.append(client.post(
                    f"{SHUNYA_BASE_URL}/api/v1/call-processing/process",
                    json=payload,
                    headers=headers,
                ))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    print(f"  ✗ Error: {res}")
                    failed += 1
                elif res.status_code in (200, 202):
                    submitted += 1
                else:
                    print(f"  ✗ HTTP {res.status_code}: {res.text[:200]}")
                    failed += 1

            total_done = batch_start + len(batch)
            print(f"  Submitted batch {batch_start+1}-{total_done}  "
                  f"(ok={submitted}, fail={failed})")
            await asyncio.sleep(DELAY)

    print(f"\n[Shunya] Done — submitted={submitted}, failed={failed}")
    return submitted, failed


# ─── MAIN ────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print(" Arizona Roofers Clone Setup")
    print("=" * 60)

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    psycopg2.extras.register_uuid()

    try:
        # Phase 1
        user_ids = phase1_create_company_and_users(conn)

        # Phase 2
        source_calls = phase2_fetch_source_calls(conn)
        if not source_calls:
            print("No calls found — aborting.")
            return

        # Phase 3
        new_calls = phase3_seed_calls(conn, source_calls, user_ids)

        # Phase 4
        submitted, failed = await phase4_submit_to_shunya(new_calls, user_ids)

        # Save state
        state = {
            "new_company_id":   NEW_COMPANY_ID,
            "new_company_name": NEW_COMPANY_NAME,
            "users": user_ids,
            "calls_submitted": submitted,
            "calls_failed": failed,
        }
        state_path = "scripts/arizona_clone_state.json"
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nState saved → {state_path}")

    finally:
        conn.close()

    # ── Credentials Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" NEW COMPANY CREATED SUCCESSFULLY")
    print("=" * 60)
    print(f"  Company ID   : {NEW_COMPANY_ID}")
    print(f"  Company Name : {NEW_COMPANY_NAME}")
    print()
    print("  LOGIN CREDENTIALS")
    print(f"  ─────────────────────────────────────────────────")
    for email, info in user_ids.items():
        pw = EXEC_PASSWORD if info["role"] == "executive" else MEMBER_PASSWORD
        print(f"  [{info['role']:12s}] {email}  /  {pw}")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  Calls submitted for analysis: {submitted}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
