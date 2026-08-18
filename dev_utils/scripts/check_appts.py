import psycopg2, json
db = "postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"
import sys
calls = ["2e0a2fc2-95c5-4464-a2a8-ae8d3f2e6bf2","2c989fd8-e8ac-492c-8f90-d1bbbc5d38ef"]
conn = None
try:
    conn = psycopg2.connect(db)
    cur = conn.cursor()
    for c in calls:
        cur.execute("SELECT id, lead_id, contact_card_id, scheduled_start, extra_metadata FROM appointments WHERE extra_metadata->>'created_from_call' = %s", (c,))
        rows = cur.fetchall()
        print('CALL', c)
        if not rows:
            print('  No appointment found')
        else:
            for r in rows:
                print('  appt_id:', r[0], 'lead_id:', r[1], 'contact_card_id:', r[2], 'scheduled_start:', str(r[3]), 'extra:', json.dumps(r[4]))
except Exception as e:
    print('db_error', e)
finally:
    if conn:
        conn.close()
