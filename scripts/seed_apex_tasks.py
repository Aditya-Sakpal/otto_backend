"""
Seed Task Management (pending_actions) for Apex Roofing demo.
Creates ~40 tasks across all statuses, priorities, and team members.
"""
import uuid, psycopg2, psycopg2.extras
from datetime import datetime, timedelta, timezone

DB  = "***DB_URL_REMOVED***"
CID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

# User IDs
USERS = {
    "marcus":   "7970e248-d6c6-472b-89f4-ca5f7c6f9940",  # executive
    "sarah":    "2a6bd9e5-92e5-42ed-bfd3-9002ae099bff",  # csr
    "jennifer": "e46de9cf-ab56-4fb7-8c21-94f899bb7d3f",  # csr
    "ashley":   "9e75eab4-4c80-4b65-b8ba-75520d44968e",  # csr
    "nicole":   "4489ccb2-be79-415a-9545-c757d0fa649f",  # csr
    "rachel":   "69e19f27-d18e-42f1-97c9-5e9a63a390b1",  # csr
    "tyler":    "d7bfdf29-a1d6-4a2d-b47b-fe110bf41217",  # sales
    "brandon":  "971be14a-ebee-4317-8472-8d8018f3f6bb",  # sales
    "dylan":    "a89fb9d5-b75f-4fb0-8039-ab8fd8baa6cb",  # sales
    "austin":   "a141ca20-96a6-4892-96a0-1ecbdc0f5df2",  # sales
    "chase":    "76b420a9-2ace-4328-be72-f65a308e3e81",  # sales
}

now = datetime.now(timezone.utc)

def due(days_from_now):
    return now + timedelta(days=days_from_now)

def past(days_ago):
    return now - timedelta(days=days_ago)

# (raw_text, action_type, status, priority 1-10, owner, assigned_by, due_days, source)
TASKS = [
    # --- PENDING (12) ---
    ("Send detailed roof inspection estimate to customer after emergency call",             "send_quote",            "pending", 9, "tyler",    "sarah",    1,  "shunya"),
    ("Follow up with homeowner re: storm damage assessment - hasn't returned call",        "follow_up",             "pending", 8, "brandon",  "jennifer", 2,  "shunya"),
    ("Send payment plan options to customer concerned about full replacement cost",        "send_quote",            "pending", 7, "austin",   "ashley",   2,  "shunya"),
    ("Schedule in-person estimate for tile roof repair - Scottsdale property",             "schedule_appointment",  "pending", 8, "dylan",    "nicole",   3,  "shunya"),
    ("Coordinate with insurance adjuster for storm damage claim documentation",            "coordinate",            "pending", 7, "chase",    "rachel",   3,  "shunya"),
    ("Call back customer who requested skylight installation quote",                        "follow_up",             "pending", 6, "tyler",    "sarah",    4,  "shunya"),
    ("Send before/after photo examples of flat roof repairs to hesitant customer",        "send_documentation",    "pending", 5, "brandon",  "jennifer", 4,  "shunya"),
    ("Reschedule appointment - customer had scheduling conflict on original date",          "schedule_appointment",  "pending", 8, "austin",   "ashley",   1,  "shunya"),
    ("Send shingle replacement material options and color swatches",                       "send_info",             "pending", 5, "dylan",    "nicole",   5,  "shunya"),
    ("Reach out to customer for annual roof maintenance check reminder",                   "check_in",              "pending", 4, "chase",    "sarah",    7,  "manual"),
    ("Prepare warranty documentation for completed roof replacement project",              "send_documentation",    "pending", 6, "tyler",    "marcus",   5,  "manual"),
    ("Verify permit status for ongoing gutter installation project in Mesa",               "check_availability",    "pending", 7, "brandon",  "marcus",   2,  "manual"),

    # --- IN PROGRESS (10) ---
    ("Reviewing storm damage photos submitted by customer - preparing estimate",           "send_quote",            "in_progress", 9, "tyler",    "sarah",    0,  "shunya"),
    ("Coordinating crew availability for emergency roof repair in Phoenix",                "coordinate",            "in_progress", 9, "austin",   "jennifer", 0,  "shunya"),
    ("Following up with customer after initial inspection to confirm scope of work",       "follow_up",             "in_progress", 8, "brandon",  "ashley",   1,  "shunya"),
    ("Obtaining HOA approval for roof color change before replacement begins",             "coordinate",            "in_progress", 7, "dylan",    "nicole",   2,  "shunya"),
    ("Sending revised estimate after customer requested upgraded shingle grade",           "send_quote",            "in_progress", 7, "chase",    "rachel",   1,  "shunya"),
    ("Processing insurance claim paperwork for wind damage repair",                        "send_documentation",    "in_progress", 8, "tyler",    "sarah",    2,  "shunya"),
    ("Scheduling final walk-through inspection with Scottsdale customer post-repair",     "schedule_appointment",  "in_progress", 6, "brandon",  "jennifer", 1,  "manual"),
    ("Contacting supplier to confirm delivery of specialty tile materials",                "check_availability",    "in_progress", 7, "austin",   "marcus",   0,  "manual"),
    ("Updating CRM with call notes from today's roof inspection consultation",             "custom",                "in_progress", 5, "dylan",    "marcus",   0,  "manual"),
    ("Preparing job site safety checklist for Goodyear flat roof replacement",             "custom",                "in_progress", 6, "chase",    "marcus",   1,  "manual"),

    # --- COMPLETED (12) ---
    ("Sent estimate for shingle replacement - customer approved",                          "send_quote",            "completed", 8, "tyler",    "sarah",    -3, "shunya"),
    ("Scheduled roof inspection appointment for Chandler property",                        "schedule_appointment",  "completed", 7, "brandon",  "jennifer", -2, "shunya"),
    ("Followed up with customer post storm damage - appointment confirmed",                "follow_up",             "completed", 9, "austin",   "ashley",   -4, "shunya"),
    ("Sent insurance documentation for hail damage claim",                                 "send_documentation",    "completed", 8, "dylan",    "nicole",   -1, "shunya"),
    ("Coordinated with HOA for Scottsdale flat roof approval - approved",                  "coordinate",            "completed", 7, "chase",    "rachel",   -5, "shunya"),
    ("Called back customer - appointment for tile inspection scheduled",                   "follow_up",             "completed", 6, "tyler",    "sarah",    -6, "shunya"),
    ("Collected remaining balance payment from completed Mesa project",                    "custom",                "completed", 8, "brandon",  "marcus",   -2, "manual"),
    ("Sent thank-you note and referral program info to happy customer",                    "send_info",             "completed", 4, "austin",   "marcus",   -7, "manual"),
    ("Updated project status in system for Peoria roof replacement",                       "custom",                "completed", 5, "dylan",    "marcus",   -3, "manual"),
    ("Confirmed material order for next week's Surprise installation",                     "check_availability",    "completed", 6, "chase",    "marcus",   -4, "manual"),
    ("Sent post-job satisfaction survey to Gilbert homeowner",                             "send_info",             "completed", 4, "sarah",    "marcus",   -8, "manual"),
    ("Prepared monthly call performance summary for team review",                          "custom",                "completed", 5, "marcus",   "marcus",   -10,"manual"),

    # --- CANCELLED (4) ---
    ("Follow up with customer who requested quote - customer decided not to proceed",      "follow_up",             "cancelled", 5, "tyler",    "sarah",    -5, "shunya"),
    ("Schedule estimate visit - customer moved out of service area",                       "schedule_appointment",  "cancelled", 6, "brandon",  "jennifer", -3, "shunya"),
    ("Send roof replacement financing options - customer already hired another contractor","send_quote",            "cancelled", 7, "austin",   "ashley",   -7, "shunya"),
    ("Coordinate inspection for new construction - project cancelled by builder",         "coordinate",            "cancelled", 5, "dylan",    "nicole",   -4, "shunya"),
]

conn = psycopg2.connect(DB)
conn.autocommit = False
cur = conn.cursor()
psycopg2.extras.register_uuid()

# Get some real call IDs to link to tasks
cur.execute("""
    SELECT id FROM calls
    WHERE company_id=%s AND missed_call=false
    ORDER BY created_at DESC LIMIT 38
""", (CID,))
call_ids = [r[0] for r in cur.fetchall()]

inserted = 0
for i, (text, action_type, status, priority, owner_key, assigned_by_key, due_offset, source) in enumerate(TASKS):
    task_id   = str(uuid.uuid4())
    owner_id  = USERS[owner_key]
    by_id     = USERS[assigned_by_key]
    call_id   = call_ids[i % len(call_ids)] if call_ids else None
    due_at    = due(due_offset) if due_offset >= 0 else past(-due_offset)
    created   = past(abs(due_offset) + 1)

    cur.execute("""
        INSERT INTO pending_actions
          (id, company_id, call_id, action_type, raw_text, status, priority,
           owner_id, assigned_by_id, source, extra_metadata, due_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        task_id, CID, call_id, action_type, text, status, priority,
        owner_id, by_id, source, psycopg2.extras.Json({}),
        due_at, created, created
    ))
    inserted += 1

conn.commit()

# Verify
cur.execute("""
    SELECT status, COUNT(*) FROM pending_actions
    WHERE company_id=%s GROUP BY status ORDER BY status
""", (CID,))
print("=== TASKS SEEDED ===")
total = 0
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")
    total += r[1]
print(f"  TOTAL: {total}")

cur.close()
conn.close()
print("Done.")
