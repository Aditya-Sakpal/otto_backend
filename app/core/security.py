"""
JWT token creation and verification.

Centralized JWT handling for access and refresh tokens.
"""
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Union
from uuid import UUID
from enum import Enum

import bcrypt
from jose import JWTError, jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _prehash_password(password: str) -> str:
    """
    Pre-hash password with SHA-256 to handle bcrypt's 72-byte limit.

    Bcrypt has a 72-byte limit, so we pre-hash with SHA-256 to:
    1. Support passwords of any length
    2. Create a fixed 32-byte (256-bit) input for bcrypt

    We use base64 encoding of the raw hash bytes to ensure we stay well under
    the 72-byte limit (base64 of 32 bytes = 44 characters = 44 bytes).

    Args:
        password: Plain text password

    Returns:
        Base64-encoded SHA-256 hash of the password (44 characters)
    """
    # Hash to get 32 bytes, then base64 encode to get 44 bytes (well under 72-byte limit)
    hash_bytes = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.b64encode(hash_bytes).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        # Pre-hash the plain password before verification
        prehashed = _prehash_password(plain_password)
        # Use bcrypt directly to avoid passlib's bug detection issues
        return bcrypt.checkpw(prehashed.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    To handle bcrypt's 72-byte limit, we pre-hash the password with SHA-256
    before passing it to bcrypt. This allows passwords of any length.

    We use bcrypt directly instead of passlib to avoid initialization issues
    with passlib's bug detection.

    Args:
        password: Plain text password

    Returns:
        Bcrypt-hashed password string
    """
    try:
        # Pre-hash with SHA-256 to handle long passwords
        prehashed = _prehash_password(password)
        # Use bcrypt directly to avoid passlib's bug detection issues
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(prehashed.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Error hashing password: {e}")
        raise e


def create_access_token(
    user_id: UUID,
    role: Union[str, Enum],
    company_id: Optional[UUID] = None,
    name: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: User UUID
        role: User role (EXECUTIVE, CSR, SALES_REP)
        company_id: Optional company UUID
        name: Optional user name (full name)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT access token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # Convert role enum to string value if it's an Enum
    role_value = role.value if hasattr(role, 'value') else role

    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "role": role_value,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    # Add company_id to payload if provided
    if company_id:
        payload["company_id"] = str(company_id)

    # Add name to payload if provided
    if name:
        payload["name"] = name

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return encoded_jwt


def create_refresh_token(
    user_id: UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT refresh token.

    Args:
        user_id: User UUID
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return encoded_jwt


def decode_token(token: str, token_type: str = "access") -> dict:
    """
    Decode and verify a JWT token.

    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        # Verify token type
        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {token_type}",
            )

        return payload

    except JWTError as e:
        logger.warning("JWT decode error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    except Exception as e:
        logger.error("Token verification error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        )


def get_user_id_from_token(token: str, token_type: str = "access") -> UUID:
    """
    Extract user ID from a JWT token.

    Args:
        token: JWT token string
        token_type: Expected token type

    Returns:
        User UUID

    Raises:
        HTTPException: If token is invalid
    """
    payload = decode_token(token, token_type)
    user_id_str = payload.get("sub")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID",
        )

    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        )


def get_role_from_token(token: str) -> str:
    """
    Extract role from an access token.

    Args:
        token: JWT access token

    Returns:
        User role string

    Raises:
        HTTPException: If token is invalid or missing role
    """
    payload = decode_token(token, token_type="access")
    role = payload.get("role")

    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing role",
        )

    return role


def get_company_id_from_token(token: str) -> Optional[UUID]:
    """
    Extract company_id from an access token.

    Args:
        token: JWT access token

    Returns:
        Company UUID or None if not present

    Raises:
        HTTPException: If token is invalid
    """
    payload = decode_token(token, token_type="access")
    company_id_str = payload.get("company_id")

    if not company_id_str:
        return None

    try:
        return UUID(company_id_str)
    except ValueError:
        logger.warning(f"Invalid company_id in token: {company_id_str}")
        return None

