"""One-off: count rehash candidates per category (with age gates).

Mirrors the eligibility SQL in app/services/rehash_service.py so the counts
upper-bound (before idempotency/noise suppression) what scan_and_sync_rehash
would create. Reads thresholds from settings/.env.

Usage:
    cd backend
    python dev_utils/scripts/count_rehash_candidates.py
    python dev_utils/scripts/count_rehash_candidates.py --company-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# backend/ is parents[2] (scripts → dev_utils → backend); the app package and
# .env live there.
_BACKEND = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND / ".env")
sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"

Q_QUALIFIED_UNBOOKED = """
SELECT COUNT(DISTINCT l.id)
FROM leads l
WHERE l.status = 'qualified_unbooked'
  AND l.pipeline_stage = 'qualified'
  AND COALESCE(l.updated_at, l.created_at) < now() - make_interval(days => $1)
  AND ($2::uuid IS NULL OR l.company_id = $2::uuid)
  AND NOT EXISTS (
    SELECT 1 FROM appointments a
    WHERE a.lead_id = l.id
      AND a.scheduled_start > now()
      AND LOWER(COALESCE(a.outcome, 'pending')) = 'pending'
  )
"""

Q_APPOINTMENT_PENDING = """
SELECT COUNT(DISTINCT l.id)
FROM leads l
JOIN appointments a ON a.lead_id = l.id
WHERE l.pipeline_stage = 'appointment_ran'
  AND LOWER(COALESCE(a.outcome, 'pending')) = 'pending'
  AND a.scheduled_start < now() - make_interval(days => $1)
  AND ($2::uuid IS NULL OR l.company_id = $2::uuid)
"""

Q_STALE_LEAD = """
WITH activity AS (
  SELECT l.id,
    GREATEST(
      COALESCE(l.updated_at, l.created_at),
      COALESCE((SELECT MAX(c.created_at) FROM calls c WHERE c.lead_id = l.id), '-infinity'::timestamptz),
      COALESCE((SELECT MAX(COALESCE(a.updated_at, a.created_at)) FROM appointments a WHERE a.lead_id = l.id), '-infinity'::timestamptz)
    ) AS last_activity
  FROM leads l
  WHERE l.pipeline_stage IN ('qualified','booked','appointment')
    AND l.status NOT IN ('closed_won','closed_lost','abandoned','dormant','qualified_service_not_offered')
    AND l.pipeline_stage NOT IN ('won','lost','service_not_offered','unqualified','review')
    AND ($2::uuid IS NULL OR l.company_id = $2::uuid)
)
SELECT COUNT(*) FROM activity WHERE last_activity < now() - make_interval(days => $1)
"""


def _normalize_asyncpg_url(url: str) -> str:
    u = url.split("?", 1)[0]
    return (
        u.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres://", "postgresql://")
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", default=None)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if "sqlite" in url.lower():
        print("DATABASE_URL is SQLite; rehash queries are defined on Postgres.")
        sys.exit(0)

    import asyncpg

    cid = args.company_id
    conn = await asyncpg.connect(_normalize_asyncpg_url(url))
    try:
        n_qu = await conn.fetchval(
            Q_QUALIFIED_UNBOOKED, settings.REHASH_QUALIFIED_UNBOOKED_DAYS, cid
        )
        n_ap = await conn.fetchval(
            Q_APPOINTMENT_PENDING, settings.REHASH_APPOINTMENT_PENDING_DAYS, cid
        )
        n_st = await conn.fetchval(
            Q_STALE_LEAD, settings.REHASH_STALE_LEAD_DAYS, cid
        )
    finally:
        await conn.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company_id": cid,
        "thresholds": {
            "qualified_unbooked_days": settings.REHASH_QUALIFIED_UNBOOKED_DAYS,
            "appointment_pending_days": settings.REHASH_APPOINTMENT_PENDING_DAYS,
            "stale_lead_days": settings.REHASH_STALE_LEAD_DAYS,
        },
        "counts": {
            "qualified_unbooked": n_qu,
            "appointment_pending": n_ap,
            "stale_lead": n_st,
            "total": (n_qu or 0) + (n_ap or 0) + (n_st or 0),
        },
    }

    print(json.dumps(report["counts"], indent=2))

    out_dir = EVIDENCE / f"rehash_counts_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "counts.json"
    out_file.write_text(json.dumps(report, indent=2))
    print(f"Evidence: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
