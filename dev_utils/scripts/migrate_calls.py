"""
Migrate calls from old company to new company by re-triggering CTM webhooks.

Reads raw CTM payloads from exported JSONL, replaces audio URL with S3 URL,
and POSTs to the staging CTM webhook endpoint. Retries on 503 errors.
"""
import json
import time
import httpx

STAGING_URL = "https://otto-backend-stage-8040383b5e71.herokuapp.com"
WEBHOOK_ENDPOINT = f"{STAGING_URL}/api/v1/webhooks/ctm/calls"
INPUT_FILE = "ctm_calls_all.jsonl"
DELAY_BETWEEN_CALLS = 1  # seconds between webhook calls
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries


def send_webhook(raw_payload, attempt=1):
    """Send a single webhook with retry on 503."""
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            WEBHOOK_ENDPOINT,
            json=raw_payload,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 200:
            return True, response.json()
        elif response.status_code == 503 and attempt < MAX_RETRIES:
            print(f"  -> 503, retrying in {RETRY_DELAY}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
            return send_webhook(raw_payload, attempt + 1)
        else:
            return False, f"{response.status_code}: {response.text[:200]}"


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Total calls to migrate: {len(lines)}")

    success = 0
    failed = 0
    skipped = 0
    failed_ids = []

    for i, line in enumerate(lines):
        data = json.loads(line.strip())
        raw_payload = data.get("raw_payload")
        s3_audio_url = data.get("audio_url")
        old_call_id = data.get("call_id")

        if not raw_payload:
            print(f"[{i+1}] SKIP - No raw payload for call {old_call_id}")
            skipped += 1
            continue

        # Replace audio URL with S3 URL (CTM URLs need auth and may expire)
        if s3_audio_url:
            raw_payload["audio"] = s3_audio_url

        ctm_call_id = raw_payload.get("id")
        name = raw_payload.get("name", "Unknown")
        status_val = raw_payload.get("status", "unknown")
        direction = raw_payload.get("direction", "unknown")
        caller = raw_payload.get("caller_number_bare") or raw_payload.get("caller_number", "unknown")

        print(f"[{i+1}/{len(lines)}] CTM {ctm_call_id} - {name} ({caller}) [{status_val}/{direction}]", end=" ", flush=True)

        try:
            ok, result = send_webhook(raw_payload)
            if ok:
                print(f"OK -> {result.get('call_id')}")
                success += 1
            else:
                print(f"FAIL -> {result}")
                failed += 1
                failed_ids.append(ctm_call_id)
        except Exception as e:
            print(f"ERROR -> {e}")
            failed += 1
            failed_ids.append(ctm_call_id)

        # Delay between calls
        if i < len(lines) - 1:
            time.sleep(DELAY_BETWEEN_CALLS)

        # Progress update every 100 calls
        if (i + 1) % 100 == 0:
            print(f"\n--- Progress: {i+1}/{len(lines)} | Success: {success} | Failed: {failed} ---\n")

    print(f"\n{'='*60}")
    print(f"MIGRATION COMPLETE")
    print(f"{'='*60}")
    print(f"Success: {success}")
    print(f"Failed:  {failed}")
    print(f"Skipped: {skipped}")
    print(f"Total:   {len(lines)}")
    if failed_ids:
        print(f"\nFailed CTM IDs: {failed_ids}")


if __name__ == "__main__":
    main()
