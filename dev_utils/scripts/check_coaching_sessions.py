"""
Check coaching sessions in database
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
        # Check all coaching sessions
        print("\n=== All Coaching Sessions ===")
        all_sessions = await conn.fetch("""
            SELECT 
                id,
                company_id,
                rep_user_id,
                coach_user_id,
                status,
                coached_at,
                created_at
            FROM coaching_sessions
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        if not all_sessions:
            print("No coaching sessions found in database at all")
        else:
            print(f"Found {len(all_sessions)} total coaching sessions:")
            for row in all_sessions:
                print(f"\n  Session ID: {row['id']}")
                print(f"  Company ID: {row['company_id']}")
                print(f"  Rep User ID: {row['rep_user_id']}")
                print(f"  Status: {row['status']}")
                print(f"  Coached At: {row['coached_at']}")
        
        # Check for specific user
        print(f"\n\n=== Coaching Sessions for User {user_id} ===")
        user_sessions = await conn.fetch("""
            SELECT 
                id,
                company_id,
                rep_user_id,
                coach_user_id,
                status,
                coached_at,
                focus_areas,
                targets,
                baseline_scores,
                impact_scores,
                overall_improved,
                improvement_pct,
                follow_up_days,
                follow_up_end_date
            FROM coaching_sessions
            WHERE rep_user_id = $1
            AND company_id = $2
            ORDER BY coached_at DESC
        """, user_id, company_id)
        
        if not user_sessions:
            print(f"No coaching sessions found for user {user_id} in company {company_id}")
        else:
            print(f"Found {len(user_sessions)} coaching sessions:")
            for row in user_sessions:
                print(f"\n  Session ID: {row['id']}")
                print(f"  Status: {row['status']}")
                print(f"  Coached At: {row['coached_at']}")
                print(f"  Focus Areas: {row['focus_areas']}")
                print(f"  Baseline Scores: {row['baseline_scores']}")
                print(f"  Impact Scores: {row['impact_scores']}")
                print(f"  Overall Improved: {row['overall_improved']}")
                print(f"  Improvement %: {row['improvement_pct']}")
        
        # Check table structure
        print("\n\n=== Coaching Sessions Table Structure ===")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'coaching_sessions'
            ORDER BY ordinal_position
        """)
        
        for col in columns:
            print(f"  {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
