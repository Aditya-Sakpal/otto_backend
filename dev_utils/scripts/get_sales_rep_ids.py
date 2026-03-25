"""Get sales rep IDs for testing."""
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
SELECT id, first_name, last_name, email, role
FROM users
WHERE role = 'sales_rep'
LIMIT 5
"""

async def main():
    conn = await asyncpg.connect(u)
    try:
        rows = await conn.fetch(QUERY)
        if not rows:
            print("No sales reps found")
            return
        print("Sales Reps:")
        for row in rows:
            print(f"  ID: {row['id']}")
            print(f"  Name: {row['first_name']} {row['last_name']}")
            print(f"  Email: {row['email']}")
            print()
    finally:
        await conn.close()

asyncio.run(main())
