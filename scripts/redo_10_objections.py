"""
Reprocess 10 calls that had objections. Submit with allow_reprocess=true,
poll, fire webhooks, then print new objections side by side with old.
"""
import asyncio
import time
import json
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
COMPANY_ID   = "689202f5-43cb-4b4a-8e03-928c364beb8d"
SHUNYA_URL   = "https://ottoai.shunyalabs.ai"
SHUNYA_KEY   = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
WEBHOOK_URL  = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
SHUNYA_HEADERS = {
    "X-API-Key": SHUNYA_KEY,
    "Content-Type": "application/json",
    "X-Company-Id": COMPANY_ID,
}


def fetch_10_calls_with_objections(conn):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT ca.call_id, c.audio_url, c.phone_number, c.duration_seconds,
               ca.objections AS old_objections,
               ca.objection_texts AS old_objection_texts,
               ca.qualification_status AS old_qualification,
               ca.booking_status AS old_booking
        FROM call_analyses ca
        JOIN calls c ON c.id = ca.call_id
        WHERE ca.company_id = %s
          AND ca.objections IS NOT NULL
          AND array_length(ca.objections, 1) > 0
        ORDER BY c.answered_at
        LIMIT 10
    """, (COMPANY_ID,))
    return cur.fetchall()


async def reprocess(calls):
    job_map = {}  # job_id -> call_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Submit
        print("\n[1/3] Submitting 10 calls to Shunya (allow_reprocess=true)...")
        for i, c in enumerate(calls):
            payload = {
                "call_id":         str(c["call_id"]),
                "company_id":      COMPANY_ID,
                "audio_url":       c["audio_url"],
                "phone_number":    c["phone_number"] or "0000000000",
                "duration":        c["duration_seconds"] or 60,
                "call_date":       "2026-02-15T00:00:00Z",
                "allow_reprocess": True,
                "metadata": {
                    "agent": {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
                    "call_type": "csr_call",
                },
                "options": {"priority": "normal"},
            }
            for attempt in range(4):
                try:
                    resp = await client.post(
                        f"{SHUNYA_URL}/api/v1/call-processing/process",
                        json=payload, headers=SHUNYA_HEADERS,
                    )
                    if resp.status_code in (200, 202):
                        data = resp.json()
                        job_map[data["job_id"]] = str(c["call_id"])
                        print(f"  [{i+1}] Submitted: job={data['job_id'][:8]}...")
                        break
                    elif resp.status_code in (429, 500, 502, 503):
                        wait = [3, 6, 12, 24][min(attempt, 3)]
                        print(f"  [{i+1}] HTTP {resp.status_code}, retry in {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        print(f"  [{i+1}] FAIL: {resp.status_code} {resp.text[:80]}")
                        break
                except Exception as e:
                    wait = [3, 6, 12, 24][min(attempt, 3)]
                    print(f"  [{i+1}] ERR {e}, retry in {wait}s")
                    await asyncio.sleep(wait)
            await asyncio.sleep(0.5)

        if not job_map:
            print("No jobs submitted!")
            return []

        # Poll
        print(f"\n[2/3] Polling {len(job_map)} jobs...")
        completed = []
        pending = dict(job_map)
        for rnd in range(1, 91):
            await asyncio.sleep(20)
            for jid in list(pending.keys()):
                try:
                    resp = await client.get(
                        f"{SHUNYA_URL}/api/v1/call-processing/status/{jid}",
                        headers=SHUNYA_HEADERS, timeout=15.0,
                    )
                    if resp.status_code == 200:
                        st = resp.json().get("status", "pending")
                        if st in ("completed", "failed"):
                            completed.append({"job_id": jid, "call_id": pending.pop(jid)})
                            print(f"  Job {jid[:8]}... -> {st}")
                except Exception:
                    pass
            if not pending:
                break
            print(f"  Poll {rnd}: {len(completed)} done, {len(pending)} pending")

        for jid, cid in pending.items():
            completed.append({"job_id": jid, "call_id": cid})

        # Webhooks
        print(f"\n[3/3] Firing {len(completed)} webhooks...")
        ok_ids = []
        for job in completed:
            payload = {
                "status":     "completed",
                "job_id":     job["job_id"],
                "call_id":    job["call_id"],
                "company_id": COMPANY_ID,
                "event_type": "call_processing",
            }
            resp = await client.post(WEBHOOK_URL, json=payload, timeout=90.0)
            st = "OK" if resp.status_code == 200 else f"FAIL({resp.status_code})"
            print(f"  {job['call_id'][:8]}... -> {st}")
            if resp.status_code == 200:
                ok_ids.append(job["call_id"])
            await asyncio.sleep(0.5)

    return ok_ids


def compare_objections(conn, old_data, processed_ids):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    old_map = {str(c["call_id"]): c for c in old_data}

    print("\n" + "=" * 80)
    print(" OBJECTION COMPARISON: OLD vs NEW (after reprocessing)")
    print("=" * 80)

    for cid in processed_ids:
        cur.execute("""
            SELECT objections, objection_texts, qualification_status, booking_status
            FROM call_analyses WHERE call_id = %s
        """, (cid,))
        new = cur.fetchone()
        old = old_map.get(cid, {})

        print(f"\nCall ID: {cid}")
        print(f"  Phone: {old.get('phone_number', '?')}")
        print(f"  --- OLD ---")
        print(f"    Qualification: {old.get('old_qualification')}")
        print(f"    Booking:       {old.get('old_booking')}")
        print(f"    Objections:    {old.get('old_objections')}")
        print(f"    Texts:         {old.get('old_objection_texts')}")
        if new:
            print(f"  --- NEW ---")
            print(f"    Qualification: {new['qualification_status']}")
            print(f"    Booking:       {new['booking_status']}")
            print(f"    Objections:    {new['objections']}")
            print(f"    Texts:         {new['objection_texts']}")
        else:
            print(f"  --- NEW: NO ANALYSIS FOUND ---")


async def main():
    t0 = time.time()
    conn = psycopg2.connect(DB_URL)

    print("Fetching 10 calls with objections...")
    calls = fetch_10_calls_with_objections(conn)
    print(f"Found {len(calls)} calls with objections")
    for i, c in enumerate(calls):
        print(f"  [{i+1}] {c['call_id']} phone={c['phone_number']} objections={c['old_objections']}")
    conn.close()

    processed_ids = await reprocess(calls)

    conn = psycopg2.connect(DB_URL)
    compare_objections(conn, calls, processed_ids)
    conn.close()

    elapsed = int(time.time() - t0)
    print(f"\nDone in {elapsed//60}m{elapsed%60}s")


if __name__ == "__main__":
    asyncio.run(main())
