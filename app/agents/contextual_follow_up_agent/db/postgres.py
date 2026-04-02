"""
Async SQLAlchemy connection to Otto-Backend PostgreSQL.

Read-only for scans; writes to pending_actions for rep nudges.
Pattern from Otto-Backend/app/infrastructure/database/session.py.
"""
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from contextual_follow_up_agent.config.settings import settings
from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_url(url: str) -> str:
    """Normalize database URL for asyncpg driver."""
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://") and "+asyncpg" not in url:
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def init_pg() -> None:
    """Initialize the PostgreSQL engine and session factory."""
    global _engine, _session_factory
    if _engine is not None:
        return

    url = _normalize_url(settings.DATABASE_URL)
    _engine = create_async_engine(
        url,
        echo=settings.is_development,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
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
