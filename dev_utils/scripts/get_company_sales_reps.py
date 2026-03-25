"""Get sales rep IDs for a specific company."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("c:/Users/abhi1/Desktop/OTTO/.env"))

url = os.getenv("DATABASE_URL", "")
if not url:
    print("DATABASE_URL not set")
    raise SystemExit(1)

import asyncpg

u = url.split("?", 1)[0]
u = u.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

QUERY = """
SELECT id, first_name, last_name, email, role, company_id
FROM users
WHERE role = 'sales_rep' 
  AND company_id = $1
LIMIT 10
"""

async def main():
    company_id = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"
    conn = await asyncpg.connect(u)
    try:
        rows = await conn.fetch(QUERY, company_id)
        if not rows:
            print(f"No sales reps found for company {company_id}")
            return
        print(f"Sales Reps for company {company_id}:")
        print()
        for row in rows:
            print(f"  ID: {row['id']}")
            print(f"  Name: {row['first_name']} {row['last_name']}")
            print(f"  Email: {row['email']}")
            print()
    finally:
        await conn.close()

asyncio.run(main())
