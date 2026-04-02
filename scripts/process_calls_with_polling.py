"""
Full pipeline script:
1. Submit 100 calls directly to Shunya (track job_ids)
2. Poll each job until complete
3. Manually fire the local webhook endpoint so call_analyses gets populated

Run:  python scripts/process_calls_with_polling.py
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

SHUNYA_BASE_URL    = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY     = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
LOCAL_WEBHOOK_URL  = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
NEW_COMPANY_ID     = "689202f5-43cb-4b4a-8e03-928c364beb8d"

CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]

SHUNYA_HEADERS = {
    "X-API-Key":     SHUNYA_API_KEY,
    "Content-Type":  "application/json",
    "X-Company-Id":  NEW_COMPANY_ID,
}


# ─── Fetch calls from DB ──────────────────────────────────────────────────────
def fetch_calls():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, audio_url, phone_number, answered_at, duration_seconds
        FROM calls
        WHERE company_id = %s AND audio_url IS NOT NULL
        ORDER BY answered_at
        LIMIT 100
    """, (NEW_COMPANY_ID,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


# ─── Submit a single call to Shunya ──────────────────────────────────────────
async def submit_one(client: httpx.AsyncClient, call: dict, agent: dict) -> dict | None:
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
        "options": {"allow_reprocess": True, "priority": "normal"},
    }
    try:
        resp = await client.post(
            f"{SHUNYA_BASE_URL}/api/v1/call-processing/process",
            json=payload,
            headers=SHUNYA_HEADERS,
        )
        if resp.status_code in (200, 202):
            data = resp.json()
            return {"call_id": str(call["id"]), "job_id": data["job_id"]}
        else:
            print(f"  SUBMIT FAIL [{call['id']}] HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  SUBMIT FAIL [{call['id']}] {e}")
        return None


# ─── Poll single job status ───────────────────────────────────────────────────
async def poll_job(client: httpx.AsyncClient, job_id: str) -> str:
    """Returns 'completed', 'failed', or 'pending'."""
    try:
        resp = await client.get(
            f"{SHUNYA_BASE_URL}/api/v1/call-processing/status/{job_id}",
            headers=SHUNYA_HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status", "pending")
        return "pending"
    except Exception:
        return "pending"


# ─── Fire local webhook ───────────────────────────────────────────────────────
async def fire_webhook(client: httpx.AsyncClient, call_id: str, job_id: str) -> bool:
    payload = {
        "status":     "completed",
        "job_id":     job_id,
        "call_id":    call_id,
        "company_id": NEW_COMPANY_ID,
        "event_type": "call_processing",
    }
    try:
        resp = await client.post(LOCAL_WEBHOOK_URL, json=payload)
        if resp.status_code == 200:
            return True
        print(f"  WEBHOOK FAIL [{call_id}] HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as e:
        print(f"  WEBHOOK FAIL [{call_id}] {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print(" Call Processing Pipeline (Direct Shunya + Local Webhook)")
    print("=" * 60)

    calls = fetch_calls()
    print(f"Loaded {len(calls)} calls from DB\n")

    # ── Step 1: Submit all to Shunya ─────────────────────────────────────────
    print("[1/3] Submitting calls to Shunya…")
    jobs: list[dict] = []  # [{call_id, job_id}]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, call in enumerate(calls):
            agent = CSR_AGENTS[i % len(CSR_AGENTS)]
            job = await submit_one(client, call, agent)
            if job:
                jobs.append(job)
            if (i + 1) % 10 == 0:
                print(f"  Submitted {i+1}/{len(calls)}  queued={len(jobs)}")
            await asyncio.sleep(0.3)

    print(f"  Total queued: {len(jobs)}/{len(calls)}\n")

    if not jobs:
        print("No jobs submitted — aborting.")
        return

    # ── Step 2: Poll for completion ───────────────────────────────────────────
    print("[2/3] Polling for job completion…")

    pending  = {j["job_id"]: j for j in jobs}
    done     = []
    poll_n   = 0
    MAX_POLLS = 60   # ~15 minutes (15s interval)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while pending and poll_n < MAX_POLLS:
            poll_n += 1
            await asyncio.sleep(15)

            newly_done = []
            for job_id, job_info in list(pending.items()):
                status = await poll_job(client, job_id)
                if status in ("completed", "failed"):
                    newly_done.append((job_id, status, job_info["call_id"]))
                await asyncio.sleep(0.1)

            for job_id, status, call_id in newly_done:
                del pending[job_id]
                if status == "completed":
                    done.append({"call_id": call_id, "job_id": job_id})
                else:
                    print(f"  Job FAILED: {job_id} (call {call_id})")

            print(
                f"  Poll {poll_n}: completed={len(done)}, "
                f"still_pending={len(pending)}, "
                f"elapsed~{poll_n * 15}s"
            )

            if not pending:
                break

    if pending:
        print(f"  Timed out with {len(pending)} jobs still pending")
        # Add them anyway to try the webhook
        for job_id, job_info in pending.items():
            done.append({"call_id": job_info["call_id"], "job_id": job_id})

    print(f"  Jobs ready for webhook: {len(done)}\n")

    # ── Step 3: Fire local webhook ────────────────────────────────────────────
    print("[3/3] Firing local webhook for each completed job…")

    webhook_ok   = 0
    webhook_fail = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, job in enumerate(done):
            ok = await fire_webhook(client, job["call_id"], job["job_id"])
            if ok:
                webhook_ok += 1
            else:
                webhook_fail += 1
            if (i + 1) % 10 == 0:
                print(f"  Webhooks fired: {i+1}  ok={webhook_ok}  fail={webhook_fail}")
            await asyncio.sleep(0.5)

    print(f"\n  Webhook final: ok={webhook_ok}  fail={webhook_fail}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Submitted:      {len(jobs)}")
    print(f"  Completed:      {len(done)}")
    print(f"  Webhook ok:     {webhook_ok}")
    print(f"  Webhook fail:   {webhook_fail}")
    print()
    print("  check call_analyses with:")
    print(f"    SELECT COUNT(*) FROM call_analyses WHERE company_id='{NEW_COMPANY_ID}';")


if __name__ == "__main__":
    asyncio.run(main())
