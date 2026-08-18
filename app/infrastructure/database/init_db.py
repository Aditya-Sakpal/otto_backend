"""
Database initialization utility.

Can be used to automatically create tables on startup (development only).
For production, use Alembic migrations instead.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.base import Base
from app.infrastructure.database.connection import (
    build_database_target,
    connection_failure_hint,
)
from app.infrastructure.database.models import (
    CompanyORM,
    UserORM,
    ContactCardORM,
    LeadORM,
    CallORM,
    AppointmentORM,
    CallAnalysisORM,
    InvitationORM,
    PendingActionORM,
    LeadStatusChangeORM,
    CallProcessingJobORM,
    AskOttoConversationORM,
    AskOttoMessageORM,
    InsightJobORM,
    TenantConfigORM,
    FollowUpOttoORM,
)

logger = get_logger(__name__)


async def create_tables():
    """
    Create all database tables if they don't exist.
    
    WARNING: This should only be used in development!
    For production, use Alembic migrations instead.
    
    Why use migrations instead of auto-creation?
    1. Version control: Track schema changes over time
    2. Data safety: Migrations can handle data transformations
    3. Production safety: Never auto-modify production databases
    4. Rollback: Can revert schema changes if needed
    5. Team collaboration: Everyone applies same migrations
    6. Complex changes: Can add indexes, constraints, data migrations
    """
    # Allow in development or if explicitly enabled via AUTO_CREATE_TABLES
    if settings.is_production and not settings.AUTO_CREATE_TABLES:
        logger.warning(
            "Auto-creating tables in production is disabled. "
            "Use Alembic migrations instead. "
            "To override, set AUTO_CREATE_TABLES=True (not recommended for production)."
        )
        return
    
    # Warn if using in production even with override
    if settings.is_production and settings.AUTO_CREATE_TABLES:
        logger.warning(
            "WARNING: Auto-creating tables in PRODUCTION environment! "
            "This is not recommended. Use Alembic migrations for production databases."
        )
    
    logger.info("Creating database tables (if they don't exist)...")
    
    # Normalize database URL and resolve driver connect args (TLS included)
    target = build_database_target(
        settings.DATABASE_URL,
        ssl_mode=settings.DB_SSL_MODE or None,
    )
    logger.info(f"Database target: {target.description}")

    # Create engine
    if target.is_sqlite:
        engine = create_async_engine(
            target.url,
            echo=settings.is_development,
            connect_args=target.connect_args,
        )
    else:
        engine = create_async_engine(
            target.url,
            echo=settings.is_development,
            pool_pre_ping=True,
            connect_args=target.connect_args,
        )

    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database tables created successfully!")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating tables: {error_msg}")

        # Provide helpful error messages for common issues
        hint = connection_failure_hint(error_msg, target)
        if hint:
            logger.error(hint)

        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    """Run this script directly to create tables."""
    asyncio.run(create_tables())
