"""
Fire local webhooks for all calls that don't yet have a call_analysis.
Calls are already completed on Shunya — just need to trigger the webhook handler.

Run: python scripts/fire_webhooks_993.py
"""
import asyncio
import time
import httpx
import psycopg2

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)
COMPANY_ID        = "689202f5-43cb-4b4a-8e03-928c364beb8d"
LOCAL_WEBHOOK_URL = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
CONCURRENCY       = 5
DELAY             = 0.3  # seconds between batches


def fetch_pending_call_ids() -> list[str]:
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT c.id FROM calls c
        WHERE c.company_id = %s
          AND NOT EXISTS (SELECT 1 FROM call_analyses a WHERE a.call_id = c.id)
        ORDER BY c.answered_at
    """, (COMPANY_ID,))
    ids = [str(r[0]) for r in cur.fetchall()]
    conn.close()
    return ids


async def fire_webhook(client: httpx.AsyncClient, call_id: str) -> bool:
    payload = {
        "status":     "completed",
        "job_id":     call_id,
        "call_id":    call_id,
        "company_id": COMPANY_ID,
        "event_type": "call_processing",
    }
    try:
        resp = await client.post(LOCAL_WEBHOOK_URL, json=payload, timeout=90.0)
        return resp.status_code == 200
    except Exception as e:
        print(f"  ERR [{call_id[:8]}] {e}")
        return False


async def main():
    t0 = time.time()
    print("=" * 60)
    print(f" Firing webhooks for calls missing analyses")
    print(f" Company: {COMPANY_ID}")
    print("=" * 60)

    call_ids = fetch_pending_call_ids()
    print(f"Calls without analysis: {len(call_ids)}\n")

    if not call_ids:
        print("Nothing to do.")
        return

    ok = fail = 0
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_fire(client, call_id):
        async with sem:
            result = await fire_webhook(client, call_id)
            await asyncio.sleep(DELAY)
            return result

    async with httpx.AsyncClient(timeout=90.0) as client:
        for batch_start in range(0, len(call_ids), 50):
            batch = call_ids[batch_start:batch_start + 50]
            results = await asyncio.gather(*[bounded_fire(client, cid) for cid in batch])
            for success in results:
                if success: ok += 1
                else: fail += 1

            elapsed = int(time.time() - t0)
            done = batch_start + len(batch)
            print(
                f"  Progress {done}/{len(call_ids)}"
                f"  ok={ok}  fail={fail}"
                f"  elapsed={elapsed//60}m{elapsed%60}s"
            )

    # Final DB counts
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM calls         WHERE company_id=%s) AS calls,
          (SELECT COUNT(*) FROM call_analyses WHERE company_id=%s) AS analyses,
          (SELECT COUNT(*) FROM contact_cards WHERE company_id=%s) AS contacts
    """, (COMPANY_ID,)*3)
    row = cur.fetchone()
    conn.close()

    elapsed = int(time.time() - t0)
    print(f"\n{'='*60}")
    print(f" DONE in {elapsed//60}m{elapsed%60}s")
    print(f"{'='*60}")
    print(f"  Total calls    : {row[0]}")
    print(f"  call_analyses  : {row[1]}")
    print(f"  contact_cards  : {row[2]}")
    print(f"  Webhooks ok    : {ok}  fail={fail}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
