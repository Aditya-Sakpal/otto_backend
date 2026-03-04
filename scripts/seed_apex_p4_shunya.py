"""
Phase 4: Shunya API setup — tenant config + SOP upload for Apex Roofing.
"""
import json, os, time
import urllib.request, urllib.error
import urllib.parse

SHUNYA_BASE = "https://ottoai.shunyalabs.ai"
API_KEY     = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
COMPANY_ID  = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

JSON_HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

SOP_URL = "https://otto-documents-staging.s3.ap-southeast-2.amazonaws.com/user-onboarding-docs/anthony@arizonaroofers.com_Intake_Calls_(3)_(1).pdf.pdf"
REF_URL = "https://otto-documents-staging.s3.ap-southeast-2.amazonaws.com/user-onboarding-docs/anthony@arizonaroofers.com_What_types_of_appointments_to_book_.pdf.pdf"


def api_json(method: str, path: str, body=None) -> dict:
    url  = f"{SHUNYA_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=JSON_HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  HTTP {e.code}: {err[:500]}")
        return {"error": err, "status_code": e.code}
    except Exception as ex:
        print(f"  Error: {ex}")
        return {"error": str(ex)}


def upload_sop_multipart(file_url: str, sop_name: str, target_role: str = None) -> dict:
    """Upload SOP using multipart/form-data with file_url field."""
    url = f"{SHUNYA_BASE}/api/v1/sop/documents/upload"

    # Build multipart form data
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    fields = [
        ("company_id", COMPANY_ID),
        ("sop_name", sop_name),
        ("file_url", file_url),
    ]
    if target_role:
        fields.append(("target_role", target_role))

    body_parts = []
    for name, value in fields:
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    body_parts.append(f"--{boundary}--\r\n")
    body = "".join(body_parts).encode("utf-8")

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  HTTP {e.code}: {err[:500]}")
        return {"error": err, "status_code": e.code}
    except Exception as ex:
        print(f"  Error: {ex}")
        return {"error": str(ex)}


def main():
    # -- Step 1: Create tenant config --
    print("Creating Shunya tenant config...")
    config_body = {
        "company_id": COMPANY_ID,
        "company_name": "Apex Roofing",
        "industry": "home_services",
        "primary_services": [
            "Roof Repair", "Roof Replacement", "Shingle Replacement",
            "Tile Roof Repair", "Flat Roof Repair", "Emergency Roof Repair",
            "Roof Inspection", "Storm Damage Repair", "Gutter Repair",
        ],
        "qualification_thresholds": {
            "hot_score": 0.75,
            "warm_score": 0.50,
            "cold_score": 0.25,
            "bant_weights": {
                "need": 0.30,
                "budget": 0.25,
                "authority": 0.25,
                "timeline": 0.20,
            }
        },
        # service_prioritization must be a dict (object), not a list
        "service_prioritization": {
            "Emergency Roof Repair":  {"priority": 1, "wait_time_weeks": 0, "boost": 0.20},
            "Storm Damage Repair":    {"priority": 2, "wait_time_weeks": 1, "boost": 0.15},
            "Roof Repair":            {"priority": 3, "wait_time_weeks": 2, "boost": 0.10},
            "Roof Replacement":       {"priority": 4, "wait_time_weeks": 3, "boost": 0.08},
            "Shingle Replacement":    {"priority": 5, "wait_time_weeks": 4, "boost": 0.05},
            "Tile Roof Repair":       {"priority": 6, "wait_time_weeks": 4, "boost": 0.05},
            "Flat Roof Repair":       {"priority": 7, "wait_time_weeks": 5, "boost": 0.03},
            "Roof Inspection":        {"priority": 8, "wait_time_weeks": 2, "boost": 0.05},
            "Gutter Repair":          {"priority": 9, "wait_time_weeks": 3, "boost": 0.02},
        },
        "custom_keywords": {
            "urgency": ["leak", "emergency", "flooding", "damage", "immediately", "asap", "urgent"],
            "budget":  ["budget", "afford", "financing", "payment plan", "price", "cost", "estimate"],
            "service": ["roof", "shingle", "tile", "flat", "gutter", "skylight", "inspection"],
        },
        "business_hours": {
            "timezone": "America/Phoenix",
            "weekdays": {"open": "07:00", "close": "18:00"},
            "saturday": {"open": "08:00", "close": "14:00"},
            "sunday":   None,
        },
        # service_area must be a flat list of strings
        "service_area": [
            "85001","85002","85003","85004","85005","85006","85007","85008",
            "85009","85010","85012","85013","85014","85015","85016","85017",
            "85018","85019","85020","85021","85022","85023","85024","85032",
            "85033","85034","85035","85040","85041","85042","85048","85050",
            "85051","85053","85054","85085","85086","85087","85250","85251",
            "85252","85253","85254","85255","85256","85257","85258","85259",
            "85260","85281","85282","85283","85284","85295","85296","85297",
            "85298","85299","85301","85302","85303","85304","85305","85306",
            "85307","85308","85309","85310","85339","85340","85345","85353",
            "85373","85374","85375","85379","85381","85382","85383","85387",
            "Phoenix","Scottsdale","Tempe","Chandler","Gilbert","Mesa",
            "Glendale","Peoria","Surprise","Avondale","Goodyear","Buckeye",
        ],
    }

    result = api_json("POST", "/api/v1/tenant-config/", config_body)
    if "error" not in result:
        print(f"  Tenant config created: {result.get('company_id', result)}")
    else:
        print(f"  Config result: {result}")

    # -- Step 2: Upload CSR SOP (customer_rep) via multipart --
    print("Uploading CSR SOP (customer_rep)...")
    result = upload_sop_multipart(SOP_URL, "Apex Roofing CSR Intake SOP", target_role="customer_rep")
    csr_job_id = result.get("job_id")
    print(f"  CSR SOP job: {csr_job_id}, status: {result.get('status')}")
    if "error" in result:
        print(f"  Warning: {result}")

    # -- Step 3: Upload Reference Doc (company-wide) via multipart --
    print("Uploading reference doc (company-wide)...")
    result = upload_sop_multipart(REF_URL, "Apex Roofing Appointment Booking Guide")
    ref_job_id = result.get("job_id")
    print(f"  Reference doc job: {ref_job_id}, status: {result.get('status')}")
    if "error" in result:
        print(f"  Warning: {result}")

    # -- Step 4: Poll SOP jobs (up to 3 min each) --
    for label, job_id in [("CSR SOP", csr_job_id), ("Reference Doc", ref_job_id)]:
        if not job_id:
            continue
        print(f"  Polling {label} job {job_id}...")
        for attempt in range(18):   # 18 x 10s = 3 min
            time.sleep(10)
            status_result = api_json("GET", f"/api/v1/sop/documents/status/{job_id}")
            st = status_result.get("status", "unknown")
            print(f"    [{attempt+1}] {label}: {st}")
            if st in ("completed", "failed"):
                break

    # -- Step 5: Verify tenant config --
    print("Verifying tenant config...")
    verify = api_json("GET", f"/api/v1/tenant-config/{COMPANY_ID}")
    print(f"  Config: {verify.get('company_name', verify)}")

    # -- Step 6: List SOPs --
    print("Listing SOPs...")
    sops = api_json("GET", f"/api/v1/sop/documents?company_id={COMPANY_ID}")
    print(f"  SOPs: {sops.get('total', sops)}")

    print("\nPhase 4 complete. Shunya setup done.")


if __name__ == "__main__":
    main()
