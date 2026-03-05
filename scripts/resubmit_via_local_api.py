"""
Re-submit the 100 calls via the local API at port 8005.
The local API sets the correct webhook_url so Shunya can push results back
and populate call_analyses.

Run:  python scripts/resubmit_via_local_api.py
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

LOCAL_API     = "http://localhost:8005"
NEW_COMPANY_ID = "689202f5-43cb-4b4a-8e03-928c364beb8d"

EXEC_EMAIL    = "admin@arizonaroofers-clone.com"
EXEC_PASSWORD = "AZRoofers@Admin2026"

CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]


def fetch_calls():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, audio_url, phone_number, answered_at, duration_seconds
        FROM calls
        WHERE company_id = %s
          AND audio_url IS NOT NULL
        ORDER BY answered_at
        LIMIT 100
    """, (NEW_COMPANY_ID,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


async def login(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{LOCAL_API}/api/v1/auth/login",
        json={"email": EXEC_EMAIL, "password": EXEC_PASSWORD},
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text[:300]}")
    token = resp.json().get("access_token")
    print(f"Logged in as {EXEC_EMAIL}  (token: {token[:20]}...)")
    return token


async def submit_calls(calls, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    submitted = 0
    failed    = 0
    BATCH     = 5
    DELAY     = 1.0

    async with httpx.AsyncClient(timeout=40.0) as client:
        for batch_start in range(0, len(calls), BATCH):
            batch = calls[batch_start : batch_start + BATCH]
            tasks = []

            for j, call in enumerate(batch):
                agent = CSR_AGENTS[(batch_start + j) % len(CSR_AGENTS)]
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
                        "agent": {
                            "id":   agent["id"],
                            "name": agent["name"],
                        },
                        "call_type": "csr_call",
                    },
                    "options": {
                        "allow_reprocess": True,
                        "priority": "normal",
                    },
                }
                tasks.append(client.post(
                    f"{LOCAL_API}/api/v1/call-processing/process",
                    json=payload,
                    headers=headers,
                ))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, res in enumerate(results):
                call_id = str(batch[idx]["id"])
                if isinstance(res, Exception):
                    print(f"  FAIL [{call_id}] {res}")
                    failed += 1
                elif res.status_code in (200, 202):
                    submitted += 1
                else:
                    print(f"  FAIL [{call_id}] HTTP {res.status_code}: {res.text[:300]}")
                    failed += 1

            total = batch_start + len(batch)
            print(f"  Batch {batch_start+1}-{total}:  ok={submitted}  fail={failed}")
            await asyncio.sleep(DELAY)

    return submitted, failed


async def main():
    print("=" * 60)
    print(f" Re-submitting calls via local API  {LOCAL_API}")
    print("=" * 60)

    calls = fetch_calls()
    print(f"Found {len(calls)} calls to submit")
    if not calls:
        print("Nothing to submit — exiting.")
        return

    async with httpx.AsyncClient(timeout=20.0) as client:
        token = await login(client)

    submitted, failed = await submit_calls(calls, token)

    print()
    print("=" * 60)
    print(f" DONE   submitted={submitted}   failed={failed}")
    print("=" * 60)
    print()
    print("Calls are now queued in Shunya with the correct webhook.")
    print("call_analyses will be populated as each job completes.")
    print()
    print("Monitor with:")
    print(f"  GET {LOCAL_API}/api/v1/call-processing/status/<job_id>")


if __name__ == "__main__":
    asyncio.run(main())
