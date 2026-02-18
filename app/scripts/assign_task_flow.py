#!/usr/bin/env python3
import requests
import psycopg2
import time
import uuid
import os

API_BASE = "http://127.0.0.1:8005/api/v1"
DB = os.getenv("DATABASE_URL") or "***DB_URL_REMOVED***"
COMPANY_ID = "6d40b509-82bc-4d21-9614-de91cc25dc1b"

def login(email, password):
    r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()

def create_user_as_exec(exec_token, email, password, first, last, role="csr"):
    r = requests.post(f"{API_BASE}/users", json={
        "email": email, "password": password, "first_name": first, "last_name": last, "role": role, "company_id": COMPANY_ID
    }, headers={"Authorization": f"Bearer {exec_token}"})
    if not r.ok:
        print("Create user failed:", r.status_code, r.text)
    r.raise_for_status()
    return r.json()

def get_assignees(token):
    r = requests.get(f"{API_BASE}/users/assignees?company_id={COMPANY_ID}", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    data = r.json()
    # endpoint may return a list or a dict with "assignees"
    if isinstance(data, list):
        return data
    return data.get("assignees", [])

def create_task(exec_token):
    payload = {
        "company_id": COMPANY_ID,
        "action_type": "follow_up_call",
        "raw_text": "Please follow up with customer",
        "priority": 2
    }
    r = requests.post(f"{API_BASE}/tasks", json=payload, headers={"Authorization": f"Bearer {exec_token}"})
    r.raise_for_status()
    return r.json()

def patch_task_as_csr(csr_token, task_id, owner_id):
    payload = {"owner_id": owner_id}
    r = requests.patch(f"{API_BASE}/tasks/{task_id}", json=payload, headers={"Authorization": f"Bearer {csr_token}"})
    r.raise_for_status()
    return r.json()

def check_db_task_owner(task_id):
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT owner_id, assigned_by_id FROM pending_actions WHERE id=%s", (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def main():
    # Executive login (provided creds)
    exec_creds = {"email": "kaustarafdar@gmail.com", "password": "12345678"}
    print("Logging in executive...")
    exec_login = login(exec_creds["email"], exec_creds["password"])
    exec_token = exec_login["access_token"]
    print("Exec token len:", len(exec_token))

    # Get assignees and pick a sales rep
    assignees = get_assignees(exec_token)
    sales_rep = None
    for a in assignees:
        role_val = a.get("role") or a.get("role", None)
        # role may be enum value or string; normalize lowercase
        if role_val and str(role_val).lower() == "sales_rep" or role_val and str(role_val).lower() == "salesrep":
            sales_rep = a
            break
    if not sales_rep and assignees:
        sales_rep = assignees[0]

    if not sales_rep:
        raise RuntimeError("No assignees found for company")
    # user id field may be 'id' or 'user_id' depending on endpoint
    sales_rep_id = sales_rep.get("id") or sales_rep.get("user_id") or sales_rep.get("userId")
    print("Selected sales rep:", sales_rep_id, sales_rep.get("role"))

    # Create CSR as executive (use admin users endpoint)
    csr_email = f"testcsr+{uuid.uuid4().hex[:6]}@example.com"
    print("Creating CSR as executive:", csr_email)
    user_resp = create_user_as_exec(exec_token, csr_email, "Password123!", "Test", "CSR", role="csr")
    csr_id = user_resp["id"]
    # Login CSR to get token
    csr_login = login(csr_email, "Password123!")
    csr_token = csr_login["access_token"]
    print("CSR created id:", csr_id)

    # Create a task as executive (unassigned)
    print("Creating task as executive...")
    task = create_task(exec_token)
    task_id = task["id"]
    print("Task created:", task_id)

    # CSR assigns task to sales rep
    print("CSR assigning task to sales rep:", sales_rep_id)
    patched = patch_task_as_csr(csr_token, task_id, sales_rep_id)
    print("Patch result owner_id:", patched.get("owner_id"))

    # Verify DB
    time.sleep(1)
    db_row = check_db_task_owner(task_id)
    print("DB row owner_id, assigned_by_id:", db_row)

if __name__ == "__main__":
    main()

