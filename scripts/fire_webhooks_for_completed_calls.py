"""
All 100 calls are already 'completed' in Shunya.
This script fires the local webhook endpoint for each call_id
so the handler fetches the summary from Shunya and populates call_analyses.

Run:  python scripts/fire_webhooks_for_completed_calls.py
"""
import asyncio
import httpx
import psycopg2

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)

LOCAL_WEBHOOK_URL = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
NEW_COMPANY_ID    = "689202f5-43cb-4b4a-8e03-928c364beb8d"
SHUNYA_BASE_URL   = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY    = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"


def fetch_call_ids():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id FROM calls
        WHERE company_id = %s AND audio_url IS NOT NULL
        ORDER BY answered_at
        LIMIT 100
    """, (NEW_COMPANY_ID,))
    ids = [str(r[0]) for r in cur.fetchall()]
    conn.close()
    return ids


async def get_job_id_for_call(client: httpx.AsyncClient, call_id: str) -> str | None:
    """Try to get a job_id for this call from Shunya status endpoint."""
    try:
        resp = await client.get(
            f"{SHUNYA_BASE_URL}/api/v1/call-processing/status/{call_id}",
            headers={
                "X-API-Key":    SHUNYA_API_KEY,
                "X-Company-Id": NEW_COMPANY_ID,
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("job_id") or call_id
    except Exception:
        pass
    return call_id  # fallback: use call_id as job_id


async def fire_webhook(client: httpx.AsyncClient, call_id: str, job_id: str) -> bool:
    payload = {
        "status":     "completed",
        "job_id":     job_id,
        "call_id":    call_id,
        "company_id": NEW_COMPANY_ID,
        "event_type": "call_processing",
    }
    try:
        resp = await client.post(LOCAL_WEBHOOK_URL, json=payload, timeout=60.0)
        if resp.status_code == 200:
            return True
        print(f"  FAIL [{call_id}] HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as e:
        print(f"  FAIL [{call_id}] {e}")
        return False


async def main():
    print("=" * 60)
    print(" Firing webhooks for 100 already-completed Shunya calls")
    print("=" * 60)

    call_ids = fetch_call_ids()
    print(f"Loaded {len(call_ids)} call IDs from DB\n")

    ok = 0
    fail = 0
    DELAY = 0.5

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, call_id in enumerate(call_ids):
            # Use call_id as job_id (Shunya accepts this on the status endpoint)
            success = await fire_webhook(client, call_id, call_id)
            if success:
                ok += 1
            else:
                fail += 1

            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{len(call_ids)}  ok={ok}  fail={fail}")

            await asyncio.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f" DONE   ok={ok}   fail={fail}")
    print(f"{'='*60}")

    # Verify DB
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM call_analyses WHERE company_id=%s",
        (NEW_COMPANY_ID,)
    )
    count = cur.fetchone()[0]
    conn.close()
    print(f"\n call_analyses rows for new company: {count}")


if __name__ == "__main__":
    asyncio.run(main())
