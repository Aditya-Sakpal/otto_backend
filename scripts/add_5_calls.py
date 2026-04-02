"""
Add 5 new calls from source company, submit to Shunya, fire webhooks, print objections.
"""
import asyncio
import time
import uuid
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
OLD_COMPANY  = "6d40b509-82bc-4d21-9614-de91cc25dc1b"
NEW_COMPANY  = "689202f5-43cb-4b4a-8e03-928c364beb8d"
SHUNYA_URL   = "https://ottoai.shunyalabs.ai"
SHUNYA_KEY   = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
WEBHOOK_URL  = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
SHUNYA_HEADERS = {
    "X-API-Key": SHUNYA_KEY,
    "Content-Type": "application/json",
    "X-Company-Id": NEW_COMPANY,
}

CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]


def get_source_calls(conn, limit=5):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, audio_url, phone_number, answered_at, duration_seconds, call_type
        FROM calls
        WHERE company_id = %s
          AND audio_url IS NOT NULL
          AND audio_url NOT IN (
              SELECT audio_url FROM calls WHERE company_id = %s AND audio_url IS NOT NULL
          )
        ORDER BY answered_at
        LIMIT %s
    """, (OLD_COMPANY, NEW_COMPANY, limit))
    return cur.fetchall()


def insert_calls(conn, source_calls):
    cur = conn.cursor()
    new_calls = []
    for i, sc in enumerate(source_calls):
        call_id = str(uuid.uuid4())
        contact_id = str(uuid.uuid4())
        agent = CSR_AGENTS[i % len(CSR_AGENTS)]
        phone = sc["phone_number"] or f"555000{i:04d}"

        cur.execute("""
            INSERT INTO contact_cards (id, company_id, primary_phone, first_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (contact_id, NEW_COMPANY, phone, f"Customer_{i+1}"))

        cur.execute("""
            INSERT INTO calls (
                id, company_id, contact_card_id, audio_url,
                phone_number, call_type, missed_call, answered_at, duration_seconds,
                status, extra_metadata, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, false, %s, %s,
                'completed', %s, NOW(), NOW()
            )
        """, (
            call_id, NEW_COMPANY, contact_id,
            sc["audio_url"],
            phone, sc.get("call_type", "inbound"),
            sc["answered_at"], sc.get("duration_seconds", 60),
            '{"agent": {"id": "' + agent["id"] + '", "name": "' + agent["name"] + '"}, "call_type": "csr_call"}',
        ))

        new_calls.append({
            "call_id": call_id,
            "audio_url": sc["audio_url"],
            "phone": phone,
            "answered_at": sc["answered_at"],
            "duration": sc.get("duration_seconds", 60),
            "agent": agent,
        })

    conn.commit()
    return new_calls


async def submit_and_process(calls):
    job_map = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n[1/3] Submitting to Shunya...")
        for i, c in enumerate(calls):
            call_date = c["answered_at"]
            if hasattr(call_date, "isoformat"):
                call_date = call_date.isoformat()

            payload = {
                "call_id":     c["call_id"],
                "company_id":  NEW_COMPANY,
                "audio_url":   c["audio_url"],
                "phone_number": c["phone"],
                "duration":    c["duration"] or 60,
                "call_date":   call_date,
                "allow_reprocess": True,
                "metadata": {
                    "agent": {"id": c["agent"]["id"], "name": c["agent"]["name"]},
                    "call_type": "csr_call",
                },
                "options": {"priority": "normal"},
            }
            resp = await client.post(
                f"{SHUNYA_URL}/api/v1/call-processing/process",
                json=payload, headers=SHUNYA_HEADERS,
            )
            if resp.status_code in (200, 202):
                data = resp.json()
                job_map[data["job_id"]] = c["call_id"]
                print(f"  [{i+1}] Submitted: job={data['job_id'][:8]}... call={c['call_id'][:8]}...")
            else:
                print(f"  [{i+1}] FAIL: {resp.status_code} {resp.text[:100]}")
            await asyncio.sleep(0.5)

        if not job_map:
            print("No jobs submitted!")
            return []

        # Poll
        print(f"\n[2/3] Polling {len(job_map)} jobs...")
        completed_jobs = []
        pending = dict(job_map)
        for rnd in range(1, 91):
            await asyncio.sleep(20)
            for job_id in list(pending.keys()):
                try:
                    resp = await client.get(
                        f"{SHUNYA_URL}/api/v1/call-processing/status/{job_id}",
                        headers=SHUNYA_HEADERS, timeout=15.0,
                    )
                    if resp.status_code == 200:
                        status = resp.json().get("status", "pending")
                        if status in ("completed", "failed"):
                            completed_jobs.append({"job_id": job_id, "call_id": pending.pop(job_id)})
                            print(f"  Job {job_id[:8]}... -> {status}")
                except Exception:
                    pass
            if not pending:
                break
            print(f"  Poll {rnd}: {len(completed_jobs)} done, {len(pending)} pending")

        for jid, cid in pending.items():
            completed_jobs.append({"job_id": jid, "call_id": cid})

        # Fire webhooks
        print(f"\n[3/3] Firing {len(completed_jobs)} webhooks...")
        call_ids = []
        for job in completed_jobs:
            payload = {
                "status":     "completed",
                "job_id":     job["job_id"],
                "call_id":    job["call_id"],
                "company_id": NEW_COMPANY,
                "event_type": "call_processing",
            }
            resp = await client.post(WEBHOOK_URL, json=payload, timeout=90.0)
            status = "OK" if resp.status_code == 200 else f"FAIL({resp.status_code})"
            print(f"  Webhook {job['call_id'][:8]}... -> {status}")
            if resp.status_code == 200:
                call_ids.append(job["call_id"])
            await asyncio.sleep(0.5)

    return call_ids


def print_objections(conn, call_ids):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    print("\n" + "=" * 70)
    print(" OBJECTIONS FROM 5 NEW CALLS")
    print("=" * 70)

    for cid in call_ids:
        cur.execute("""
            SELECT ca.objections, ca.objection_texts, ca.status,
                   ca.qualification_status, ca.booking_status,
                   c.phone_number, c.answered_at
            FROM call_analyses ca
            JOIN calls c ON c.id = ca.call_id
            WHERE ca.call_id = %s
        """, (cid,))
        row = cur.fetchone()
        if row:
            print(f"\nCall ID: {cid}")
            print(f"  Phone: {row['phone_number']}")
            print(f"  Date:  {row['answered_at']}")
            print(f"  Status: {row['status']}")
            print(f"  Qualification: {row['qualification_status']}")
            print(f"  Booking: {row['booking_status']}")
            print(f"  Objections: {row['objections']}")
            print(f"  Objection Texts: {row['objection_texts']}")
        else:
            print(f"\nCall ID: {cid} -- NO ANALYSIS FOUND")

    # Summary
    print("\n" + "=" * 70)
    cur.execute("""
        SELECT (SELECT COUNT(*) FROM calls WHERE company_id=%s) AS total_calls,
               (SELECT COUNT(*) FROM call_analyses WHERE company_id=%s) AS total_analyses
    """, (NEW_COMPANY, NEW_COMPANY))
    r = cur.fetchone()
    print(f" TOTALS: {r['total_calls']} calls, {r['total_analyses']} analyses")
    print("=" * 70)


async def main():
    t0 = time.time()
    conn = psycopg2.connect(DB_URL)

    print("Fetching 5 source calls from old company...")
    source = get_source_calls(conn, 5)
    print(f"Found {len(source)} source calls")

    print("Inserting calls into new company...")
    new_calls = insert_calls(conn, source)
    print(f"Inserted {len(new_calls)} calls")
    conn.close()

    processed_ids = await submit_and_process(new_calls)

    conn = psycopg2.connect(DB_URL)
    print_objections(conn, processed_ids)
    conn.close()

    elapsed = int(time.time() - t0)
    print(f"\nDone in {elapsed//60}m{elapsed%60}s")


if __name__ == "__main__":
    asyncio.run(main())
