"""
Local SQLite database for the follow-up log.

This is the agent's own state — tracks which leads have been
contacted, attempt numbers, cadence overrides, and message content.
"""
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS follow_up_log (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    queue_type TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    sent_at TEXT,
    channel TEXT NOT NULL,
    message_content TEXT NOT NULL,
    cadence_override INTEGER DEFAULT 0,
    override_reason TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    shunya_context_used INTEGER DEFAULT 1,
    pending_action_id TEXT,
    error_message TEXT,
    paused_reason TEXT,
    paused_at TEXT,
    comms_path TEXT,
    masked_comm_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fl_lead_queue
    ON follow_up_log(lead_id, queue_type);
CREATE INDEX IF NOT EXISTS idx_fl_status
    ON follow_up_log(status);
CREATE INDEX IF NOT EXISTS idx_fl_scheduled
    ON follow_up_log(scheduled_at, status);

CREATE TABLE IF NOT EXISTS opt_out_log (
    id TEXT PRIMARY KEY,
    phone TEXT NOT NULL,
    lead_id TEXT,
    opted_out_at TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_opt_out_phone
    ON opt_out_log(phone);
"""


async def init_local_db(db_path: str | None = None) -> None:
    """Initialize the local SQLite engine and create tables."""
    global _engine, _session_factory
    if _engine is not None:
        return

    path = db_path or settings.LOCAL_DB_PATH
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    url = f"sqlite+aiosqlite:///{path}"
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables
    async with _engine.begin() as conn:
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))

    logger.info("Local SQLite initialized", path=path)


async def get_local_session() -> AsyncSession:
    """Get a new local SQLite session."""
    if _session_factory is None:
        await init_local_db()
    assert _session_factory is not None
    return _session_factory()


async def close_local_db() -> None:
    """Dispose the local engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Local SQLite closed")
