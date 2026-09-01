"""
Database session management.

Provides async database sessions using SQLAlchemy 2.x.
"""
import traceback
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from app.core import db_credentials
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

# When the password is managed by Secrets Manager it is injected per-connection
# (see below) rather than baked into the URL, so that an automatic rotation is
# picked up without a restart.
use_managed_password = db_credentials.is_enabled() and not database_target.is_sqlite

engine_url = database_target.url
if use_managed_password:
    db_credentials.set_fallback_password(
        db_credentials.extract_password(engine_url)
    )
    engine_url = db_credentials.strip_password(engine_url)
    logger.info("Database password will be read from AWS Secrets Manager")

# Create async engine
# Handle both PostgreSQL (asyncpg) and SQLite (aiosqlite) drivers
if database_target.is_sqlite:
    # SQLite configuration (for development)
    engine = create_async_engine(
        engine_url,
        echo=False,
        connect_args=database_target.connect_args,
    )
else:
    # PostgreSQL configuration (production)
    engine = create_async_engine(
        engine_url,
        echo=False,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={**database_target.connect_args, "statement_cache_size": 0},
    )

if use_managed_password:

    @event.listens_for(engine.sync_engine, "do_connect")
    def _inject_managed_password(dialect, conn_rec, cargs, cparams):
        """Supply the current password each time a new connection is opened."""
        cparams["password"] = db_credentials.get_password()

    @event.listens_for(engine.sync_engine, "handle_error")
    def _refresh_password_on_auth_failure(context):
        """
        Drop the cached password when the server rejects it.

        A rotation between two cache refreshes shows up as an authentication
        failure; clearing the cache means the next connection attempt fetches
        the new password instead of retrying the old one.
        """
        exception_name = type(context.original_exception).__name__
        if exception_name in (
            "InvalidPasswordError",
            "InvalidAuthorizationSpecificationError",
        ):
            db_credentials.invalidate()


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
