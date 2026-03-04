"""
Backfill script: Populate coaching_issues, coaching_strengths, and call_objection_details
from existing call_analyses.raw_analysis JSON data.

Usage:
    python backfill_coaching_data.py

Requires DATABASE_URL environment variable or .env file.
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


async def backfill():
    db_url = settings.DATABASE_URL
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    # Normalize URL for async
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False, connect_args={"timeout": 120})
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # =====================================================================
        # 1. Backfill coaching_issues using pure SQL with json_array_elements
        # =====================================================================
        print("Backfilling coaching_issues...", flush=True)
        issues_result = await session.execute(text("""
            INSERT INTO coaching_issues
                (id, call_analysis_id, call_id, company_id, user_id, issue, severity,
                 why_it_matters, how_to_fix, example_language, transcript_evidence, related_sop_metric)
            SELECT
                gen_random_uuid(),
                ca.id,
                ca.call_id,
                ca.company_id,
                c.handled_by_user_id,
                elem->>'issue',
                COALESCE(elem->>'severity', 'medium'),
                elem->>'why_it_matters',
                elem->>'how_to_fix',
                elem->>'example_language',
                elem->>'transcript_evidence',
                elem->>'related_sop_metric'
            FROM call_analyses ca
            JOIN calls c ON c.id = ca.call_id
            CROSS JOIN LATERAL json_array_elements(
                ca.raw_analysis->'compliance'->'sop_compliance'->'coaching_issues'
            ) AS elem
            WHERE ca.raw_analysis IS NOT NULL
            AND ca.status = 'completed'
            AND json_array_length(
                COALESCE(ca.raw_analysis->'compliance'->'sop_compliance'->'coaching_issues', '[]'::json)
            ) > 0
            AND (elem->>'issue') IS NOT NULL
            AND (elem->>'issue') != ''
            AND ca.id NOT IN (SELECT DISTINCT call_analysis_id FROM coaching_issues)
        """))
        issues_count = issues_result.rowcount
        print(f"  Inserted {issues_count} coaching issues", flush=True)

        # =====================================================================
        # 2. Backfill coaching_strengths
        # =====================================================================
        print("Backfilling coaching_strengths...", flush=True)
        strengths_result = await session.execute(text("""
            INSERT INTO coaching_strengths
                (id, call_analysis_id, call_id, company_id, user_id, behavior,
                 why_effective, transcript_evidence, related_sop_metric)
            SELECT
                gen_random_uuid(),
                ca.id,
                ca.call_id,
                ca.company_id,
                c.handled_by_user_id,
                elem->>'behavior',
                elem->>'why_effective',
                elem->>'transcript_evidence',
                elem->>'related_sop_metric'
            FROM call_analyses ca
            JOIN calls c ON c.id = ca.call_id
            CROSS JOIN LATERAL json_array_elements(
                ca.raw_analysis->'compliance'->'sop_compliance'->'coaching_strengths'
            ) AS elem
            WHERE ca.raw_analysis IS NOT NULL
            AND ca.status = 'completed'
            AND json_array_length(
                COALESCE(ca.raw_analysis->'compliance'->'sop_compliance'->'coaching_strengths', '[]'::json)
            ) > 0
            AND (elem->>'behavior') IS NOT NULL
            AND (elem->>'behavior') != ''
            AND ca.id NOT IN (SELECT DISTINCT call_analysis_id FROM coaching_strengths)
        """))
        strengths_count = strengths_result.rowcount
        print(f"  Inserted {strengths_count} coaching strengths", flush=True)

        # =====================================================================
        # 3. Backfill call_objection_details
        # =====================================================================
        print("Backfilling call_objection_details...", flush=True)
        objections_result = await session.execute(text("""
            INSERT INTO call_objection_details
                (id, call_analysis_id, call_id, company_id, user_id, category_id,
                 category_text, objection_text, overcome, severity, confidence_score)
            SELECT
                gen_random_uuid(),
                ca.id,
                ca.call_id,
                ca.company_id,
                c.handled_by_user_id,
                CASE WHEN (elem->>'category_id') ~ '^\d+$'
                     THEN (elem->>'category_id')::integer
                     ELSE NULL END,
                COALESCE(elem->>'category_text', elem->>'category', 'Other'),
                elem->>'objection_text',
                COALESCE((elem->>'overcome')::boolean, false),
                elem->>'severity',
                CASE WHEN (elem->>'confidence_score') ~ '^\d+\.?\d*$'
                     THEN (elem->>'confidence_score')::double precision
                     ELSE NULL END
            FROM call_analyses ca
            JOIN calls c ON c.id = ca.call_id
            CROSS JOIN LATERAL json_array_elements(
                ca.raw_analysis->'objections'->'objections'
            ) AS elem
            WHERE ca.raw_analysis IS NOT NULL
            AND ca.status = 'completed'
            AND json_typeof(ca.raw_analysis->'objections') = 'object'
            AND json_array_length(
                COALESCE(ca.raw_analysis->'objections'->'objections', '[]'::json)
            ) > 0
            AND COALESCE(elem->>'category_text', elem->>'category', '') != ''
            AND ca.id NOT IN (SELECT DISTINCT call_analysis_id FROM call_objection_details)
        """))
        objections_count = objections_result.rowcount
        print(f"  Inserted {objections_count} objection details", flush=True)

        await session.commit()

        # Print final counts
        for table in ["coaching_issues", "coaching_strengths", "call_objection_details"]:
            r = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            print(f"  Total {table}: {r.scalar()} rows", flush=True)

    print("\nBackfill complete!", flush=True)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
