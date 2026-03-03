#!/usr/bin/env python3
"""
Test script: Fetch one record from each ServiceTitan export API
and POST them to the local Otto server to test ingestion.

Usage:
  1. Set environment variables (or edit the CONFIG section below)
  2. Make sure your Otto server is running (uvicorn app.main:app --reload --port 8001)
  3. Run: python test_st_ingestion.py

Required env vars:
  ST_TENANT_ID, ST_CLIENT_ID, ST_CLIENT_SECRET, ST_APP_KEY

Optional:
  ST_ENV          - "production" or "integration" (default: integration)
  SERVER_URL      - Otto server base URL (default: http://localhost:8001)
  ST_WORKER_SECRET - Shared secret for webhook auth header
"""

import asyncio
import json
import os
import sys

import httpx

# ── CONFIG ──────────────────────────────────────────────────────────────
TENANT_ID = 2593347861
CLIENT_ID = "cid.dxk17u2vdjivnb1uxmwma0wiu"
CLIENT_SECRET = "cs1.ohh63eu6a565bzy5c61hjpsf05566k3wt59msurmf1svvs6sn5"
APP_KEY = "ak1.y6as8uzrv9cg4fuefx5rckxa9"
ENV = "production"

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8001")
WORKER_SECRET = "st_live_rsqeTR7pJfaiOKpl7YKpT2Fhb546bCc1"

# ── AUTH / API URLS ─────────────────────────────────────────────────────
AUTH_URLS = {
    "production": "https://auth.servicetitan.io/connect/token",
    "integration": "https://auth-integration.servicetitan.io/connect/token",
}
API_BASES = {
    "production": "https://api.servicetitan.io",
    "integration": "https://api-integration.servicetitan.io",
}


async def get_token(client: httpx.AsyncClient) -> str:
    """Fetch an OAuth2 access token via client_credentials grant."""
    resp = await client.post(
        AUTH_URLS[ENV],
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json",
    }


async def fetch_export_page(
    client: httpx.AsyncClient, token: str, path: str, cursor: str | None = None,
) -> dict:
    """Fetch one page from an export endpoint. Returns the raw response body."""
    url = f"{API_BASES[ENV]}{path}"
    params = {}
    if cursor:
        params["from"] = cursor
    resp = await client.get(url, headers=auth_headers(token), params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


async def collect_all_records(
    client: httpx.AsyncClient, token: str, path: str,
    label: str = "record", max_pages: int = 50,
) -> list[dict]:
    """Page through an entire export feed and return all records."""
    all_records: list[dict] = []
    cursor = None
    pages = 0
    while pages < max_pages:
        body = await fetch_export_page(client, token, path, cursor)
        cursor = body.get("continueFrom")
        records = body.get("data", [])
        all_records.extend(records)
        pages += 1
        if not body.get("hasMore", False):
            break
    print(f"  {label}: collected {len(all_records)} records across {pages} page(s)")
    return all_records


def pick_populated(records: list[dict], required_fields: list[str]) -> dict | None:
    """Return the first record where all required_fields are truthy."""
    for r in records:
        if all(r.get(f) for f in required_fields):
            return r
    return None


async def post_to_server(
    client: httpx.AsyncClient, endpoint: str, payload: dict,
) -> dict:
    """POST a payload to the Otto webhook endpoint and return the response."""
    url = f"{SERVER_URL}/api/v1/webhooks{endpoint}"
    headers = {"Content-Type": "application/json"}
    if WORKER_SECRET:
        headers["X-Worker-Secret"] = WORKER_SECRET
    resp = await client.post(url, json=payload, headers=headers, timeout=30)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return {"status_code": resp.status_code, "body": body}


def pp(obj: object) -> str:
    return json.dumps(obj, indent=2, default=str)


# ── MAIN ────────────────────────────────────────────────────────────────

async def main():
    # Validate required config
    missing = [
        name
        for name, val in [
            ("ST_TENANT_ID", TENANT_ID),
            ("ST_CLIENT_ID", CLIENT_ID),
            ("ST_CLIENT_SECRET", CLIENT_SECRET),
            ("ST_APP_KEY", APP_KEY),
        ]
        if not val
    ]
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    print(f"ServiceTitan env : {ENV}")
    print(f"Tenant ID        : {TENANT_ID}")
    print(f"Server URL       : {SERVER_URL}")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # ── Step 1: Authenticate ────────────────────────────────────
        print("\n[1/3] Authenticating with ServiceTitan...")
        token = await get_token(client)
        print("  OK - token acquired")

        # ── Step 2: Fetch one call with a recording + customer ──────
        print("\n[2/3] Fetching a call with recordingUrl + customer from export API...")
        all_calls = await collect_all_records(
            client, token,
            f"/telecom/v2/tenant/{TENANT_ID}/export/calls",
            label="calls",
        )
        call = pick_populated(all_calls, ["id", "from", "duration", "recordingUrl", "customer"])
        if call:
            cust = call.get("customer", {})
            print(f"  OK - call id={call.get('id')}, from={call.get('from')}, "
                  f"duration={call.get('duration')}")
            print(f"       customer.id={cust.get('id')}, customer.name={cust.get('name')}")
            print(f"       recordingUrl={call.get('recordingUrl')}")
            print(f"  Full record:\n{pp(call)}")
        else:
            print("  WARN - no calls with populated fields found in export feed")

        # ── Step 3: POST call to server (server enriches CRM data) ──
        print("\n[3/3] Sending call to Otto server...")
        print("  (server will fetch full customer, contacts, and leads from ST API)")

        if call:
            calls_payload = {
                "tenant_id": TENANT_ID,
                "calls": [call],
                "poll_timestamp": "2026-03-03T00:00:00Z",
            }
            print(f"\n  -> POST {SERVER_URL}/api/v1/webhooks/servicetitan/calls")
            result = await post_to_server(client, "/servicetitan/calls", calls_payload)
            print(f"     Status  : {result['status_code']}")
            print(f"     Response: {pp(result['body'])}")
        else:
            print("\n  Skipping — no call data fetched")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
