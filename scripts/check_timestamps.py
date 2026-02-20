import requests
import re

base = "http://127.0.0.1:8005"
endpoints = [
    (
        "company_overview",
        f"{base}/api/v1/metrics/exec/company-overview?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&start_date=2026-02-14&end_date=2026-02-20",
    ),
    ("sales_dashboard", f"{base}/api/v1/sales_rep/exec/dashboard?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b"),
    ("objections_top", f"{base}/api/v1/metrics/objections/top?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5"),
    ("calls_logs", f"{base}/api/v1/calls/logs?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5"),
    ("appointments", f"{base}/api/v1/appointments?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&limit=5"),
]

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


if __name__ == "__main__":
    for name, url in endpoints:
        try:
            r = requests.get(url, timeout=20)
            print("---", name, "status", r.status_code)
            if r.status_code != 200:
                print(r.text[:1000])
                continue
            j = r.json()
            ts = find_timestamps(j)
            print(f"Found {len(ts)} timestamps in {name}")
            for p, t in ts[:20]:
                ok = ("+00:00" in t) or t.endswith("Z")
                print(p, t, "UTC" if ok else "NOT-UTC")
        except Exception as e:
            print("ERROR", name, e)

