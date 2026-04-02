"""
Fetch lead IDs for a given company_id.
"""

import asyncio
import os
from uuid import UUID

import asyncpg
from dotenv import load_dotenv


COMPANY_ID = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"


async def main() -> None:
    load_dotenv("c:/Users/abhi1/Desktop/OTTO/.env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    UUID(COMPANY_ID)

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT id::text AS lead_id, created_at, updated_at, status, pipeline_stage
            FROM leads
            WHERE company_id = $1
            ORDER BY created_at DESC
            LIMIT 10
            """,
            COMPANY_ID,
        )

        if not rows:
            print(f"No leads found for company_id={COMPANY_ID}")
            return

        print(f"Leads for company_id={COMPANY_ID} (showing up to 10, newest first):")
        for r in rows:
            print(
                f"- {r['lead_id']}  status={r['status']}  stage={r['pipeline_stage']}  created_at={r['created_at']}"
            )

        print("\nUse this lead_id for testing (newest):")
        print(rows[0]["lead_id"])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

