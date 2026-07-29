"""
Seed script: Create Apex Roofing demo company with full dummy data.
Run in phases. This is Phase 1: Company + Users + Contact Cards.
"""
import uuid
import random
import hashlib
import base64
from datetime import datetime, timedelta, timezone
import psycopg2
import psycopg2.extras
import bcrypt

DB_URL = "postgresql://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"
SOURCE_ID = "6d40b509-82bc-4d21-9614-de91cc25dc1b"

# ── Fixed new company UUID ──────────────────────────────────────────────────
COMPANY_ID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

# ── Password hashing (matches app/core/security.py) ─────────────────────────
def hash_password(plain: str) -> str:
    pre = base64.b64encode(hashlib.sha256(plain.encode()).digest()).decode()
    return bcrypt.hashpw(pre.encode(), bcrypt.gensalt()).decode()

# ── Users ────────────────────────────────────────────────────────────────────
EXEC_PASSWORD = "DemoAdmin@2026"
COMMON_PASSWORD = "ApexDemo@2026"

USERS = [
    # (first, last, email, role)
    ("Marcus", "Reynolds", "admin@demoproofing.com", "executive"),
    # CSRs
    ("Sarah",    "Mitchell",  "sarah.mitchell@apexroofing.com",   "csr"),
    ("Jennifer", "Brooks",    "jennifer.brooks@apexroofing.com",  "csr"),
    ("Ashley",   "Carter",    "ashley.carter@apexroofing.com",    "csr"),
    ("Nicole",   "Davis",     "nicole.davis@apexroofing.com",     "csr"),
    ("Rachel",   "Evans",     "rachel.evans@apexroofing.com",     "csr"),
    # Sales reps
    ("Tyler",   "Anderson",  "tyler.anderson@apexroofing.com",   "sales_rep"),
    ("Brandon", "Wilson",    "brandon.wilson@apexroofing.com",   "sales_rep"),
    ("Dylan",   "Thompson",  "dylan.thompson@apexroofing.com",   "sales_rep"),
    ("Austin",  "Martinez",  "austin.martinez@apexroofing.com",  "sales_rep"),
    ("Chase",   "Robinson",  "chase.robinson@apexroofing.com",   "sales_rep"),
]

# ── Phoenix-area customer names + phones + addresses ────────────────────────
FIRST_NAMES = [
    "James","John","Robert","Michael","William","David","Joseph","Thomas","Charles","Christopher",
    "Daniel","Matthew","Anthony","Donald","Mark","Paul","Steven","Andrew","Kenneth","George",
    "Mary","Patricia","Linda","Barbara","Elizabeth","Jennifer","Maria","Susan","Margaret","Dorothy",
    "Lisa","Nancy","Karen","Betty","Helen","Sandra","Donna","Carol","Ruth","Sharon",
    "Kevin","Brian","Edward","Ronald","Timothy","Jason","Jeffrey","Ryan","Jacob","Gary",
    "Amanda","Melissa","Deborah","Stephanie","Rebecca","Laura","Sharon","Cynthia","Kathleen","Amy",
    "Angela","Shirley","Anna","Brenda","Pamela","Emma","Nicole","Helen","Samantha","Katherine",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
    "Evans","Turner","Collins","Stewart","Morris","Murphy","Cook","Rogers","Morgan","Peterson",
]
AZ_CITIES = [
    "Phoenix", "Scottsdale", "Tempe", "Chandler", "Gilbert", "Mesa",
    "Glendale", "Peoria", "Surprise", "Avondale", "Goodyear", "Buckeye",
]
STREET_TYPES = ["St", "Ave", "Blvd", "Dr", "Ln", "Way", "Ct", "Pl", "Rd", "Circle"]
SERVICES = [
    "Roof repair", "Full roof replacement", "Shingle replacement",
    "Tile roof repair", "Flat roof repair", "Emergency roof repair",
    "Roof inspection", "Gutter repair", "Skylight installation",
    "Storm damage repair",
]

random.seed(42)

def rand_phone():
    return f"6{random.randint(0,2)}{random.randint(2,9)}{random.randint(1000000,9999999)}"

def rand_address(i):
    n = random.randint(100, 9999)
    sn = random.choice(["Main","Oak","Maple","Cedar","Pine","Elm","Park","Lake","Hill","Desert",
                        "Canyon","Sunset","Sunrise","Valley","Mountain","Palo Verde","Camelback",
                        "Scottsdale","Tempe","McDowell","Thomas","Indian School","Baseline","Ray"])
    st = random.choice(STREET_TYPES)
    city = random.choice(AZ_CITIES)
    zip_ = random.randint(85001, 85399)
    return f"{n} {sn} {st}", city, "AZ", str(zip_)

def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    psycopg2.extras.register_uuid()

    # ── 1. Company ────────────────────────────────────────────────────────────
    print("Creating company...")
    cur.execute("""
        INSERT INTO companies (id, name, phone_number, address, extra_metadata,
            reference_doc_url, sop_doc_url, csr_sop_doc_url, sales_sop_doc_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO NOTHING
    """, (
        COMPANY_ID,
        "Apex Roofing",
        "4805559100",
        "1234 N Scottsdale Rd, Suite 200, Scottsdale, AZ 85254",
        psycopg2.extras.Json({"ghost_mode_enabled": True}),
        "https://otto-documents-staging.s3.ap-southeast-2.amazonaws.com/user-onboarding-docs/anthony@arizonaroofers.com_What_types_of_appointments_to_book_.pdf.pdf",
        "https://otto-documents-staging.s3.ap-southeast-2.amazonaws.com/user-onboarding-docs/anthony@arizonaroofers.com_Intake_Calls_(3)_(1).pdf.pdf",
        "https://otto-documents-staging.s3.ap-southeast-2.amazonaws.com/user-onboarding-docs/anthony@arizonaroofers.com_Intake_Calls_(3)_(1).pdf.pdf",
        None,
    ))
    print(f"  Company ID: {COMPANY_ID}")

    # ── 2. Users ──────────────────────────────────────────────────────────────
    print("Creating users...")
    user_ids = {}
    for first, last, email, role in USERS:
        uid = str(uuid.uuid4())
        pw = EXEC_PASSWORD if role == "executive" else COMMON_PASSWORD
        h = hash_password(pw)
        cur.execute("""
            INSERT INTO users (id, email, password_hash, role, is_active, first_name, last_name, company_id, extra_metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id
        """, (uid, email, h, role, True, first, last, COMPANY_ID, psycopg2.extras.Json({})))
        row = cur.fetchone()
        if row:
            user_ids[email] = row[0]
        else:
            # Already exists — fetch
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            r = cur.fetchone()
            if r:
                user_ids[email] = r[0]
        print(f"  {role}: {first} {last} <{email}> -> {user_ids.get(email)}")

    conn.commit()

    # ── 3. Contact Cards (~200 customers) ─────────────────────────────────────
    print("Creating contact cards...")
    contact_cards = []
    used_phones = set()
    for i in range(200):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        phone = rand_phone()
        while phone in used_phones:
            phone = rand_phone()
        used_phones.add(phone)
        addr, city, state, zip_ = rand_address(i)
        cc_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO contact_cards
              (id, company_id, primary_phone, email, first_name, last_name,
               address, city, state, postal_code)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            cc_id, COMPANY_ID, phone,
            f"{fn.lower()}.{ln.lower()}@gmail.com",
            fn, ln, addr, city, state, zip_
        ))
        contact_cards.append({
            "id": cc_id, "phone": phone, "name": f"{fn} {ln}",
            "address": f"{addr}, {city}, {state} {zip_}"
        })

    conn.commit()
    print(f"  Created {len(contact_cards)} contact cards")

    # ── Save user_ids and contact_cards for next phase ────────────────────────
    import json, os
    state_path = os.path.join(os.path.dirname(__file__), "apex_seed_state.json")
    with open(state_path, "w") as f:
        json.dump({
            "company_id": COMPANY_ID,
            "user_ids": {k: str(v) for k, v in user_ids.items()},
            "contact_cards": contact_cards,
        }, f, indent=2)
    print(f"\nState saved to {state_path}")
    print(f"\nPhase 1 complete. Company: {COMPANY_ID}")
    print(f"  Login: admin@demoproofing.com / {EXEC_PASSWORD}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
