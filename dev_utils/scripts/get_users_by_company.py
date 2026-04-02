"""
Get users for a specific company
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("c:/Users/abhi1/Desktop/OTTO/.env")

async def main():
    company_id = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found in environment")
        return
    
    print(f"Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # Get users for this company
        rows = await conn.fetch("""
            SELECT 
                id,
                first_name,
                last_name,
                email,
                role,
                is_active
            FROM users
            WHERE company_id = $1
            ORDER BY created_at DESC
            LIMIT 10
        """, company_id)
        
        print(f"\nUsers for company {company_id}:")
        print("-" * 100)
        
        if not rows:
            print("No users found for this company")
        else:
            for row in rows:
                print(f"User ID: {row['id']}")
                print(f"  Name: {row['first_name']} {row['last_name']}")
                print(f"  Email: {row['email']}")
                print(f"  Role: {row['role']}")
                print(f"  Active: {row['is_active']}")
                print("-" * 100)
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
