"""
Check coaching sessions for Arizona Roofers company
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
        # Check coaching sessions for this company
        print(f"\n=== Coaching Sessions for Company {company_id} ===")
        sessions = await conn.fetch("""
            SELECT 
                id,
                rep_user_id,
                coach_user_id,
                status,
                coached_at,
                focus_areas,
                baseline_scores,
                impact_scores,
                overall_improved,
                improvement_pct,
                created_at
            FROM coaching_sessions
            WHERE company_id = $1
            ORDER BY coached_at DESC
        """, company_id)
        
        if not sessions:
            print(f"\nNO COACHING SESSIONS FOUND for company {company_id}")
        else:
            print(f"\nFound {len(sessions)} coaching sessions:")
            for row in sessions:
                print(f"\n  Session ID: {row['id']}")
                print(f"  Rep User ID: {row['rep_user_id']}")
                print(f"  Coach User ID: {row['coach_user_id']}")
                print(f"  Status: {row['status']}")
                print(f"  Coached At: {row['coached_at']}")
                print(f"  Focus Areas: {row['focus_areas']}")
        
        # Count sessions by company
        print(f"\n\n=== Session Count by Company ===")
        company_counts = await conn.fetch("""
            SELECT 
                company_id,
                COUNT(*) as session_count
            FROM coaching_sessions
            GROUP BY company_id
            ORDER BY session_count DESC
        """)
        
        for row in company_counts:
            print(f"  Company {row['company_id']}: {row['session_count']} sessions")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
