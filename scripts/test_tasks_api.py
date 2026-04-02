import sys, json
import requests

BASE = "http://127.0.0.1:8005/api/v1"

def main():
    creds = {"email": "kaustarafdar@gmail.com", "password": "12345678"}
    try:
        r = requests.post(f"{BASE}/auth/login", json=creds, timeout=10)
    except Exception as e:
        print("LOGIN_REQUEST_ERROR", e)
        sys.exit(2)
    print("LOGIN_STATUS", r.status_code)
    try:
        data = r.json()
    except Exception:
        print("LOGIN_BODY_RAW", r.text)
        sys.exit(3)
    if r.status_code != 200:
        print("LOGIN_FAILED", data)
        sys.exit(4)
    token = data.get("access_token")
    if not token:
        print("NO_TOKEN", data)
        sys.exit(5)
    headers = {"Authorization": f"Bearer {token}"}
    params = {"company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b", "skip": 0, "limit": 50}
    try:
        r2 = requests.get(f"{BASE}/tasks", headers=headers, params=params, timeout=15)
    except Exception as e:
        print("TASKS_REQUEST_ERROR", e)
        sys.exit(6)
    print("TASKS_STATUS", r2.status_code)
    try:
        print("TASKS_BODY", json.dumps(r2.json(), indent=2))
    except Exception:
        print("TASKS_BODY_RAW", r2.text)
        sys.exit(7)
    # also test /auth/me
    try:
        r3 = requests.get(f"{BASE}/auth/me", headers=headers, timeout=10)
        print("ME_STATUS", r3.status_code)
        try:
            print("ME_BODY", json.dumps(r3.json(), indent=2))
        except Exception:
            print("ME_BODY_RAW", r3.text)
    except Exception as e:
        print("ME_REQUEST_ERROR", e)

if __name__ == "__main__":
    main()

