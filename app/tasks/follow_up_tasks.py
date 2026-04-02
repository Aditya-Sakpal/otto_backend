"""
Celery task: contextual follow-up agent.

Wraps the fully-async agent orchestrator in asyncio.run() so it can
run inside a synchronous Celery worker process.
"""
import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.follow_up_tasks.run_contextual_follow_up",
    # Do not retry the full orchestrator: one failure after many leads would
    # re-run the entire scan and duplicate all Anthropic calls (very expensive).
    max_retries=0,
)
def run_contextual_follow_up() -> dict:
    """
    Run the contextual follow-up agent as a Celery task.

    Initialises DB connections, runs the full orchestrator loop
    (scan → gate → generate → execute), then tears down connections.
    Returns the stats dict from the orchestrator.
    """
    # Lazy imports so the agent package is only loaded inside the worker,
    # not at import time in other processes (e.g. the FastAPI server).
    from contextual_follow_up_agent.config.logging import setup_logging
    from contextual_follow_up_agent.db.local import (
        close_local_db,
        get_local_session,
        init_local_db,
    )
    from contextual_follow_up_agent.db.postgres import (
        close_pg,
        get_pg_session,
        init_pg,
    )
    from contextual_follow_up_agent.orchestrator import run

    async def _run() -> dict:
        setup_logging()
        await init_pg()
        await init_local_db()
        try:
            pg_session = await get_pg_session()
            local_session = await get_local_session()
            async with pg_session, local_session:
                stats = await run(
                    pg_session=pg_session,
                    local_session=local_session,
                )
            logger.info("Contextual follow-up agent finished: %s", stats)
            return stats
        finally:
            await close_pg()
            await close_local_db()

    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("Contextual follow-up agent failed")
        raise
