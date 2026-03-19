"""
Entry point: python -m contextual_follow_up

Supports:
  --lead-id UUID    Process a single lead end-to-end
  --dry-run         Override DRY_RUN=true (no execution)
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from contextual_follow_up_agent.config.logging import get_logger, setup_logging
from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.db.local import close_local_db, init_local_db, get_local_session
from contextual_follow_up_agent.db.postgres import close_pg, get_pg_session, init_pg
from contextual_follow_up_agent.orchestrator import run

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Contextual Follow-Up Agent for gomotto",
    )
    parser.add_argument(
        "--lead-id",
        type=str,
        default=None,
        help="Process a single lead by UUID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Force dry-run mode (no SMS, no pending_actions writes)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging()

    if args.dry_run:
        settings.DRY_RUN = True
        settings.AUTO_EXECUTE = False

    logger.info(
        "Starting contextual follow-up agent",
        environment=settings.ENVIRONMENT,
        dry_run=settings.DRY_RUN,
        auto_execute=settings.AUTO_EXECUTE,
    )

    # Initialize databases
    await init_pg()
    await init_local_db()

    try:
        pg_session = await get_pg_session()
        local_session = await get_local_session()

        async with pg_session, local_session:
            stats = await run(
                pg_session=pg_session,
                local_session=local_session,
                lead_id_filter=args.lead_id,
            )

        logger.info("Agent finished", **stats)

    except Exception as e:
        logger.error("Agent failed", error=str(e))
        sys.exit(1)

    finally:
        await close_pg()
        await close_local_db()


if __name__ == "__main__":
    asyncio.run(main())
