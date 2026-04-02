import requests
import re
import sys

BASE = "http://127.0.0.1:8005"
LOGIN = f"{BASE}/api/v1/auth/login"
CREDS = {"email": "kaustarafdar@gmail.com", "password": "12345678"}

endpoints = {
    "company_overview": f"{BASE}/api/v1/metrics/exec/company-overview?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&start_date=2026-02-14&end_date=2026-02-20",
    "sales_dashboard": f"{BASE}/api/v1/sales_rep/exec/dashboard?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b",
    "objections_top": f"{BASE}/api/v1/metrics/objections/top?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5",
    "calls_logs": f"{BASE}/api/v1/calls/logs?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5",
    "appointments": f"{BASE}/api/v1/appointments?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5",
}

iso_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([.]\d+)?(Z|\+00:00)")


def find_timestamps(o, path=""):
    found = []
    if isinstance(o, dict):
        for k, v in o.items():
            found += find_timestamps(v, path + ("/" + k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            found += find_timestamps(v, f"{path}[{i}]")
    elif isinstance(o, str):
        if iso_re.search(o):
            found.append((path, o))
    return found


def main():
    try:
        r = requests.post(LOGIN, json=CREDS, timeout=15)
    except Exception as e:
        print("Login request failed:", e)
        sys.exit(1)

    print("LOGIN status:", r.status_code)
    try:
        jr = r.json()
    except Exception:
        print("Login response not JSON:", r.text[:1000])
        sys.exit(1)

    token = jr.get("access_token") or jr.get("token") or jr.get("accessToken")
    if not token:
        print("No access token in response:", jr)
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    for name, url in endpoints.items():
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            print(f"--- {name} -> {resp.status_code}")
            text = resp.text or ""
            print(text[:1000])
            if resp.status_code == 200:
                try:
                    j = resp.json()
                    ts = find_timestamps(j)
                    print(f"Found {len(ts)} timestamps; sample up to 5:")
                    for p, t in ts[:5]:
                        ok = ("+00:00" in t) or t.endswith("Z")
                        print(p, t, "UTC" if ok else "NOT-UTC")
                except Exception as e:
                    print("JSON parse error:", e)
        except Exception as e:
            print("Request error for", name, e)


if __name__ == "__main__":
    main()

