"""
Authentication dependencies.

Provides dependency injection for authenticated users.
"""
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_token, get_user_id_from_token
from app.domain.users.service import UserService
from app.domain.users.models import User

logger = get_logger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Get current authenticated user from JWT token.
    
    In DEV mode (APP_ENV=DEV), bypasses authentication and returns a mock user.
    In PROD mode (APP_ENV=PROD), requires valid JWT access token.
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer token credentials
        db: Database session
        
    Returns:
        Current authenticated user
        
    Raises:
        HTTPException: If user is not authenticated or token is invalid
    """
    # DEV mode: bypass authentication (optional - can be enabled for easier development)
    # For now, we require authentication even in DEV mode for security
    # Uncomment below to bypass auth in DEV mode:
    # if settings.is_dev_mode:
    #     logger.debug("DEV mode: Authentication bypassed")
    #     # Return a mock user (for development only)
    #     from app.domain.users.models import User
    #     from app.domain.enums import UserRole
    #     from uuid import UUID
    #     return User(
    #         id=UUID("00000000-0000-0000-0000-000000000001"),
    #         email="dev@example.com",
    #         role=UserRole.EXECUTIVE,
    #         is_active=True,
    #     )
    
    # PROD mode: require valid JWT token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        # Decode and verify token
        payload = decode_token(token, token_type="access")
        user_id_str = payload.get("sub")
        
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user ID",
            )
        
        # Get user from database
        # Create a new session (we can't inject db here due to circular dependency)
        # In routes, we'll need to pass db explicitly or create a wrapper
        from app.infrastructure.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            user = await user_service.get_by_id(user_id_str)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = None,
) -> Optional[User]:
    """
    Get current authenticated user (optional).
    
    Returns None if no token is provided or token is invalid.
    Useful for endpoints that work with or without authentication.
    
    Args:
        request: FastAPI request object
        credentials: Optional HTTP Bearer token credentials
        db: Database session
        
    Returns:
        Current user or None
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None

