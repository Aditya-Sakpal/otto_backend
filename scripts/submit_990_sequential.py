"""
Submit the 990 pending calls to Shunya sequentially with rate limiting + retries,
then poll for completion and fire local webhooks.

Uses sequential submission (not concurrent) to avoid overwhelming Shunya.
Resumes from where it left off — only submits calls not yet in call_processing_jobs.

Run:  python scripts/submit_990_sequential.py
"""
import asyncio
import json
import time

import httpx
import psycopg2

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
NEW_COMPANY_ID    = "689202f5-43cb-4b4a-8e03-928c364beb8d"
SHUNYA_BASE_URL   = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY    = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
LOCAL_WEBHOOK_URL = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"

CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]
SHUNYA_HEADERS = {
    "X-API-Key": SHUNYA_API_KEY,
    "Content-Type": "application/json",
    "X-Company-Id": NEW_COMPANY_ID,
}

SUBMIT_DELAY   = 0.4   # seconds between submissions
MAX_RETRIES    = 5     # per call
RETRY_BACKOFF  = [2, 4, 8, 16, 30]  # seconds


def fetch_pending_calls():
    """Return calls that don't yet have a call_processing_job entry."""
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT c.id, c.audio_url, c.phone_number, c.answered_at, c.duration_seconds
        FROM calls c
        WHERE c.company_id = %s
          AND c.audio_url IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM call_processing_jobs j
              WHERE j.call_id = c.id AND j.company_id = c.company_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM call_analyses a WHERE a.call_id = c.id
          )
        ORDER BY c.answered_at
    """, (NEW_COMPANY_ID,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


async def submit_one(client: httpx.AsyncClient, idx: int, call: dict) -> dict | None:
    agent = CSR_AGENTS[idx % len(CSR_AGENTS)]
    call_date = call["answered_at"]
    if hasattr(call_date, "isoformat"):
        call_date = call_date.isoformat()

    payload = {
        "call_id":      str(call["id"]),
        "company_id":   NEW_COMPANY_ID,
        "audio_url":    call["audio_url"],
        "phone_number": call["phone_number"] or "0000000000",
        "duration":     call["duration_seconds"] or 60,
        "call_date":    call_date or "2026-02-02T00:00:00Z",
        "metadata": {
            "agent": {"id": agent["id"], "name": agent["name"]},
            "call_type": "csr_call",
        },
        "options": {"priority": "normal"},
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(
                f"{SHUNYA_BASE_URL}/api/v1/call-processing/process",
                json=payload,
                headers=SHUNYA_HEADERS,
                timeout=30.0,
            )
            if resp.status_code in (200, 202):
                data = resp.json()
                return {"call_id": str(call["id"]), "job_id": data["job_id"]}
            elif resp.status_code in (429, 500, 502, 503):
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF)-1)]
                print(f"  [{idx+1}] HTTP {resp.status_code} - retry {attempt+1}/{MAX_RETRIES} in {wait}s")
                await asyncio.sleep(wait)
            elif resp.status_code == 409:
                # Already exists - fire webhook directly
                data = resp.json()
                call_id_str = str(call["id"])
                return {"call_id": call_id_str, "job_id": call_id_str}
            else:
                print(f"  [{idx+1}] FAIL HTTP {resp.status_code}: {resp.text[:150]}")
                return None
        except Exception as e:
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF)-1)]
            print(f"  [{idx+1}] ERR {e} - retry {attempt+1}/{MAX_RETRIES} in {wait}s")
            await asyncio.sleep(wait)
    return None


async def poll_batch(client: httpx.AsyncClient, pending_jobs: dict) -> list[dict]:
    """Poll a batch of jobs. Returns newly completed jobs."""
    done = []
    CONCURRENCY = 15
    sem = asyncio.Semaphore(CONCURRENCY)

    async def check(job_id):
        async with sem:
            try:
                resp = await client.get(
                    f"{SHUNYA_BASE_URL}/api/v1/call-processing/status/{job_id}",
                    headers=SHUNYA_HEADERS,
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return job_id, resp.json().get("status", "pending")
            except Exception:
                pass
            return job_id, "pending"

    results = await asyncio.gather(*[check(j) for j in list(pending_jobs.keys())])
    for job_id, status in results:
        if status in ("completed", "failed"):
            done.append(pending_jobs[job_id])
    return done


async def fire_webhooks(client: httpx.AsyncClient, jobs: list[dict]) -> tuple[int,int]:
    ok = fail = 0
    CONCURRENCY = 8
    sem = asyncio.Semaphore(CONCURRENCY)

    async def fire(job):
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

    results = await asyncio.gather(*[fire(j) for j in jobs])
    for success in results:
        if success: ok += 1
        else: fail += 1
    return ok, fail


async def main():
    t0 = time.time()
    print("=" * 65)
    print(f" Sequential Submit: 990 pending calls -> {NEW_COMPANY_ID}")
    print("=" * 65)

    calls = fetch_pending_calls()
    print(f"Pending calls to submit: {len(calls)}")
    if not calls:
        print("All calls already submitted or analysed.")
        return

    # ── Submit sequentially ───────────────────────────────────────────────────
    print(f"\n[1/3] Submitting {len(calls)} calls (sequential, {SUBMIT_DELAY}s delay)…")
    submitted_jobs: dict[str, dict] = {}   # job_id -> {call_id, job_id}
    submitted_ok = 0
    failed_submit = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, call in enumerate(calls):
            job = await submit_one(client, i, call)
            if job:
                submitted_jobs[job["job_id"]] = job
                submitted_ok += 1
            else:
                failed_submit += 1

            if (i + 1) % 50 == 0:
                elapsed = int(time.time() - t0)
                print(
                    f"  Progress {i+1}/{len(calls)}"
                    f"  ok={submitted_ok}  fail={failed_submit}"
                    f"  elapsed={elapsed//60}m{elapsed%60}s"
                )
            await asyncio.sleep(SUBMIT_DELAY)

    print(f"  Submission done: ok={submitted_ok}  fail={failed_submit}")

    if not submitted_jobs:
        print("Nothing queued — exiting.")
        return

    # ── Poll until all complete ───────────────────────────────────────────────
    print(f"\n[2/3] Polling {len(submitted_jobs)} jobs…")
    pending  = dict(submitted_jobs)
    all_done = []
    MAX_ROUNDS, POLL_INTERVAL = 90, 20  # 30 min max

    async with httpx.AsyncClient(timeout=20.0) as client:
        for rnd in range(1, MAX_ROUNDS + 1):
            await asyncio.sleep(POLL_INTERVAL)
            newly_done = await poll_batch(client, pending)

            for job in newly_done:
                del pending[job["job_id"]]
                all_done.append(job)

            elapsed = int(time.time() - t0)
            print(
                f"  Poll {rnd:3d}: done={len(all_done):4d}"
                f"  pending={len(pending):4d}"
                f"  elapsed={elapsed//60}m{elapsed%60}s"
            )
            if not pending:
                break

    if pending:
        print(f"  Timeout: adding {len(pending)} remaining to webhook queue")
        all_done.extend(pending.values())

    # ── Fire webhooks ─────────────────────────────────────────────────────────
    print(f"\n[3/3] Firing {len(all_done)} webhooks…")
    async with httpx.AsyncClient(timeout=60.0) as client:
        wh_ok, wh_fail = await fire_webhooks(client, all_done)
    print(f"  Webhooks: ok={wh_ok}  fail={wh_fail}")

    # ── Final counts ──────────────────────────────────────────────────────────
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM calls         WHERE company_id=%s) AS calls,
          (SELECT COUNT(*) FROM call_analyses WHERE company_id=%s) AS analyses,
          (SELECT COUNT(*) FROM contact_cards WHERE company_id=%s) AS contacts
    """, (NEW_COMPANY_ID,)*3)
    row = cur.fetchone()
    conn.close()

    elapsed = int(time.time() - t0)
    print(f"\n{'='*65}")
    print(f" DONE in {elapsed//60}m{elapsed%60}s")
    print(f"{'='*65}")
    print(f"  Total calls        : {row[0]}")
    print(f"  call_analyses      : {row[1]}")
    print(f"  contact_cards      : {row[2]}")
    print(f"  Submit ok/fail     : {submitted_ok}/{failed_submit}")
    print(f"  Webhooks ok/fail   : {wh_ok}/{wh_fail}")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())
