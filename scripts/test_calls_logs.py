import sys, json, requests

BASE = "http://127.0.0.1:8005/api/v1"

def main():
    creds = {"email": "kaustarafdar@gmail.com", "password": "12345678"}
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=10)
    print("LOGIN_STATUS", r.status_code)
    data = r.json()
    token = data.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    params = {"company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b", "skip": 0, "limit": 10}
    r2 = requests.get(f"{BASE}/calls/logs", headers=headers, params=params, timeout=15)
    print("CALLS_LOGS_STATUS", r2.status_code)
    try:
        print("CALLS_LOGS_BODY", json.dumps(r2.json(), indent=2))
    except Exception:
        print("CALLS_LOGS_RAW", r2.text)

if __name__ == "__main__":
    main()

