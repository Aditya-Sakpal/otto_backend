"""Read-only API smoke test for local Otto server."""
import json
import sys
from datetime import date
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"
COMPANY_ID = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"

pass_count = fail_count = warn_count = 0
results: list[tuple[str, str, int | None, str]] = []


def req(method: str, path: str, token: str | None = None, body: dict | None = None, ok=(200,)):
    global pass_count, fail_count, warn_count
    url = f"{BASE}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            code = resp.getcode()
            status = "PASS" if code in ok else "WARN"
            if status == "PASS":
                pass_count += 1
            else:
                warn_count += 1
            results.append((status, path, code, ""))
            return code, resp.read()
    except urllib.error.HTTPError as e:
        code = e.code
        if code in ok:
            pass_count += 1
            results.append(("PASS", path, code, "expected"))
        else:
            fail_count += 1
            results.append(("FAIL", path, code, str(e.reason)))
        return code, None
    except Exception as e:
        fail_count += 1
        results.append(("FAIL", path, None, str(e)))
        return None, None


def main() -> int:
    # Public
    req("GET", "/health")
    req("GET", "/")
    req("GET", "/openapi.json")
    req("GET", "/docs", ok=(200,))

    # Auth
    _, raw = req(
        "POST",
        "/api/v1/auth/login",
        body={"email": "test@example.com", "password": "password123"},
        ok=(200,),
    )
    if not raw:
        print("FATAL: login failed")
        return 1
    login = json.loads(raw)
    token = login["access_token"]
    refresh = login.get("refresh_token")

    _, me_raw = req("GET", "/api/v1/auth/me", token=token)
    req("GET", "/api/v1/users/me", token=token)
    if refresh:
        req("POST", "/api/v1/auth/refresh", token=token, body={"refresh_token": refresh})

    user_id = json.loads(me_raw)["id"] if me_raw else ""
    today = date.today().isoformat()
    q = f"company_id={COMPANY_ID}"
    endpoints: list[tuple[str, str, tuple[int, ...]]] = [
        ("GET", f"/api/v1/calls?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/calls/logs?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/leads?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/leads/pipeline?{q}", (200,)),
        ("GET", f"/api/v1/users?{q}", (200,)),
        ("GET", f"/api/v1/users/sales-reps?{q}", (200,)),
        ("GET", f"/api/v1/users/assignees?{q}", (200,)),
        ("GET", "/api/v1/users/companies", (200,)),
        ("GET", f"/api/v1/appointments?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/appointments/upcoming?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/appointments/past?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/appointments/today?{q}&assigned_rep_id={user_id}&date={today}", (200,)),
        ("GET", f"/api/v1/leaderboards?{q}&period=weekly", (200, 403)),
        ("GET", f"/api/v1/appointments/counts?{q}", (200,)),
        ("GET", f"/api/v1/tasks?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/settings?{q}", (200,)),
        ("GET", f"/api/v1/settings/integrations?{q}", (200,)),
        ("GET", f"/api/v1/tenant-config/{COMPANY_ID}", (200,)),
        ("GET", f"/api/v1/ghost-mode/status?{q}", (200,)),
        ("GET", f"/api/v1/coaching/nudges?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/coaching/nudges/unread-count?{q}", (200,)),
        ("GET", f"/api/v1/coaching/sessions?{q}&limit=5", (200,)),
        ("GET", f"/api/v1/coaching/team-dashboard?{q}", (200,)),
        ("GET", f"/api/v1/insights/company/{COMPANY_ID}/current", (200, 404, 503)),
        ("GET", f"/api/v1/ask-Gomotto/conversations?{q}", (200, 404, 500)),
    ]
    metrics = [
        "exec/company-overview",
        "exec/csr/dashboard",
        "exec/missed-calls",
        "csr/auto-queued-leads",
        "booking-rate-improvement",
        "close-rate-trends",
        "bookings/summary",
        "objections/top",
        "objections/summary",
        "coaching/opportunities",
        "conversion/lead-to-sale",
        "company/performance",
        "calls/summary",
        "leads/unbooked",
        "actions/pending",
    ]
    for m in metrics:
        endpoints.append(("GET", f"/api/v1/metrics/{m}?{q}", (200,)))

    for method, path, ok in endpoints:
        req(method, path, token=token, ok=ok)

    req(
        "POST",
        "/api/v1/rag/ask-otto",
        token=token,
        body={"query": "hello", "context": {}},
        ok=(200, 403, 503),
    )

    # Detail routes from first call/lead
    _, raw = req("GET", f"/api/v1/calls?{q}&limit=1", token=token)
    if raw:
        calls = json.loads(raw)
        if calls:
            cid = calls[0]["id"]
            req("GET", f"/api/v1/calls/{cid}", token=token)
            req("GET", f"/api/v1/contact-card/calls/{cid}", token=token)

    _, raw = req("GET", f"/api/v1/leads?{q}&limit=1", token=token)
    if raw:
        leads = json.loads(raw)
        if leads:
            lid = leads[0]["id"]
            req("GET", f"/api/v1/leads/{lid}", token=token)
            req("GET", f"/api/v1/leads/{lid}/customer-card", token=token)

    print(f"\n=== SUMMARY: PASS={pass_count} FAIL={fail_count} WARN={warn_count} ===\n")
    for status, path, code, note in results:
        if status == "FAIL":
            print(f"FAIL  [{code}] {path} {note}")
    for status, path, code, note in results:
        if status == "WARN":
            print(f"WARN  [{code}] {path}")
    print(f"\nTotal endpoints tested: {len(results)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
