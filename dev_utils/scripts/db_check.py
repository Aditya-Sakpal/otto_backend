import psycopg2, json
from datetime import datetime, timedelta

db = "***DB_URL_REMOVED***"
company = '6d40b509-82bc-4d21-9614-de91cc25dc1b'
start_date = (datetime.utcnow() - timedelta(days=30)).date().isoformat()
end_date = datetime.utcnow().date().isoformat()
start_ts = start_date + ' 00:00:00'
end_ts = end_date + ' 23:59:59'
conn = None
try:
    conn = psycopg2.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(deal_size),0) FROM leads WHERE company_id=%s AND deal_size IS NOT NULL AND deal_size>0 AND (status='closed_won' OR LOWER(COALESCE(deal_status,''))='won') AND (closed_at BETWEEN %s AND %s OR updated_at BETWEEN %s AND %s)", (company, start_ts, end_ts, start_ts, end_ts))
    rev = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(AVG(deal_size),0) FROM leads WHERE company_id=%s AND deal_size IS NOT NULL AND deal_size>0 AND (status='closed_won' OR LOWER(COALESCE(deal_status,''))='won') AND (closed_at BETWEEN %s AND %s OR updated_at BETWEEN %s AND %s)", (company, start_ts, end_ts, start_ts, end_ts))
    avg = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(COUNT(id),0) FROM calls WHERE company_id=%s AND created_at BETWEEN %s AND %s", (company, start_ts, end_ts))
    calls = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END),0), COALESCE(COUNT(id),0) FROM appointments WHERE company_id=%s AND scheduled_start BETWEEN %s AND %s", (company, start_ts, end_ts))
    won,total = cur.fetchone()
    result = {'sql_revenue': float(rev or 0), 'sql_avg_deal': float(avg or 0), 'sql_calls': int(calls or 0), 'appt_won': int(won or 0), 'appt_total': int(total or 0), 'start_date': start_date, 'end_date': end_date}
    print(json.dumps(result, indent=2))
except Exception as e:
    print('db_error', str(e))
finally:
    if conn:
        conn.close()
