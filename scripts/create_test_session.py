import os
import uuid
import psycopg2

db_url = os.environ.get("DATABASE_URL")

if not db_url:
    db_url = "***DB_URL_REMOVED***"

try:
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # 1. Fetch reference records required for the session context
    cursor.execute("SELECT id FROM users LIMIT 1;")
    user_row = cursor.fetchone()
    rep_user_id = user_row[0]
    print(f"Using representative user ID: {rep_user_id}")

    cursor.execute("SELECT id FROM companies LIMIT 1;")
    company_row = cursor.fetchone()
    company_id = company_row[0]
    print(f"Using company ID: {company_id}")

    cursor.execute("SELECT id FROM leads LIMIT 1;")
    lead_row = cursor.fetchone()
    lead_id = lead_row[0]
    print(f"Using lead ID: {lead_id}")

    cursor.execute("SELECT id FROM proxy_numbers LIMIT 1;")
    proxy_num_row = cursor.fetchone()
    proxy_id = proxy_num_row[0]
    print(f"Using proxy number ID: {proxy_id}")

    # 2. Deactivate conflicting active sessions to maintain unique constraint integrity
    cursor.execute(
        "UPDATE proxy_sessions SET status = 'closed' WHERE lead_id = %s AND rep_user_id = %s;",
        (lead_id, rep_user_id)
    )
    conn.commit()
    print("Successfully resolved active proxy session conflicts.")

    # 3. Initialize fresh session configuration parameters
    session_id = str(uuid.uuid4())
    homeowner_phone = "+91XXXXXXXXXX"  # Define target homeowner phone number here
    rep_phone = "+91YYYYYYYYYY"        # Define target representative phone number here

    # 4. Insert the new active session record
    query = """
    INSERT INTO proxy_sessions 
    (id, lead_id, proxy_number_id, rep_user_id, company_id, homeowner_phone, rep_phone, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'active');
    """
    
    cursor.execute(query, (session_id, lead_id, proxy_id, rep_user_id, company_id, homeowner_phone, rep_phone))
    conn.commit()
    
    print("\nSession record inserted successfully.")
    print(f"Generated Session ID: {session_id}")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"\nExecution failed: {e}")