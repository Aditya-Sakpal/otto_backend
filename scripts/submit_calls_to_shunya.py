"""
Submit the 100 pre-created calls of the new company to the Shunya API.
Run after setup_arizona_roofers_clone.py has already created the company/users/calls.
"""
import asyncio
import json
import sys

import httpx
import psycopg2
import psycopg2.extras

DB_URL = (
    "postgresql://u3us7scpstukqr:"
    "p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d"
    "@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com"
    ":5432/dcmep4gk3l4f2n"
)

SHUNYA_BASE_URL = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY  = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"

NEW_COMPANY_ID = "689202f5-43cb-4b4a-8e03-928c364beb8d"

# CSRs to cycle through as agent metadata
CSR_AGENTS = [
    {"id": "a8b450d6-d3c2-48b2-8be7-6f106bd4bde9", "name": "Maria Gonzalez"},
    {"id": "1cd61b81-071a-4db7-8a9b-291a91f70b81", "name": "James Parker"},
]


def fetch_calls(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, audio_url, phone_number, answered_at, duration_seconds
        FROM calls
        WHERE company_id = %s
          AND audio_url IS NOT NULL
          AND status = 'pending'
        ORDER BY answered_at
        LIMIT 100
    """, (NEW_COMPANY_ID,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    return [dict(zip(cols, r)) for r in rows]


async def submit_calls(calls):
    headers = {
        "X-API-Key": SHUNYA_API_KEY,
        "Content-Type": "application/json",
        "X-Company-Id": NEW_COMPANY_ID,
    }

    submitted = 0
    failed = 0
    BATCH = 5
    DELAY = 0.8

    async with httpx.AsyncClient(timeout=30.0) as client:
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
                        "call_type":       "csr_call",
                        "allow_reprocess": True,
                    },
                    "options": {"priority": "normal"},
                }
                tasks.append(client.post(
                    f"{SHUNYA_BASE_URL}/api/v1/call-processing/process",
                    json=payload,
                    headers=headers,
                ))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, res in enumerate(results):
                call_id = str(batch[idx]["id"])
                if isinstance(res, Exception):
                    print(f"  FAIL [{call_id}] Exception: {res}")
                    failed += 1
                elif res.status_code in (200, 202):
                    submitted += 1
                else:
                    body = res.text[:300] if res.text else ""
                    print(f"  FAIL [{call_id}] HTTP {res.status_code}: {body}")
                    failed += 1

            total = batch_start + len(batch)
            print(f"  Batch {batch_start+1}-{total}: ok={submitted}, fail={failed}")
            await asyncio.sleep(DELAY)

    return submitted, failed


async def main():
    print("=" * 60)
    print(f" Submitting calls for company {NEW_COMPANY_ID}")
    print("=" * 60)

    conn = psycopg2.connect(DB_URL)
    calls = fetch_calls(conn)
    conn.close()

    print(f"Found {len(calls)} pending calls to submit")
    if not calls:
        print("Nothing to submit.")
        return

    submitted, failed = await submit_calls(calls)

    print()
    print("=" * 60)
    print(f" DONE  submitted={submitted}  failed={failed}")
    print("=" * 60)
    print()
    print("LOGIN CREDENTIALS")
    print("-" * 40)
    print("Company ID :", NEW_COMPANY_ID)
    print()
    print("[executive]  admin@arizonaroofers-clone.com         / AZRoofers@Admin2026")
    print("[csr]        maria.gonzalez@arizonaroofers-clone.com / AZRoofers@Demo2026")
    print("[csr]        james.parker@arizonaroofers-clone.com   / AZRoofers@Demo2026")
    print("[sales_rep]  tyler.brooks@arizonaroofers-clone.com   / AZRoofers@Demo2026")
    print("[sales_rep]  ashley.chen@arizonaroofers-clone.com    / AZRoofers@Demo2026")
    print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
