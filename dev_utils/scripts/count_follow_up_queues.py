"""One-off: count leads matching contextual follow-up scanners (Q1 + Q2)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")

Q1 = """
SELECT COUNT(*) AS n
FROM leads l
JOIN contact_cards cc ON l.contact_card_id = cc.id
JOIN companies co ON l.company_id = co.id
WHERE l.pipeline_stage = 'qualified'
  AND l.status = 'qualified_unbooked'
"""

Q2 = """
SELECT COUNT(*) AS n
FROM leads l
JOIN appointments a ON a.lead_id = l.id
JOIN contact_cards cc ON l.contact_card_id = cc.id
JOIN companies co ON l.company_id = co.id
WHERE l.pipeline_stage = 'appointment_ran'
  AND (a.outcome IS NULL OR a.outcome NOT IN ('won', 'lost'))
"""


def _normalize_asyncpg_url(url: str) -> str:
    u = url.split("?", 1)[0]
    return (
        u.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres://", "postgresql://")
    )


async def main() -> None:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if "sqlite" in url.lower():
        print("DATABASE_URL is SQLite; these queues are defined on Postgres.")
        sys.exit(0)

    import asyncpg

    conn = await asyncpg.connect(_normalize_asyncpg_url(url))
    try:
        n1 = await conn.fetchval(Q1)
        n2 = await conn.fetchval(Q2)
        print("Queue 1 (qualified + qualified_unbooked):", n1)
        print("Queue 2 (appointment_ran + open appointment rows):", n2)
        print("Total work items per orchestrator run:", n1 + n2)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
