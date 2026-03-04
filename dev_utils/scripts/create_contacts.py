import psycopg2, uuid
from datetime import datetime
DB='postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n'
conn = psycopg2.connect(DB)
cur = conn.cursor()
company='6d40b509-82bc-4d21-9614-de91cc25dc1b'
phones=['+15550000001','+15550000002']
ids=[]
for p in phones:
    cid=str(uuid.uuid4())
    cur.execute("INSERT INTO contact_cards (id, company_id, primary_phone, first_name, last_name, extra_metadata) VALUES (%s,%s,%s,%s,%s,%s)", (cid, company, p, 'Test','User', None))
    ids.append(cid)
conn.commit()
cur.close()
conn.close()
print(ids)
