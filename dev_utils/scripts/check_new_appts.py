import psycopg2, json
DB='***DB_URL_REMOVED***'
calls=['1dae8cf7-8e41-483f-9a2d-7cfbe9b10774','91993279-2b2a-47cd-8eae-9fd9b523b6fe']
conn = psycopg2.connect(DB)
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
conn.close()
