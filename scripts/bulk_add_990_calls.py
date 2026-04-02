"""
Bulk add 990 more calls to company 689202f5-43cb-4b4a-8e03-928c364beb8d.
Pipeline:
  Phase 1 - Insert 990 contact_cards + call records into DB
  Phase 2 - Submit all 990 to Shunya (direct, skip already-completed guard)
  Phase 3 - Poll Shunya in parallel until all complete
  Phase 4 - Fire local webhook for each completed call -> populates call_analyses

Run:  python scripts/bulk_add_990_calls.py
"""

import asyncio
import json
import time
import uuid as _uuid
from datetime import datetime, timezone

import httpx
import psycopg2
import psycopg2.extras

# ── config ───────────────────────────────────────────────────────────────────
DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
SOURCE_COMPANY_ID  = "6d40b509-82bc-4d21-9614-de91cc25dc1b"
NEW_COMPANY_ID     = "689202f5-43cb-4b4a-8e03-928c364beb8d"
SHUNYA_BASE_URL    = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY     = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
LOCAL_WEBHOOK_URL  = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
TARGET_NEW_CALLS   = 990
SOURCE_OFFSET      = 100   # skip the first 100 already used

CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]

SHUNYA_HEADERS = {
    "X-API-Key": SHUNYA_API_KEY,
    "Content-Type": "application/json",
    "X-Company-Id": NEW_COMPANY_ID,
}

# ── Phase 1: fetch source calls & insert into DB ──────────────────────────────
def phase1_insert_calls() -> list[dict]:
    """Fetch 990 source calls and insert contact_cards + calls. Returns new_calls list."""
    conn = psycopg2.connect(DB_URL)
    psycopg2.extras.register_uuid()
    cur = conn.cursor()

    # Pick CSR to handle calls
    csr_id = CSR_AGENTS[0]["id"]

    # Fetch source calls (offset past the first 100 already used)
    cur.execute("""
        SELECT id, audio_url, phone_number, created_at, duration_seconds
        FROM calls
        WHERE company_id = %s
          AND audio_url LIKE 'https://ottoaudio.s3%%'
          AND created_at >= '2026-02-02'
        ORDER BY created_at
        LIMIT %s OFFSET %s
    """, (SOURCE_COMPANY_ID, TARGET_NEW_CALLS, SOURCE_OFFSET))
    sources = cur.fetchall()
    src_cols = [d[0] for d in cur.description]
    source_calls = [dict(zip(src_cols, r)) for r in sources]
    print(f"  Fetched {len(source_calls)} source calls from DB")

    phone_to_cc: dict[str, str] = {}
    new_calls: list[dict] = []

    CHUNK = 50
    for batch_start in range(0, len(source_calls), CHUNK):
        batch = source_calls[batch_start : batch_start + CHUNK]

        for i, call in enumerate(batch):
            phone = call["phone_number"] or f"000{batch_start+i:07d}"

            # contact card
            if phone not in phone_to_cc:
                cc_id = str(_uuid.uuid4())
                cur.execute("""
                    INSERT INTO contact_cards (id, company_id, primary_phone)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """, (cc_id, NEW_COMPANY_ID, phone))
                row = cur.fetchone()
                phone_to_cc[phone] = str(row[0]) if row else cc_id
            cc_id = phone_to_cc[phone]

            new_call_id  = str(_uuid.uuid4())
            answered_at  = call["created_at"]
            duration     = call["duration_seconds"] or 60

            cur.execute("""
                INSERT INTO calls
                  (id, company_id, contact_card_id, phone_number, missed_call,
                   audio_url, duration_seconds, handled_by_user_id,
                   answered_at, call_type, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                new_call_id, NEW_COMPANY_ID, cc_id, phone, False,
                call["audio_url"], duration, csr_id,
                answered_at, "csr_call", "pending",
            ))

            call_date = answered_at.isoformat() if hasattr(answered_at, "isoformat") else str(answered_at)
            new_calls.append({
                "call_id":   new_call_id,
                "audio_url": call["audio_url"],
                "phone":     phone,
                "duration":  duration,
                "call_date": call_date,
            })

        conn.commit()
        done = min(batch_start + CHUNK, len(source_calls))
        print(f"  DB inserted {done}/{len(source_calls)}")

    cur.close()
    conn.close()
    return new_calls


# ── Phase 2: submit all to Shunya ─────────────────────────────────────────────
async def phase2_submit(new_calls: list[dict]) -> list[dict]:
    """Submit all calls to Shunya. Returns list of {call_id, job_id}."""
    jobs: list[dict] = []
    fail_count = 0
    CONCURRENCY = 10
    DELAY       = 0.2   # seconds between individual requests

    sem = asyncio.Semaphore(CONCURRENCY)

    async def submit_one(client, idx, call):
        agent = CSR_AGENTS[idx % len(CSR_AGENTS)]
        payload = {
            "call_id":      call["call_id"],
            "company_id":   NEW_COMPANY_ID,
            "audio_url":    call["audio_url"],
            "phone_number": call["phone"],
            "duration":     call["duration"],
            "call_date":    call["call_date"],
            "metadata": {
                "agent": {"id": agent["id"], "name": agent["name"]},
                "call_type": "csr_call",
            },
            "options": {"priority": "normal"},
        }
        async with sem:
            try:
                resp = await client.post(
                    f"{SHUNYA_BASE_URL}/api/v1/call-processing/process",
                    json=payload,
                    headers=SHUNYA_HEADERS,
                )
                if resp.status_code in (200, 202):
                    data = resp.json()
                    return {"call_id": call["call_id"], "job_id": data["job_id"]}
                else:
                    print(f"  SUBMIT FAIL [{call['call_id'][:8]}] HTTP {resp.status_code}: {resp.text[:150]}")
                    return None
            except Exception as e:
                print(f"  SUBMIT ERR [{call['call_id'][:8]}] {e}")
                return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [submit_one(client, i, call) for i, call in enumerate(new_calls)]
        results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            jobs.append(r)
        else:
            fail_count += 1

    print(f"  Submitted: {len(jobs)} ok, {fail_count} failed")
    return jobs


# ── Phase 3: poll all jobs until complete ─────────────────────────────────────
async def phase3_poll(jobs: list[dict]) -> list[dict]:
    """Poll until all jobs complete. Returns same list (all completed or timed-out)."""
    POLL_INTERVAL = 20    # seconds
    MAX_ROUNDS    = 60    # 20 min max
    CONCURRENCY   = 20

    pending: dict[str, dict] = {j["job_id"]: j for j in jobs}
    done:    list[dict]      = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async def check_one(client, job_id):
        async with sem:
            try:
                resp = await client.get(
                    f"{SHUNYA_BASE_URL}/api/v1/call-processing/status/{job_id}",
                    headers=SHUNYA_HEADERS,
                )
                if resp.status_code == 200:
                    return job_id, resp.json().get("status", "pending")
                return job_id, "pending"
            except Exception:
                return job_id, "pending"

    for rnd in range(1, MAX_ROUNDS + 1):
        await asyncio.sleep(POLL_INTERVAL)

        async with httpx.AsyncClient(timeout=30.0) as client:
            results = await asyncio.gather(
                *[check_one(client, jid) for jid in list(pending.keys())]
            )

        newly_done = [(jid, st) for jid, st in results if st in ("completed", "failed")]
        for jid, st in newly_done:
            job = pending.pop(jid)
            if st == "completed":
                done.append(job)
            else:
                print(f"  Job FAILED: {jid[:8]}")

        print(
            f"  Poll {rnd:2d}/{MAX_ROUNDS}: completed={len(done):4d}"
            f"  pending={len(pending):4d}  elapsed~{rnd*POLL_INTERVAL//60}m{rnd*POLL_INTERVAL%60}s"
        )
        if not pending:
            break

    if pending:
        print(f"  Timeout: adding {len(pending)} still-pending jobs to webhook queue")
        done.extend(pending.values())

    return done


# ── Phase 4: fire local webhooks ──────────────────────────────────────────────
async def phase4_webhooks(jobs: list[dict]) -> tuple[int, int]:
    CONCURRENCY = 10
    DELAY       = 0.1
    ok = 0
    fail = 0
    sem = asyncio.Semaphore(CONCURRENCY)

    async def fire(client, job):
        async with sem:
            payload = {
                "status":     "completed",
                "job_id":     job["job_id"],
                "call_id":    job["call_id"],
                "company_id": NEW_COMPANY_ID,
                "event_type": "call_processing",
            }
            try:
                resp = await client.post(LOCAL_WEBHOOK_URL, json=payload, timeout=60.0)
                return resp.status_code == 200
            except Exception as e:
                print(f"  WEBHOOK ERR [{job['call_id'][:8]}] {e}")
                return False

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks   = [fire(client, j) for j in jobs]
        results = await asyncio.gather(*tasks)

    for i, success in enumerate(results):
        if success:
            ok += 1
        else:
            fail += 1
        if (i + 1) % 100 == 0:
            print(f"  Webhooks fired: {i+1}/{len(jobs)}  ok={ok}  fail={fail}")

    return ok, fail


# ── verify DB state ───────────────────────────────────────────────────────────
def verify():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM calls         WHERE company_id=%s) AS calls,
          (SELECT COUNT(*) FROM call_analyses WHERE company_id=%s) AS analyses,
          (SELECT COUNT(*) FROM contact_cards WHERE company_id=%s) AS contacts,
          (SELECT COUNT(*) FROM leads         WHERE company_id=%s) AS leads
    """, (NEW_COMPANY_ID,)*4)
    row = cur.fetchone()
    conn.close()
    return dict(zip(["calls","analyses","contacts","leads"], row))


# ── main ──────────────────────────────────────────────────────────────────────
async def main():
    t0 = time.time()
    print("=" * 65)
    print(f" Bulk Add 990 Calls  ->  {NEW_COMPANY_ID}")
    print("=" * 65)

    # ── Phase 1 ──────────────────────────────────────────────────────────────
    print("\n[1/4] Inserting call records into DB…")
    new_calls = phase1_insert_calls()
    print(f"  Total inserted: {len(new_calls)}")

    if not new_calls:
        print("Nothing to do — exiting.")
        return

    # ── Phase 2 ──────────────────────────────────────────────────────────────
    print(f"\n[2/4] Submitting {len(new_calls)} calls to Shunya…")
    jobs = await phase2_submit(new_calls)
    print(f"  Jobs queued: {len(jobs)}")

    if not jobs:
        print("No jobs submitted — aborting.")
        return

    # ── Phase 3 ──────────────────────────────────────────────────────────────
    print(f"\n[3/4] Polling {len(jobs)} jobs for completion…")
    completed_jobs = await phase3_poll(jobs)
    print(f"  Ready for webhook: {len(completed_jobs)}")

    # ── Phase 4 ──────────────────────────────────────────────────────────────
    print(f"\n[4/4] Firing {len(completed_jobs)} webhooks to populate call_analyses…")
    ok, fail = await phase4_webhooks(completed_jobs)
    print(f"  Webhook ok={ok}  fail={fail}")

    # ── Summary ──────────────────────────────────────────────────────────────
    counts = verify()
    elapsed = int(time.time() - t0)
    print(f"\n{'='*65}")
    print(f" DONE in {elapsed//60}m{elapsed%60}s")
    print(f"{'='*65}")
    print(f"  calls         : {counts['calls']}")
    print(f"  call_analyses : {counts['analyses']}")
    print(f"  contact_cards : {counts['contacts']}")
    print(f"  leads         : {counts['leads']}")
    print(f"  webhooks ok   : {ok}  fail={fail}")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())
