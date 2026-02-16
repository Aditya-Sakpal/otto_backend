"""
FastAPI dependencies.

Provides dependency injection for:
- Database sessions
- Current user (JWT-based)
- Current company/tenant
- Service instances
"""
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database import get_db_session
from app.core.auth import get_current_user
from app.domain.users.models import User

logger = get_logger(__name__)


# Database dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session.
    
    Yields:
        Async database session
        
    Note:
        Session is automatically closed after request completes.
    """
    async for session in get_db_session():
        yield session


# Type alias for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


# Authentication dependencies
# Note: get_current_user is now in app.core.auth and uses JWT tokens
# It creates its own database session internally to avoid circular imports

# Type alias for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]

