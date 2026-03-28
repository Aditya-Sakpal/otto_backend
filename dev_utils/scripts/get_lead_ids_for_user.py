"""
Fetch lead IDs related to a given user_id (sales rep / CSR).

Tries common relationships:
- leads.assigned_agent_id / leads.assigned_to_user_id / leads.owner_id (if present)
- calls.handled_by_user_id -> calls.lead_id (if present)

Prints a small set of candidate lead IDs for debugging/testing.
"""

import asyncio
import os
from uuid import UUID

import asyncpg
from dotenv import load_dotenv


USER_ID = "38dc7d9f-2935-416a-8fb9-2f929da8c0ab"


async def _table_has_column(conn: asyncpg.Connection, table: str, column: str) -> bool:
    val = await conn.fetchval(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = $1 AND column_name = $2
        LIMIT 1
        """,
        table,
        column,
    )
    return val == 1


async def main() -> None:
    load_dotenv("c:/Users/abhi1/Desktop/OTTO/.env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    # Validate UUID early
    UUID(USER_ID)

    conn = await asyncpg.connect(database_url)
    try:
        print(f"User ID: {USER_ID}")
        # quick sanity: does this user exist?
        if await _table_has_column(conn, "users", "id"):
            exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1 LIMIT 1", USER_ID)
            print(f"User exists in users table: {bool(exists)}")

        # 1) Look for direct lead assignment columns
        lead_cols_to_try = [
            "assigned_agent_id",
            "assigned_to_user_id",
            "handled_by_user_id",
            "owner_id",
            "user_id",
        ]

        direct_queries = []
        for col in lead_cols_to_try:
            if await _table_has_column(conn, "leads", col):
                direct_queries.append(
                    (
                        col,
                        f"SELECT DISTINCT id::text AS lead_id FROM leads WHERE {col} = $1 LIMIT 50",
                    )
                )

        if direct_queries:
            print("\n== Leads table direct mappings ==")
            for col, sql in direct_queries:
                rows = await conn.fetch(sql, USER_ID)
                lead_ids = [r["lead_id"] for r in rows]
                print(f"- leads.{col}: {len(lead_ids)} lead(s)")
                for lid in lead_ids[:10]:
                    print(f"  {lid}")
        else:
            print("\n== Leads table direct mappings ==")
            print("- No known assignment columns found on leads table (checked common names).")

        # 2) Look for calls -> lead relationship (common in call-centric systems)
        if await _table_has_column(conn, "calls", "handled_by_user_id") and await _table_has_column(
            conn, "calls", "lead_id"
        ):
            print("\n== Calls -> lead_id mapping ==")
            rows = await conn.fetch(
                """
                SELECT DISTINCT lead_id::text AS lead_id
                FROM calls
                WHERE handled_by_user_id = $1
                  AND lead_id IS NOT NULL
                ORDER BY lead_id
                LIMIT 50
                """,
                USER_ID,
            )
            lead_ids = [r["lead_id"] for r in rows]
            print(f"- calls.handled_by_user_id -> calls.lead_id: {len(lead_ids)} lead(s)")
            for lid in lead_ids[:10]:
                print(f"  {lid}")
        else:
            print("\n== Calls -> lead_id mapping ==")
            print("- calls.lead_id or calls.handled_by_user_id not present; skipping.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

