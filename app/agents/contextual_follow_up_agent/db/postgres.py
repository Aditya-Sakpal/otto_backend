"""
Async SQLAlchemy connection to Otto-Backend PostgreSQL.

Read-only for scans; writes to pending_actions for rep nudges.
Pattern from Otto-Backend/app/infrastructure/database/session.py.
"""
import os
import sys

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.config.logging import get_logger

# This package is importable standalone (app/agents is put on sys.path), so the
# project root is not guaranteed to be there when it runs on its own.
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.infrastructure.database.connection import build_database_target  # noqa: E402

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_pg() -> None:
    """Initialize the PostgreSQL engine and session factory."""
    global _engine, _session_factory
    if _engine is not None:
        return

    target = build_database_target(
        settings.DATABASE_URL,
        ssl_mode=settings.DB_SSL_MODE or None,
    )
    _engine = create_async_engine(
        target.url,
        echo=settings.is_development,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=target.connect_args,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    logger.info("PostgreSQL engine initialized")


async def get_pg_session() -> AsyncSession:
    """Get a new async session."""
    if _session_factory is None:
        await init_pg()
    assert _session_factory is not None
    return _session_factory()


async def close_pg() -> None:
    """Dispose the engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL engine closed")
