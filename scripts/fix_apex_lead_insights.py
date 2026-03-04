"""
Fix Lead Insights page for Apex Roofing:
1. Populate call_analyses.objections arrays (Top Objections)
2. Create hot/warm/new leads (Queued Leads Ready for Booking)
3. Link missed calls to leads (Missed Calls Recovery Overview)
"""
import uuid, random, psycopg2, psycopg2.extras
from datetime import datetime, timedelta, timezone

DB  = "postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"
CID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

random.seed(99)
now = datetime.now(timezone.utc)

CSR_IDS = [
    "2a6bd9e5-92e5-42ed-bfd3-9002ae099bff",  # sarah
    "e46de9cf-ab56-4fb7-8c21-94f899bb7d3f",  # jennifer
    "9e75eab4-4c80-4b65-b8ba-75520d44968e",  # ashley
    "4489ccb2-be79-415a-9545-c757d0fa649f",  # nicole
    "69e19f27-d18e-42f1-97c9-5e9a63a390b1",  # rachel
]

conn = psycopg2.connect(DB)
conn.autocommit = False
cur = conn.cursor()
psycopg2.extras.register_uuid()

# ── FIX 1: Populate call_analyses.objections ───────────────────────────────────
# Distribution: ~60% price, 15% timing, 10% competition, 10% trust, 5% need
OBJECTION_POOL = (
    ["price"] * 60 +
    ["timing"] * 15 +
    ["competition"] * 10 +
    ["trust"] * 10 +
    ["need"] * 5
)
OBJECTION_TEXTS = {
    "price":       ["Price is too high", "Can't afford it right now", "Need a cheaper option",
                    "Got a lower quote elsewhere", "Need payment plan options"],
    "timing":      ["Not ready until next month", "Need to wait for insurance payout",
                    "Scheduling conflicts", "Too busy right now"],
    "competition": ["Getting another estimate first", "Friend recommended another company",
                    "Already have a contractor in mind"],
    "trust":       ["Need to verify your reviews", "Want to check references first",
                    "Concerned about warranty"],
    "need":        ["Not sure I need full replacement", "Just want an inspection for now"],
}

# Get call_analyses IDs that have empty objections (not_booked calls first, then all)
cur.execute("""
    SELECT ca.id, ca.booking_status
    FROM call_analyses ca
    JOIN calls c ON c.id = ca.call_id
    WHERE c.company_id = %s
      AND (ca.objections IS NULL OR array_length(ca.objections, 1) IS NULL)
    ORDER BY CASE WHEN ca.booking_status='not_booked' THEN 0 ELSE 1 END,
             ca.created_at DESC
""", (CID,))
analysis_rows = cur.fetchall()
print(f"call_analyses with empty objections: {len(analysis_rows)}")

# Populate objections for ~70% of not_booked, ~20% of booked
updated = 0
for analysis_id, booking_status in analysis_rows:
    is_not_booked = (booking_status == 'not_booked')
    # 70% of not_booked calls get objections, 20% of booked calls
    if is_not_booked and random.random() > 0.70:
        continue
    if not is_not_booked and random.random() > 0.20:
        continue

    # Pick 1-2 objections
    num_obj = random.choices([1, 2], weights=[75, 25])[0]
    chosen = random.sample(OBJECTION_POOL, num_obj)
    chosen = list(dict.fromkeys(chosen))  # deduplicate, preserve order

    obj_texts = []
    for obj in chosen:
        obj_texts.append(random.choice(OBJECTION_TEXTS[obj]))

    cur.execute("""
        UPDATE call_analyses
        SET objections          = %s::text[],
            objection_texts     = %s::text[],
            objections_total_count = %s
        WHERE id = %s
    """, (chosen, obj_texts, len(chosen), analysis_id))
    updated += 1

print(f"Updated {updated} call_analyses with objections")

# ── FIX 2: Create hot/warm/new queued leads ────────────────────────────────────
# get_auto_queued_leads queries leads with status IN ('hot','warm','new') in last 30 days
# Grab unused contact cards
cur.execute("""
    SELECT id, first_name, last_name, primary_phone, address, city, state, postal_code
    FROM contact_cards
    WHERE company_id = %s
      AND id NOT IN (SELECT DISTINCT contact_card_id FROM leads WHERE company_id=%s AND contact_card_id IS NOT NULL)
    LIMIT 30
""", (CID, CID))
free_contacts = cur.fetchall()
print(f"Free contact cards for queued leads: {len(free_contacts)}")

SERVICES = [
    "Roof Repair", "Emergency Roof Repair", "Storm Damage Repair",
    "Roof Inspection", "Shingle Replacement", "Flat Roof Repair",
    "Gutter Repair", "Tile Roof Repair",
]

queued_created = 0
for i, (cc_id, fn, ln, phone, addr, city, state, zip_) in enumerate(free_contacts[:25]):
    if i < 8:
        status = "hot"
    elif i < 18:
        status = "warm"
    else:
        status = "new"

    days_ago = random.randint(1, 25)
    created_at = now - timedelta(days=days_ago, hours=random.randint(0, 12))
    service_req = random.choice(SERVICES)

    lead_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO leads
          (id, company_id, contact_card_id, status, pipeline_stage, deal_size,
           extra_metadata, created_at, updated_at)
        VALUES (%s,%s,%s,%s,'qualified',%s,%s,%s,%s)
    """, (
        lead_id, CID, cc_id, status, random.randint(3000, 22000),
        psycopg2.extras.Json({"service_requested": service_req}), created_at, created_at
    ))
    queued_created += 1

print(f"Created {queued_created} hot/warm/new queued leads")

# ── FIX 3: Link missed calls to leads (Missed Calls Recovery) ─────────────────
# Total Missed Calls = missed_call=True in last 30 days
# Calls Picked Up    = missed_call=True AND lead_id IS NOT NULL
# Calls Booked       = picked-up calls whose lead.status = 'qualified_booked'

# Get missed calls from last 30 days that have no lead
cur.execute("""
    SELECT id, contact_card_id FROM calls
    WHERE company_id = %s
      AND missed_call = true
      AND lead_id IS NULL
      AND created_at >= NOW() - INTERVAL '30 days'
    ORDER BY created_at DESC
    LIMIT 35
""", (CID,))
missed_calls = cur.fetchall()
print(f"Unlinked missed calls in last 30 days: {len(missed_calls)}")

# Target: 34 missed, 28 picked up (82%), 23 booked (82% of picked up)
target_picked_up = min(28, len(missed_calls))
target_booked    = 23

linked = 0
booked_count = 0
for i, (call_id, cc_id) in enumerate(missed_calls[:target_picked_up]):
    lead_id = str(uuid.uuid4())
    lead_status = "qualified_booked" if booked_count < target_booked else "qualified_unbooked"
    pipeline_stage = "booked" if lead_status == "qualified_booked" else "qualified"
    created_at = now - timedelta(days=random.randint(0, 25), hours=random.randint(1, 10))

    cur.execute("""
        INSERT INTO leads
          (id, company_id, contact_card_id, status, pipeline_stage, deal_size,
           extra_metadata, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        lead_id, CID, cc_id, lead_status, pipeline_stage,
        random.randint(3000, 18000),
        psycopg2.extras.Json({"service_requested": random.choice(SERVICES)}),
        created_at, created_at
    ))

    # Link the missed call back to this lead
    cur.execute("UPDATE calls SET lead_id=%s WHERE id=%s", (lead_id, call_id))
    linked += 1
    if lead_status == "qualified_booked":
        booked_count += 1

print(f"Linked {linked} missed calls to leads ({booked_count} booked)")

conn.commit()

# ── Verify ─────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION ===")

# Objections
cur.execute("""
    SELECT unnest(ca.objections) as obj, COUNT(*) as cnt
    FROM call_analyses ca
    JOIN calls c ON c.id=ca.call_id
    WHERE c.company_id=%s AND array_length(ca.objections,1)>0
    GROUP BY obj ORDER BY cnt DESC LIMIT 6
""", (CID,))
print("Top objection types:")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

# Queued leads
cur.execute("""
    SELECT status, COUNT(*) FROM leads WHERE company_id=%s AND status IN ('hot','warm','new')
    AND created_at >= NOW() - INTERVAL '30 days'
    GROUP BY status
""", (CID,))
print("Queued leads (hot/warm/new):")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

# Missed calls recovery
cur.execute("SELECT COUNT(*) FROM calls WHERE company_id=%s AND missed_call=true AND created_at>=NOW()-INTERVAL '30 days'", (CID,))
total_missed = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM calls WHERE company_id=%s AND missed_call=true AND lead_id IS NOT NULL AND created_at>=NOW()-INTERVAL '30 days'", (CID,))
picked_up = cur.fetchone()[0]
cur.execute("""
    SELECT COUNT(*) FROM calls c JOIN leads l ON l.id=c.lead_id
    WHERE c.company_id=%s AND c.missed_call=true AND l.status='qualified_booked'
    AND c.created_at>=NOW()-INTERVAL '30 days'
""", (CID,))
booked_final = cur.fetchone()[0]
print(f"Missed Calls Recovery: total={total_missed}, picked_up={picked_up}, booked={booked_final}, pct={round(booked_final/total_missed*100) if total_missed else 0}%")

cur.close()
conn.close()
print("\nDone.")
