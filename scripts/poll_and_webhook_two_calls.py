"""
Poll two specific Shunya jobs until complete, then fire local webhook.
"""
import asyncio
import httpx

SHUNYA_BASE_URL   = "https://ottoai.shunyalabs.ai"
SHUNYA_API_KEY    = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
LOCAL_WEBHOOK_URL = "http://localhost:8005/api/v1/webhooks/shoonya/job-complete"
COMPANY_ID        = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"

JOBS = [
    {"job_id": "45f710e9-cce3-423d-b876-93fef265c509", "call_id": "9376d964-ec66-4e11-b5c8-06a6626415f9"},
    {"job_id": "35ec0f30-a4c0-4bc4-b801-be6933ffe9c5", "call_id": "9b45cc86-ca2a-4934-a903-b51a4c1e71c5"},
]

SHUNYA_HEADERS = {
    "X-API-Key": SHUNYA_API_KEY,
    "X-Company-Id": COMPANY_ID,
}


async def poll_until_done(client, job_id, max_wait=600, interval=15):
    for i in range(max_wait // interval):
        await asyncio.sleep(interval)
        try:
            resp = await client.get(
                f"{SHUNYA_BASE_URL}/api/v1/call-processing/status/{job_id}",
                headers=SHUNYA_HEADERS,
            )
            data = resp.json()
            status = data.get("status")
            pct = data.get("progress", {}).get("percent", 0)
            step = data.get("progress", {}).get("current_step", "")
            print(f"  [{job_id[:8]}] {status} {pct}% ({step})")
            if status in ("completed", "failed"):
                return status
        except Exception as e:
            print(f"  Poll error: {e}")
    return "timeout"


async def fire_webhook(client, call_id, job_id):
    payload = {
        "status":     "completed",
        "job_id":     job_id,
        "call_id":    call_id,
        "company_id": COMPANY_ID,
        "event_type": "call_processing",
    }
    resp = await client.post(LOCAL_WEBHOOK_URL, json=payload, timeout=60.0)
    if resp.status_code == 200:
        print(f"  Webhook OK [{call_id}]")
    else:
        print(f"  Webhook FAIL [{call_id}] HTTP {resp.status_code}: {resp.text[:300]}")


async def main():
    print("Polling 2 Shunya jobs…")
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [poll_until_done(client, j["job_id"]) for j in JOBS]
        statuses = await asyncio.gather(*tasks)

        for job, status in zip(JOBS, statuses):
            print(f"\nJob {job['job_id'][:8]} -> {status}")
            if status in ("completed", "timeout"):
                await fire_webhook(client, job["call_id"], job["job_id"])

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
