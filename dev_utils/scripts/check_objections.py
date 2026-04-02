"""
Check objections data in database
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("c:/Users/abhi1/Desktop/OTTO/.env")

async def main():
    user_id = "f7c41116-884b-4f0e-be96-34046a30fd5d"
    company_id = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found in environment")
        return
    
    print(f"Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # Check objections for specific user
        print(f"\n=== Objections for User {user_id} ===")
        user_objections = await conn.fetch("""
            SELECT 
                id,
                call_id,
                category_text,
                overcome,
                created_at
            FROM call_objection_details
            WHERE user_id = $1
            AND company_id = $2
            ORDER BY created_at DESC
            LIMIT 20
        """, user_id, company_id)
        
        if not user_objections:
            print(f"NO OBJECTIONS found for user {user_id}")
        else:
            print(f"Found {len(user_objections)} objections:")
            for row in user_objections:
                print(f"\n  Objection ID: {row['id']}")
                print(f"  Category: {row['category_text']}")
                print(f"  Overcome: {row['overcome']}")
                print(f"  Created At: {row['created_at']}")
        
        # Check objections for entire company
        print(f"\n\n=== Objections for Company {company_id} ===")
        company_objections = await conn.fetch("""
            SELECT 
                user_id,
                COUNT(*) as objection_count
            FROM call_objection_details
            WHERE company_id = $1
            GROUP BY user_id
            ORDER BY objection_count DESC
            LIMIT 10
        """, company_id)
        
        if not company_objections:
            print(f"NO OBJECTIONS found for company {company_id}")
        else:
            print(f"Objections by user in company:")
            for row in company_objections:
                print(f"  User {row['user_id']}: {row['objection_count']} objections")
        
        # Count objections by company
        print(f"\n\n=== Objection Count by Company ===")
        company_counts = await conn.fetch("""
            SELECT 
                company_id,
                COUNT(*) as objection_count
            FROM call_objection_details
            GROUP BY company_id
            ORDER BY objection_count DESC
        """)
        
        for row in company_counts:
            print(f"  Company {row['company_id']}: {row['objection_count']} objections")
        
        # Check table structure
        print("\n\n=== call_objection_details Table Structure ===")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'call_objection_details'
            ORDER BY ordinal_position
        """)
        
        for col in columns:
            print(f"  {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
