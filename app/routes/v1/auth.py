"""
Authentication API routes.

JWT-based authentication endpoints:
- POST /auth/signup - Register a new user
- POST /auth/login - Login with email/password
- POST /auth/refresh - Refresh access token
- GET /auth/me - Get current user info
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbSession
from app.core.security import create_access_token, create_refresh_token, get_user_id_from_token
from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.domain.users.service import UserService
from app.domain.users.schemas import (
    SignupRequest,
    UserCreate,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    UserResponse,
)
from app.domain.users.models import User

router = APIRouter()
logger = get_logger(__name__)


@router.post("/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    signup_data: SignupRequest,
    db: DbSession,
) -> LoginResponse:
    """
    Register a new user account.
    
    Creates a new user with email and password, then returns authentication tokens.
    Role defaults to SALES_REP if not specified.
    
    Returns:
        Access token, refresh token, and user information
        
    Raises:
        HTTPException: 400 if email already exists or validation fails
    """
    user_service = UserService(db)
    
    try:
        # Convert SignupRequest to UserCreate
        user_data = UserCreate(
            email=signup_data.email,
            password=signup_data.password,
            first_name=signup_data.first_name,
            last_name=signup_data.last_name,
            role=signup_data.role,
            company_id=signup_data.company_id,
        )
        
        # Create new user
        user = await user_service.create(user_data)
        
        # Create tokens for immediate login
        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
        )
        refresh_token = create_refresh_token(user_id=user.id)
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
    except Exception as e:
        logger.error(f"Error in signup: {e}")
        raise e


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    login_data: LoginRequest,
    db: DbSession,
) -> LoginResponse:
    """
    Login with email and password.
    
    Returns:
        Access token, refresh token, and user information
        
    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        user_service = UserService(db)
        
        # Authenticate user
        user = await user_service.authenticate(
            email=login_data.email,
            password=login_data.password,
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create tokens
        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
        )
        refresh_token = create_refresh_token(user_id=user.id)
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in login: {e}")
        raise e


@router.post("/refresh", response_model=RefreshTokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: DbSession,
) -> RefreshTokenResponse:
    """
    Refresh access token using refresh token.
    
    Returns:
        New access token
        
    Raises:
        HTTPException: 401 if refresh token is invalid
    """
    try:
        # Verify refresh token and get user ID
        user_id = get_user_id_from_token(refresh_data.refresh_token, token_type="refresh")
        
        # Get user from database
        user_service = UserService(db)
        user = await user_service.get_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        
        # Create new access token
        access_token = create_access_token(
            user_id=user.id,
            role=user.role.value,
        )
        
        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_current_user_info(
    user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get current authenticated user information.
    
    Returns:
        Current user information
        
    Note:
        Requires valid JWT access token in Authorization header.
    """
    try:
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error(f"Error getting current user info: {e}")
        raise e
