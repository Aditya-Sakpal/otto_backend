"""
Database session management.

Provides async database sessions using SQLAlchemy 2.x.
"""
import traceback
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.connection import build_database_target

logger = get_logger(__name__)


# Resolve the async driver and, for PostgreSQL, the TLS mode. See
# app/infrastructure/database/connection.py for why the sslmode is set
# explicitly rather than left to asyncpg's plaintext-fallback default.
database_target = build_database_target(
    settings.DATABASE_URL,
    ssl_mode=settings.DB_SSL_MODE or None,
)
logger.info(f"Database target: {database_target.description}")

# Create async engine
# Handle both PostgreSQL (asyncpg) and SQLite (aiosqlite) drivers
if database_target.is_sqlite:
    # SQLite configuration (for development)
    engine = create_async_engine(
        database_target.url,
        echo=False,
        connect_args=database_target.connect_args,
    )
else:
    # PostgreSQL configuration (production)
    engine = create_async_engine(
        database_target.url,
        echo=False,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={**database_target.connect_args, "statement_cache_size": 0},
    )

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session.

    Yields:
        Async database session

    Note:
        Session is automatically closed after use.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database session error: {e}")
            traceback.print_exc()
            await session.rollback()
            raise
        finally:
            await session.close()
