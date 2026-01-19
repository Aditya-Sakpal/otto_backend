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

logger = get_logger(__name__)


def _normalize_database_url(url: str) -> str:
    """
    Normalize database URL to use correct async driver.
    
    Args:
        url: Database connection string
        
    Returns:
        Normalized URL with correct async driver
    """
    # If it's PostgreSQL without async driver, add asyncpg
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # If it's postgres:// (alternative format), convert to postgresql+asyncpg://
    elif url.startswith("postgres://") and "+asyncpg" not in url:
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    # If it's SQLite, ensure it uses aiosqlite
    elif url.startswith("sqlite://") and "+aiosqlite" not in url:
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    
    return url


# Normalize database URL for async driver
database_url = _normalize_database_url(settings.DATABASE_URL)

# Create async engine
# Handle both PostgreSQL (asyncpg) and SQLite (aiosqlite) drivers
if database_url.startswith("sqlite"):
    # SQLite configuration (for development)
    engine = create_async_engine(
        database_url,
        echo=settings.is_development,
        connect_args={"check_same_thread": False},  # SQLite requirement
    )
else:
    # PostgreSQL configuration (production)
    engine = create_async_engine(
        database_url,
        echo=settings.is_development,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
        pool_recycle=1800,
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

