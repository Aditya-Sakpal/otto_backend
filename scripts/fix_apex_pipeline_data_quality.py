"""
Comprehensive Apex Roofing pipeline data quality fixes:

1.  Add audio_url to all calls missing it (our seeded calls + pre-existing partial calls)
2.  Fix booked leads with wrong booking_status in analyses (Kevin Carter, Kenneth Clark,
    Donna Hill booked, Amanda Adams booked)
3.  Fix Kevin Carter analysis summary: replace "Arizona Roofers / Feb 3" → "Apex / March 16"
4.  Fix partial qualified analyses (NULL qualification_status / call_outcome_category)
5.  Move Donna Hill hot/qualified lead to unqualified (manager says wrongly classified)
6.  Clear appointments.interaction_id for 'appointment'-stage leads
    (no recording shown before appointment is conducted)
7.  Set appointments.outcome = NULL for 'appointment_ran' leads  (pending — no result yet)
8.  Set appointments.outcome = 'won'  for 'won' leads  (all currently say 'lost')
9.  Add 4 more service_not_offered leads with calls & analyses
"""
import os, uuid, json, random
from datetime import datetime, timedelta, timezone

import psycopg2, psycopg2.extras

# DB URL comes from the environment (see .env.example). Never hardcode credentials here.
DB  = os.environ["DATABASE_URL"]
CID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

random.seed(7)
now = datetime.now(timezone.utc)

conn = psycopg2.connect(DB)
conn.autocommit = False
cur = conn.cursor()
psycopg2.extras.register_uuid()

# ── Pool of real Apex audio URLs (from existing analysed calls) ───────────────
AUDIO_POOL = [
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/9c3f9720-7692-471b-9054-7137f3e0b766/4006817630.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/0ef6d322-a360-4e89-a1af-3e8b041c403c/4033388756.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/437cf5b0-9fee-4b49-bdb7-e761312c49bc/3995427380.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/df0344de-32d3-4323-a53a-64dcee66296b/4022050406.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/a452b372-f150-4599-9991-6bd32ab66c2f/4000590374.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/06c3e1f3-abe9-44bb-aa2d-417e7d4c9ae6/3991446131.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/4f1cfb18-afb9-49d0-8873-1636d42a019c/3981215466.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/b4f5c940-28b6-41d3-b917-88fb94b53e42/4055222822.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/2d2fa52f-462f-48ed-beb1-091cc5b5e827/4045649798.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/9f93768e-0e63-4a2c-b9ba-5cd0322e56cd/4000190804.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/0eafb182-f7b7-4449-aed2-b766f2cd6571/3977883360.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/31935f5c-bb9a-4615-97f5-6a0338c1ef89/4021712516.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/ca0f069e-f5e4-4879-ba6a-773e7c1751cb/3995714597.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/979227c3-897a-48ab-9226-f6c0fde3d1f8/4015471616.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/be74219f-1591-4b25-8125-5d7b42365718/3987953750.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/411d5473-7bd9-4ce0-b476-408fb4d5effe/4039319189.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/7b6c646b-c956-4443-bb79-f8a19df4c7ab/3986707224.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/694d8bab-138c-4d4a-9ad2-c9dd6ffa9b47/4007416793.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/eb4dbb3b-1c84-4f4b-aab2-8623cd5dd6bb/3977537073.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/5c283b56-08df-4d30-936b-34ca360b01ac/4008147536.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/16fd6b3c-505e-4021-b870-54fffa78f4a8/4024280393.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/e164807d-d78c-41dc-a09d-fca3b8e278fc/4020650882.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/2eb31a31-9e59-47ac-8a20-0c15114c1117/4046321702.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/cfba64d5-2ccc-4476-ab1a-dbf444bc67c2/4043529050.mp3",
    "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/6e71c1e9-d9a1-400b-808b-a9ddfc2b0d19/4052393537.mp3",
]
_audio_idx = 0

def next_audio():
    global _audio_idx
    url = AUDIO_POOL[_audio_idx % len(AUDIO_POOL)]
    _audio_idx += 1
    return url

def rand_past(days_lo=5, days_hi=20):
    return now - timedelta(days=random.randint(days_lo, days_hi),
                           hours=random.randint(8, 17),
                           minutes=random.randint(0, 59))

CSRS = [
    {"id": "2a6bd9e5-92e5-42ed-bfd3-9002ae099bff", "name": "Sarah Mitchell",
     "email": "sarah.mitchell@apexroofing.com", "agent_id": "USRAPEX001SARAH0000000000000001"},
    {"id": "e46de9cf-ab56-4fb7-8c21-94f899bb7d3f", "name": "Jennifer Brooks",
     "email": "jennifer.brooks@apexroofing.com", "agent_id": "USRAPEX002JENNIFER000000000002"},
    {"id": "9e75eab4-4c80-4b65-b8ba-75520d44968e", "name": "Ashley Carter",
     "email": "ashley.carter@apexroofing.com", "agent_id": "USRAPEX003ASHLEY00000000000003"},
    {"id": "4489ccb2-be79-415a-9545-c757d0fa649f", "name": "Nicole Davis",
     "email": "nicole.davis@apexroofing.com", "agent_id": "USRAPEX004NICOLE00000000000004"},
    {"id": "69e19f27-d18e-42f1-97c9-5e9a63a390b1", "name": "Rachel Evans",
     "email": "rachel.evans@apexroofing.com", "agent_id": "USRAPEX005RACHEL00000000000005"},
]

def pick_csr():
    return random.choice(CSRS)

def call_meta(csr, duration=None):
    dur = duration or random.randint(120, 480)
    return json.dumps({
        "direction": "inbound", "status": "answered", "call_status": "answered",
        "tracking_number": "+14805559100", "tracking_label": "Apex Roofing Main Line",
        "source": "Apex Roofing Main Line", "duration": dur, "talk_time": dur - random.randint(20, 60),
        "agent": {"id": csr["agent_id"], "name": csr["name"], "email": csr["email"],
                  "pic_url": f"/api/v1/accounts/999999/users/{csr['agent_id']}/pic_url"},
    })

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: Add audio_url to ALL Apex calls that currently have NULL audio_url
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FIX 1: Backfill audio_url on calls with NULL audio_url")
print("=" * 60)

cur.execute("""
    SELECT c.id
    FROM calls c
    JOIN leads l ON l.id = c.lead_id
    WHERE c.company_id = %s
      AND c.audio_url IS NULL
      AND c.interaction_type = 'inbound'
""", (CID,))
no_audio_calls = [r[0] for r in cur.fetchall()]
print(f"  Found {len(no_audio_calls)} inbound calls with NULL audio_url")

for call_id in no_audio_calls:
    cur.execute("UPDATE calls SET audio_url = %s WHERE id = %s",
                (next_audio(), call_id))
print(f"  Updated {len(no_audio_calls)} calls with audio URLs")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: Fix booked leads with not_booked in their call_analyses
# Kevin Carter, Kenneth Clark, Donna Hill (booked), Amanda Adams (booked f1391582)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 2: Fix call_analyses for booked leads with not_booked status")
print("=" * 60)

# These leads are in pipeline_stage='booked' but call_analyses shows not_booked
BOOKED_ANALYSIS_FIXES = [
    # (lead_id, service_description, first_name, last_name)
    ("e0bfab28-cb46-4390-b365-1d815cc994f1", "Emergency Roof Repair", "Kevin",   "Carter"),
    ("bbdc4d6d-e6cc-4e0e-9f6a-e17cd1babb01", "Flat Roof Repair",      "Kenneth", "Clark"),
    ("19c2da82-1194-4a5a-b8fa-d452913ac1dc", "Storm Damage Assessment","Donna",   "Hill"),
    ("f1391582-1550-44f1-be2d-161294287f93", "Full Roof Replacement",  "Amanda",  "Adams"),
]

for lead_id, service, first, last in BOOKED_ANALYSIS_FIXES:
    # Get the call_analyses id(s) for this lead's calls
    cur.execute("""
        SELECT ca.id, ca.summary
        FROM call_analyses ca
        JOIN calls c ON c.id = ca.call_id
        WHERE c.lead_id = %s
        ORDER BY ca.created_at DESC
        LIMIT 1
    """, (lead_id,))
    row = cur.fetchone()
    if not row:
        print(f"  WARN: no analysis found for lead {lead_id} ({first} {last})")
        continue
    ca_id, old_summary = row

    # Build a proper booked summary (replace any "Arizona Roofers" / old dates)
    march_date = "March 16th" if random.random() > 0.5 else "March 17th"
    new_summary = (
        f"{first} {last} called Apex Roofing requesting {service.lower()}. "
        f"The CSR thoroughly qualified the lead — confirmed the property details, "
        f"assessed the urgency, and discussed available appointment windows. "
        f"{first} accepted the proposed time and an appointment was confirmed for "
        f"{march_date} between 10:00 AM and 12:00 PM. A confirmation was sent by "
        f"email and the technician will call 30 minutes before arrival."
    )
    new_key_points = [
        f"Customer requested {service.lower()}",
        f"Appointment confirmed for {march_date}, 10 AM–12 PM window",
        "Property details and contact info collected",
        "Lead qualified — booking status: booked",
    ]
    appt_dt = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc) if "16" in march_date \
              else datetime(2026, 3, 17, 10, 0, 0, tzinfo=timezone.utc)

    cur.execute("""
        UPDATE call_analyses SET
            booking_status        = 'booked',
            qualification_status  = 'warm',
            call_outcome_category = 'qualified_and_booked',
            appointment_confirmed = true,
            appointment_date      = %s,
            summary               = %s,
            key_points            = %s,
            service_requested     = %s,
            updated_at            = NOW()
        WHERE id = %s
    """, (appt_dt, new_summary, new_key_points, service, ca_id))
    print(f"  Fixed analysis for {first} {last} ({lead_id[:8]}…) -> booked / {march_date}")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: Fix partial qualified analyses (NULL qual_status / outcome_cat)
# These are pre-existing leads whose call_analyses were partially populated
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 3: Complete partial qualified-stage call analyses")
print("=" * 60)

cur.execute("""
    SELECT ca.id, l.status, ca.booking_status, cc.first_name, cc.last_name
    FROM call_analyses ca
    JOIN calls c ON c.id = ca.call_id
    JOIN leads l ON l.id = c.lead_id
    JOIN contact_cards cc ON cc.id = l.contact_card_id
    WHERE l.company_id = %s
      AND l.pipeline_stage = 'qualified'
      AND (ca.qualification_status IS NULL OR ca.call_outcome_category IS NULL)
""", (CID,))
partial_rows = cur.fetchall()
print(f"  Found {len(partial_rows)} qualified analyses with NULL fields")

for ca_id, lead_status, booking_status, first, last in partial_rows:
    qual = "hot" if lead_status == "hot" else "warm"
    cur.execute("""
        UPDATE call_analyses SET
            qualification_status  = %s,
            booking_status        = 'not_booked',
            call_outcome_category = 'qualified_but_unbooked',
            updated_at            = NOW()
        WHERE id = %s
          AND (qualification_status IS NULL OR call_outcome_category IS NULL)
    """, (qual, ca_id))
    print(f"  Patched {first} {last} analysis {str(ca_id)[:8]}... -> {qual}/not_booked/qualified_but_unbooked")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: Move Donna Hill (74d6e71c) from hot/qualified to unqualified/abandoned
# Manager flagged: "Donna Hill is unqualified but shows in qualified"
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 4: Move Donna Hill (74d6e71c) to unqualified/abandoned")
print("=" * 60)

DONNA_HILL_MISCLASSIFIED = "74d6e71c-de27-4cb3-84f4-9c6ab3d9095c"
cur.execute("""
    UPDATE leads SET
        status         = 'abandoned',
        pipeline_stage = 'unqualified',
        updated_at     = NOW()
    WHERE id = %s
""", (DONNA_HILL_MISCLASSIFIED,))
cur.execute("""
    UPDATE call_analyses SET
        qualification_status  = 'cold',
        booking_status        = 'not_booked',
        call_outcome_category = 'unqualified',
        updated_at            = NOW()
    WHERE call_id IN (SELECT id FROM calls WHERE lead_id = %s)
""", (DONNA_HILL_MISCLASSIFIED,))
print(f"  Moved Donna Hill {DONNA_HILL_MISCLASSIFIED[:8]}… to unqualified/abandoned")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 5: Clear appointments.interaction_id for 'appointment'-stage leads
# These leads have a scheduled appointment but it hasn't happened yet —
# showing the CSR booking call as an "appointment recording" is misleading.
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 5: Clear interaction_id for appointment-stage leads (not yet run)")
print("=" * 60)

cur.execute("""
    UPDATE appointments SET
        interaction_id = NULL,
        audio_url      = NULL,
        updated_at     = NOW()
    WHERE lead_id IN (
        SELECT id FROM leads
        WHERE company_id = %s AND pipeline_stage = 'appointment'
    )
""", (CID,))
print(f"  Cleared interaction_id / audio_url on {cur.rowcount} appointment-stage appointments")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 6: Set appointment outcome = NULL for appointment_ran leads
# These appointments were conducted but outcome is pending — not 'lost'
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 6: Reset outcome to NULL for appointment_ran (pending) leads")
print("=" * 60)

cur.execute("""
    UPDATE appointments SET
        outcome    = NULL,
        updated_at = NOW()
    WHERE lead_id IN (
        SELECT id FROM leads
        WHERE company_id = %s AND pipeline_stage = 'appointment_ran'
    )
""", (CID,))
print(f"  Cleared outcome on {cur.rowcount} appointment_ran appointments")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 7: Set appointment outcome = 'won' for leads in 'won' pipeline stage
# All won leads currently show outcome = 'lost' — clearly wrong
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 7: Set outcome='won' on all won-stage appointments")
print("=" * 60)

cur.execute("""
    UPDATE appointments SET
        outcome    = 'won',
        updated_at = NOW()
    WHERE lead_id IN (
        SELECT id FROM leads
        WHERE company_id = %s AND pipeline_stage = 'won'
    )
""", (CID,))
print(f"  Updated {cur.rowcount} won-stage appointments to outcome='won'")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 8: Add 4 new service_not_offered leads (expand from 2 to 6)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIX 8: Add 4 new service_not_offered leads")
print("=" * 60)

NEW_SNO = [
    {
        "first": "Robert",  "last": "Kim",
        "phone": "6025550101",
        "service": "Metal roof installation",
        "sno_reason": "Apex Roofing does not install metal roofing systems; the company specialises in asphalt shingle and tile roofing only.",
        "summary_extra": "Robert inquired about a full metal roof installation for his property. After gathering details, the CSR explained that Apex Roofing specialises in asphalt and tile roofing and does not offer metal roof systems.",
    },
    {
        "first": "Sandra",  "last": "Price",
        "phone": "6025550202",
        "service": "Roof repair in Flagstaff",
        "sno_reason": "Outside service area — Apex Roofing currently services the Phoenix metro area only and does not dispatch crews to Flagstaff or Northern Arizona.",
        "summary_extra": "Sandra called requesting a repair at her Flagstaff property. The CSR confirmed the address and informed Sandra that Apex Roofing's current service area is limited to the Phoenix metro region.",
    },
    {
        "first": "Timothy", "last": "Brooks",
        "phone": "6025550303",
        "service": "Commercial warehouse roof replacement",
        "sno_reason": "Apex Roofing provides residential roofing services only; commercial and industrial properties are outside the company's scope of service.",
        "summary_extra": "Timothy called about replacing the roof on a commercial warehouse. The CSR determined the property is commercial and explained that Apex only services residential homes.",
    },
    {
        "first": "Patricia", "last": "Nguyen",
        "phone": "6025550404",
        "service": "Solar panel removal and roof repair",
        "sno_reason": "Apex Roofing does not handle solar panel removal or reinstallation; the customer would need to coordinate with a solar contractor before any roofing work can proceed.",
        "summary_extra": "Patricia needed her roof repaired but the property has solar panels that must be removed first. The CSR explained that Apex does not offer solar removal services and advised contacting her solar provider first.",
    },
]

for sno in NEW_SNO:
    csr = pick_csr()
    ts  = rand_past(8, 22)
    dur = random.randint(120, 320)

    # Create contact card
    cc_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO contact_cards (id, company_id, primary_phone, first_name, last_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (cc_id, CID, sno["phone"], sno["first"], sno["last"]))

    # Create lead
    lead_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO leads (id, company_id, contact_card_id, status, pipeline_stage, created_at, updated_at)
        VALUES (%s, %s, %s, 'qualified_service_not_offered', 'service_not_offered', %s, %s)
    """, (lead_id, CID, cc_id, ts, ts))

    # Create call
    call_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO calls (
            id, company_id, contact_card_id, lead_id, phone_number,
            missed_call, duration_seconds, handled_by_user_id,
            audio_url, extra_metadata, interaction_type,
            created_at, updated_at, status, scope
        ) VALUES (%s, %s, %s, %s, %s, false, %s, %s, %s, %s::json, 'inbound', %s, %s, 'completed', 'in')
    """, (call_id, CID, cc_id, lead_id, sno["phone"],
          dur, csr["id"], next_audio(),
          call_meta(csr, dur), ts, ts))

    # Full summary
    full_summary = (
        f"{sno['first']} {sno['last']} called Apex Roofing regarding {sno['service'].lower()}. "
        f"{sno['summary_extra']} "
        f"The customer was informed politely and offered referral information where applicable."
    )
    key_points = [
        f"Customer requested: {sno['service']}",
        "Service not offered — lead disqualified",
        sno["sno_reason"][:90],
        "Customer informed and provided referral guidance",
    ]

    # Create call analysis
    ca_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO call_analyses (
            id, call_id, company_id, status,
            qualification_status, booking_status, call_outcome_category,
            summary, key_points, objections, objection_texts,
            sop_stages_completed, sop_stages_missed,
            service_requested, service_not_offered_reason,
            compliance_target_role, scope,
            follow_up_required, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'completed',
            'cold', 'service_not_offered', 'qualified_service_not_offered',
            %s, %s, %s, %s, %s, %s,
            %s, %s,
            'customer_rep', 'in',
            false, %s, %s
        )
    """, (ca_id, call_id, CID,
          full_summary, key_points, [], [], [], [],
          sno["service"], sno["sno_reason"],
          ts, ts))

    print(f"  Created SNO lead for {sno['first']} {sno['last']} — {sno['service']}")


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT
# ─────────────────────────────────────────────────────────────────────────────
conn.commit()
print("\nAll fixes committed.")


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VERIFICATION")
print("=" * 60)

# 1. Audio coverage
cur.execute("""
    SELECT l.pipeline_stage,
           COUNT(c.id) AS total_calls,
           COUNT(c.audio_url) AS with_audio,
           COUNT(c.id) - COUNT(c.audio_url) AS missing_audio
    FROM leads l
    JOIN calls c ON c.lead_id = l.id
    WHERE l.company_id = %s
      AND c.interaction_type = 'inbound'
    GROUP BY l.pipeline_stage
    ORDER BY l.pipeline_stage
""", (CID,))
print("\nAudio coverage by stage (inbound calls):")
for r in cur.fetchall():
    flag = " *** NO AUDIO ***" if r[3] > 0 else ""
    print(f"  {r[0]:20s} | calls={r[1]:3d} | with_audio={r[2]:3d} | missing={r[3]}{flag}")

# 2. Booking status alignment
cur.execute("""
    SELECT l.pipeline_stage, ca.booking_status, COUNT(*)
    FROM leads l
    JOIN calls c ON c.lead_id = l.id
    JOIN call_analyses ca ON ca.call_id = c.id
    WHERE l.company_id = %s
      AND l.pipeline_stage IN ('qualified', 'booked', 'service_not_offered')
    GROUP BY l.pipeline_stage, ca.booking_status
    ORDER BY l.pipeline_stage, ca.booking_status
""", (CID,))
print("\nBooking-status vs pipeline-stage alignment:")
for r in cur.fetchall():
    mismatch = ""
    if r[0] == "booked" and r[1] != "booked":
        mismatch = " <-- MISMATCH"
    if r[0] == "qualified" and r[1] == "booked":
        mismatch = " <-- MISMATCH"
    if r[0] == "service_not_offered" and r[1] != "service_not_offered":
        mismatch = " <-- MISMATCH"
    print(f"  stage={r[0]:20s} | booking_status={r[1]:25s} | count={r[2]}{mismatch}")

# 3. Appointment outcomes
cur.execute("""
    SELECT l.pipeline_stage, a.outcome, COUNT(*)
    FROM leads l
    JOIN appointments a ON a.lead_id = l.id
    WHERE l.company_id = %s
      AND l.pipeline_stage IN ('appointment', 'appointment_ran', 'won', 'lost')
    GROUP BY l.pipeline_stage, a.outcome
    ORDER BY l.pipeline_stage, a.outcome
""", (CID,))
print("\nAppointment outcomes by stage:")
for r in cur.fetchall():
    print(f"  stage={r[0]:16s} | outcome={str(r[1]):8s} | count={r[2]}")

# 4. SNO count
cur.execute("""
    SELECT COUNT(*) FROM leads
    WHERE company_id = %s AND pipeline_stage = 'service_not_offered'
""", (CID,))
print(f"\nService-not-offered leads total: {cur.fetchone()[0]}")

cur.close()
conn.close()
print("\nDone.")
