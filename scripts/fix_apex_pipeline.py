"""
Fix Apex Roofing demo data:
1. Boost booking rate to ~72% by converting some qualified_unbooked -> qualified_booked
2. Set pipeline_stage on all leads so pipeline board is populated
"""
import psycopg2, psycopg2.extras

DB = "postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"
CID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

conn = psycopg2.connect(DB)
conn.autocommit = False
cur = conn.cursor()

# ── Step 1: Convert qualified_unbooked → qualified_booked (last 30 days) ──────
# Current: 64 qualified_booked, 74 qualified_unbooked (138 total)
# Target:  99 qualified_booked, 39 qualified_unbooked → 99/138 = 71.7% ≈ 72%
cur.execute("""
    UPDATE leads
    SET status = 'qualified_booked',
        updated_at = updated_at   -- preserve existing timestamp
    WHERE id IN (
        SELECT id FROM leads
        WHERE company_id = %s
          AND status = 'qualified_unbooked'
          AND created_at >= NOW() - INTERVAL '30 days'
        ORDER BY created_at DESC
        LIMIT 35
    )
""", (CID,))
print(f"Converted {cur.rowcount} qualified_unbooked -> qualified_booked")

# ── Step 2: Set pipeline_stage for ALL leads based on final status ─────────────
# Pipeline stage mapping:
#   abandoned           -> 'unqualified'
#   qualified_unbooked  -> 'qualified'
#   qualified_booked    -> 'booked'
#   closed_won          -> 'won'
#   closed_lost         -> 'lost'
stage_map = [
    ("abandoned",           "unqualified"),
    ("qualified_unbooked",  "qualified"),
    ("qualified_booked",    "booked"),
    ("closed_won",          "won"),
    ("closed_lost",         "lost"),
]
for status, stage in stage_map:
    cur.execute("""
        UPDATE leads SET pipeline_stage = %s
        WHERE company_id = %s AND status = %s
    """, (stage, CID, status))
    print(f"  Set pipeline_stage='{stage}' for {cur.rowcount} leads (status='{status}')")

# ── Step 3: Mark leads with upcoming appointments as 'appointment' stage ───────
# These are leads linked to appointments with NULL outcome (scheduled but not yet run)
cur.execute("""
    UPDATE leads l
    SET pipeline_stage = 'appointment'
    WHERE l.company_id = %s
      AND l.pipeline_stage = 'booked'
      AND EXISTS (
          SELECT 1 FROM appointments a
          WHERE a.lead_id = l.id
            AND a.outcome IS NULL
            AND a.scheduled_start >= NOW() - INTERVAL '1 day'
      )
""", (CID,))
print(f"  Set pipeline_stage='appointment' for {cur.rowcount} leads (upcoming appts)")

conn.commit()

# ── Verify ─────────────────────────────────────────────────────────────────────
cur.execute("""
    SELECT pipeline_stage, COUNT(*)
    FROM leads WHERE company_id=%s
    GROUP BY pipeline_stage
    ORDER BY COUNT(*) DESC
""", (CID,))
print("\n=== PIPELINE STAGES AFTER FIX ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

cur.execute("""
    SELECT
        COUNT(*) FILTER(WHERE status IN ('qualified_booked','qualified_unbooked')) as total_qualified,
        COUNT(*) FILTER(WHERE status = 'qualified_booked') as booked,
        ROUND(
            COUNT(*) FILTER(WHERE status = 'qualified_booked')::numeric /
            NULLIF(COUNT(*) FILTER(WHERE status IN ('qualified_booked','qualified_unbooked')), 0) * 100
        , 2) as booking_rate
    FROM leads
    WHERE company_id=%s AND created_at >= NOW() - INTERVAL '30 days'
""", (CID,))
r = cur.fetchone()
print(f"\n=== BOOKING RATE (last 30 days) ===")
print(f"  Total qualified: {r[0]}, Booked: {r[1]}, Rate: {r[2]}%")

cur.close()
conn.close()
print("\nDone.")
