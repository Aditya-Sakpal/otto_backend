"""
Fix Apex Roofing leads that have no calls/analyses.

25 leads across 4 stages are missing call records:
  - 13 booked/qualified_booked  -> booking_status='booked', qualified_and_booked
  - 4  qualified/hot            -> booking_status='not_booked', qualification_status='hot'
  - 6  qualified/qualified_unbooked -> booking_status='not_booked', qualified_but_unbooked
  - 2  service_not_offered      -> booking_status='service_not_offered'

For each lead we create:
  1. A calls row  (inbound, answered, linked to lead + contact_card)
  2. A call_analyses row (status='completed', with accurate stage-matching data)
"""
import uuid, json, random
from datetime import datetime, timedelta, timezone

import psycopg2, psycopg2.extras

DB  = "***DB_URL_REMOVED***"
CID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

random.seed(42)
now = datetime.now(timezone.utc)

# CSR roster
CSRS = [
    {"id": "2a6bd9e5-92e5-42ed-bfd3-9002ae099bff", "name": "Sarah Mitchell",   "email": "sarah.mitchell@apexroofing.com",   "agent_id": "USRAPEX001SARAH0000000000000001"},
    {"id": "e46de9cf-ab56-4fb7-8c21-94f899bb7d3f", "name": "Jennifer Brooks",  "email": "jennifer.brooks@apexroofing.com",  "agent_id": "USRAPEX002JENNIFER000000000002"},
    {"id": "9e75eab4-4c80-4b65-b8ba-75520d44968e", "name": "Ashley Carter",    "email": "ashley.carter@apexroofing.com",    "agent_id": "USRAPEX003ASHLEY00000000000003"},
    {"id": "4489ccb2-be79-415a-9545-c757d0fa649f", "name": "Nicole Davis",     "email": "nicole.davis@apexroofing.com",     "agent_id": "USRAPEX004NICOLE00000000000004"},
    {"id": "69e19f27-d18e-42f1-97c9-5e9a63a390b1", "name": "Rachel Evans",     "email": "rachel.evans@apexroofing.com",     "agent_id": "USRAPEX005RACHEL00000000000005"},
]

def pick_csr():
    return random.choice(CSRS)

def rand_duration(lo=120, hi=550):
    return random.randint(lo, hi)

def rand_past(days_lo=10, days_hi=25):
    """Return a UTC datetime between days_lo and days_hi days ago."""
    delta = timedelta(days=random.randint(days_lo, days_hi),
                      hours=random.randint(8, 17),
                      minutes=random.randint(0, 59))
    return now - delta

def call_meta(csr):
    return json.dumps({
        "direction": "inbound",
        "status": "answered",
        "call_status": "answered",
        "tracking_number": "+14805559100",
        "tracking_label": "Apex Roofing Main Line",
        "source": "Apex Roofing Main Line",
        "duration": rand_duration(),
        "talk_time": rand_duration(90, 400),
        "agent": {
            "id":      csr["agent_id"],
            "name":    csr["name"],
            "email":   csr["email"],
            "pic_url": f"/api/v1/accounts/999999/users/{csr['agent_id']}/pic_url",
        },
    })


# ── Lead definitions ──────────────────────────────────────────────────────────
# Each tuple: (lead_id, contact_card_id, phone, first_name, last_name,
#              status, pipeline_stage, service_requested, urgency, extra_meta)
#
# booked / qualified_booked  (13)
BOOKED_LEADS = [
    ("bb45e9ec-cbbb-4380-917e-5abb5050b2b7", "Storm damage assessment",   "high"),
    ("a29cb9e7-db41-42e0-a3fa-9e85d5ae9722", "Shingle replacement",       "medium"),
    ("231bd2c5-bcdf-4e52-a1da-4544054dc4f4", "Full roof replacement estimate","low"),
    ("455cbd9d-57f1-47f0-84ef-4ad8600975f6", "Metal roofing quote",        "low"),
    ("c355ef52-1178-4f71-90a5-f665fbf38e0c", "Emergency repair follow-up", "high"),
    ("2b4db6f8-b3c4-49b2-819e-01353a463cad", "Storm damage assessment",   "medium"),
    ("a019b815-34ec-44da-a487-799443841265", "Full roof replacement estimate","low"),
    ("29c138b8-9d78-4cb3-9b79-54da9e336319", "Emergency repair follow-up", "medium"),
    ("f667652f-372b-4ab9-bbac-921ff5536bfa", "Tile roof repair",           "low"),
    ("d5ae1ee7-e1da-4171-8c49-1a2c6634952c", "Storm damage assessment",   "medium"),
    ("f839882a-8f0c-4b37-8f7e-2e59e891d655", "Full roof replacement estimate","medium"),
    ("a4bf9562-8da2-4c64-9f01-850eb2532568", "Full roof replacement estimate","low"),
    ("90936fc2-8aac-4f67-9b94-b0fd9df2e602", "Storm damage assessment",   "medium"),
]

# qualified / hot  (4)
HOT_LEADS = [
    ("c0230c07-1dc4-4744-8dfb-9dbbb941c56c", "Shingle Replacement"),
    ("171905f1-1cea-4d1a-969b-8db593941068", "Emergency Roof Repair"),
    ("7268cfa5-4751-4d1b-aa6a-baba20b0070b", "Gutter Repair"),
    ("0d66a34a-00a9-4b38-b420-04a2da2316cc", "Emergency Roof Repair"),
]

# qualified / qualified_unbooked  (6)
UNBOOKED_LEADS = [
    ("0c3c5ca1-2208-4087-92c7-0b20f592e7a4", "Storm damage assessment",          "high"),
    ("09dc8dd9-4238-4dcc-85b4-8b27b110759b", "Tile roof repair",                 "low"),
    ("b35f1f09-d130-4a3a-98ea-fd2d5d63f16a", "Full roof replacement estimate",   "medium"),
    ("0f7bb217-ec3d-4c3e-ad9b-cb2fccb5da67", "Shingle replacement",             "high"),
    ("7ac5e045-b5b7-4994-9e02-be6732a67088", "Tile roof repair",                 "high"),
    ("f3e7e952-0fa0-4ae8-80c4-b4491051306f", "Full roof replacement estimate",   "medium"),
]

# service_not_offered / qualified_service_not_offered  (2)
SNO_LEADS = [
    (
        "ef4dd150-59a4-4bd2-bffb-64063f3940ed",
        "Roof installation for new construction",
        "Company only handles repairs and replacements on existing roofs; new construction installs are outside scope of service.",
    ),
    (
        "39826a32-d6e9-4104-9828-930b1b091d2b",
        "Commercial flat roof repair",
        "Company services residential roofing only; commercial and industrial flat roof repairs are not offered.",
    ),
]

# ── Summary / key_point templates ─────────────────────────────────────────────
def booked_summary(service, first, last):
    return (
        f"Inbound call from {first} {last} requesting {service.lower()}. "
        "Customer described the issue in detail and was receptive to scheduling. "
        "CSR qualified the lead, confirmed the address and availability, and "
        "successfully booked an appointment for an in-home estimate."
    )

def booked_key_points(service):
    return [
        f"Customer requested {service.lower()}",
        "Lead qualified — appointment confirmed and booked",
        "Customer confirmed availability and address",
        "CSR provided estimated arrival window",
    ]

def hot_summary(service, first, last):
    return (
        f"Inbound call from {first} {last} regarding {service.lower()}. "
        "Customer expressed strong urgency and interest but was unavailable "
        "for an immediate appointment. CSR captured full details and flagged "
        "as a high-priority follow-up for same-week callback."
    )

def hot_key_points(service):
    return [
        f"Customer requested {service.lower()} — high urgency",
        "Lead qualified but could not book during call",
        "Flagged for priority same-week follow-up",
        "Customer open to callback to schedule",
    ]

def unbooked_summary(service, first, last):
    return (
        f"Inbound call from {first} {last} inquiring about {service.lower()}. "
        "Customer was interested but requested time to review their schedule "
        "before committing to an appointment. CSR qualified the lead and "
        "agreed to follow up within the week."
    )

def unbooked_key_points(service):
    return [
        f"Customer inquired about {service.lower()}",
        "Lead qualified — appointment not booked during call",
        "Customer needs to check availability before scheduling",
        "Follow-up call agreed upon",
    ]

def sno_summary(service, first, last, reason):
    return (
        f"Inbound call from {first} {last} requesting {service.lower()}. "
        f"After discussing the request, CSR determined the service cannot be provided. "
        f"{reason} Customer was informed politely and offered referrals where applicable."
    )

def sno_key_points(service, reason):
    return [
        f"Customer requested {service.lower()}",
        "Service not offered — lead disqualified",
        reason[:80],
        "Customer informed and offered referral information",
    ]


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_contact(cur, lead_id):
    cur.execute(
        "SELECT l.contact_card_id, cc.primary_phone, cc.first_name, cc.last_name "
        "FROM leads l JOIN contact_cards cc ON cc.id = l.contact_card_id "
        "WHERE l.id = %s",
        (lead_id,),
    )
    return cur.fetchone()  # (contact_card_id, phone, first, last)


def insert_call(cur, *, lead_id, contact_card_id, phone, csr, created_at, duration):
    call_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO calls (
            id, company_id, contact_card_id, lead_id, phone_number,
            missed_call, duration_seconds, handled_by_user_id,
            extra_metadata, created_at, updated_at,
            status, scope
        ) VALUES (
            %s, %s, %s, %s, %s,
            false, %s, %s,
            %s::json, %s, %s,
            'completed', 'in'
        )
        """,
        (
            call_id, CID, contact_card_id, lead_id, phone,
            duration, csr["id"],
            call_meta(csr), created_at, created_at,
        ),
    )
    return call_id


def insert_analysis(cur, *, call_id, created_at, **kwargs):
    analysis_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO call_analyses (
            id, call_id, company_id, status,
            qualification_status, booking_status, call_outcome_category,
            summary, key_points, objections, objection_texts,
            sop_stages_completed, sop_stages_missed,
            service_requested, service_not_offered_reason,
            compliance_target_role, scope,
            follow_up_required,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'completed',
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            'customer_rep', 'in',
            %s,
            %s, %s
        )
        """,
        (
            analysis_id, call_id, CID,
            kwargs["qual_status"], kwargs["book_status"], kwargs["outcome_cat"],
            kwargs["summary"], kwargs["key_points"], [], [],
            kwargs.get("sop_completed", []), kwargs.get("sop_missed", []),
            kwargs.get("service_requested"), kwargs.get("sno_reason"),
            kwargs.get("follow_up", False),
            created_at, created_at,
        ),
    )
    return analysis_id


# ── Main ──────────────────────────────────────────────────────────────────────
conn = psycopg2.connect(DB)
conn.autocommit = False
cur = conn.cursor()
psycopg2.extras.register_uuid()

created_calls = 0
created_analyses = 0

# ── 1. BOOKED leads ───────────────────────────────────────────────────────────
print("Processing booked leads...")
for lead_id, service, urgency in BOOKED_LEADS:
    contact = get_contact(cur, lead_id)
    if not contact:
        print(f"  WARN: no contact for lead {lead_id}")
        continue
    cc_id, phone, first, last = contact
    csr = pick_csr()
    ts  = rand_past(8, 20)
    dur = rand_duration(200, 520)

    call_id = insert_call(cur, lead_id=lead_id, contact_card_id=cc_id,
                          phone=phone, csr=csr, created_at=ts, duration=dur)
    insert_analysis(
        cur, call_id=call_id, created_at=ts,
        qual_status="warm", book_status="booked",
        outcome_cat="qualified_and_booked",
        summary=booked_summary(service, first, last),
        key_points=booked_key_points(service),
        service_requested=service,
        follow_up=False,
    )
    # Also update lead extra_metadata to mark the source call
    cur.execute(
        "UPDATE leads SET extra_metadata = (COALESCE(extra_metadata::jsonb, '{}'::jsonb) || %s::jsonb)::json "
        "WHERE id = %s",
        (json.dumps({"created_from_call": call_id}), lead_id),
    )
    created_calls += 1
    created_analyses += 1
    print(f"  ✓ booked  lead {lead_id[:8]}… — {first} {last} / {service}")

# ── 2. HOT leads ──────────────────────────────────────────────────────────────
print("\nProcessing hot (qualified, unbooked) leads...")
for lead_id, service in HOT_LEADS:
    contact = get_contact(cur, lead_id)
    if not contact:
        print(f"  WARN: no contact for lead {lead_id}")
        continue
    cc_id, phone, first, last = contact
    csr = pick_csr()
    ts  = rand_past(5, 15)
    dur = rand_duration(150, 420)

    call_id = insert_call(cur, lead_id=lead_id, contact_card_id=cc_id,
                          phone=phone, csr=csr, created_at=ts, duration=dur)
    insert_analysis(
        cur, call_id=call_id, created_at=ts,
        qual_status="hot", book_status="not_booked",
        outcome_cat="qualified_but_unbooked",
        summary=hot_summary(service, first, last),
        key_points=hot_key_points(service),
        service_requested=service,
        follow_up=True,
    )
    cur.execute(
        "UPDATE leads SET extra_metadata = (COALESCE(extra_metadata::jsonb, '{}'::jsonb) || %s::jsonb)::json "
        "WHERE id = %s",
        (json.dumps({"created_from_call": call_id}), lead_id),
    )
    created_calls += 1
    created_analyses += 1
    print(f"  ✓ hot     lead {lead_id[:8]}… — {first} {last} / {service}")

# ── 3. QUALIFIED UNBOOKED leads ───────────────────────────────────────────────
print("\nProcessing qualified_unbooked leads...")
for lead_id, service, urgency in UNBOOKED_LEADS:
    contact = get_contact(cur, lead_id)
    if not contact:
        print(f"  WARN: no contact for lead {lead_id}")
        continue
    cc_id, phone, first, last = contact
    csr = pick_csr()
    ts  = rand_past(10, 22)
    dur = rand_duration(120, 400)

    call_id = insert_call(cur, lead_id=lead_id, contact_card_id=cc_id,
                          phone=phone, csr=csr, created_at=ts, duration=dur)
    insert_analysis(
        cur, call_id=call_id, created_at=ts,
        qual_status="warm", book_status="not_booked",
        outcome_cat="qualified_but_unbooked",
        summary=unbooked_summary(service, first, last),
        key_points=unbooked_key_points(service),
        service_requested=service,
        follow_up=True,
    )
    cur.execute(
        "UPDATE leads SET extra_metadata = (COALESCE(extra_metadata::jsonb, '{}'::jsonb) || %s::jsonb)::json "
        "WHERE id = %s",
        (json.dumps({"created_from_call": call_id}), lead_id),
    )
    created_calls += 1
    created_analyses += 1
    print(f"  ✓ unbooked lead {lead_id[:8]}… — {first} {last} / {service}")

# ── 4. SERVICE NOT OFFERED leads ──────────────────────────────────────────────
print("\nProcessing service_not_offered leads...")
for lead_id, service, sno_reason in SNO_LEADS:
    contact = get_contact(cur, lead_id)
    if not contact:
        print(f"  WARN: no contact for lead {lead_id}")
        continue
    cc_id, phone, first, last = contact
    csr = pick_csr()
    ts  = rand_past(12, 25)
    dur = rand_duration(90, 300)

    call_id = insert_call(cur, lead_id=lead_id, contact_card_id=cc_id,
                          phone=phone, csr=csr, created_at=ts, duration=dur)
    insert_analysis(
        cur, call_id=call_id, created_at=ts,
        qual_status="cold", book_status="service_not_offered",
        outcome_cat="qualified_service_not_offered",
        summary=sno_summary(service, first, last, sno_reason),
        key_points=sno_key_points(service, sno_reason),
        service_requested=service,
        sno_reason=sno_reason,
        follow_up=False,
    )
    # Update lead extra_metadata with service info
    cur.execute(
        "UPDATE leads SET extra_metadata = (COALESCE(extra_metadata::jsonb, '{}'::jsonb) || %s::jsonb)::json "
        "WHERE id = %s",
        (json.dumps({"created_from_call": call_id, "service_requested": service, "service_not_offered_reason": sno_reason}), lead_id),
    )
    created_calls += 1
    created_analyses += 1
    print(f"  ✓ sno     lead {lead_id[:8]}… — {first} {last} / {service}")

conn.commit()
print(f"\n✅ Done. Created {created_calls} calls and {created_analyses} analyses.")

# ── Verify ────────────────────────────────────────────────────────────────────
cur.execute("""
    SELECT l.pipeline_stage, l.status, COUNT(l.id),
           COUNT(CASE WHEN call_cnt = 0 THEN 1 END) AS still_no_calls
    FROM (
        SELECT l.id, l.status, l.pipeline_stage, COUNT(c.id) AS call_cnt
        FROM leads l
        LEFT JOIN calls c ON c.lead_id = l.id
        WHERE l.company_id = %s
        GROUP BY l.id, l.status, l.pipeline_stage
    ) l
    GROUP BY l.pipeline_stage, l.status
    ORDER BY l.pipeline_stage
""", (CID,))
print("\n=== VERIFICATION — leads by stage (no_calls should be 0) ===")
for r in cur.fetchall():
    flag = " ⚠️ " if r[3] > 0 else ""
    print(f"  {r[0]:20s} | {r[1]:30s} | total={r[2]:3d} | no_calls={r[3]}{flag}")

cur.close()
conn.close()
