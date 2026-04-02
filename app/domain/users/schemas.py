"""
User Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import UserRole


class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr = Field(..., description="User email")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    role: UserRole = Field(..., description="User role")
    company_id: Optional[UUID] = Field(None, description="Associated company ID")


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")


class SignupRequest(BaseModel):
    """Schema for user signup (public registration)."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    role: UserRole = Field(default=UserRole.SALES_REP, description="User role (defaults to SALES_REP). Allowed: csr, sales_rep, executive")
    company_id: Optional[UUID] = Field(None, description="Associated company ID (optional)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "john.doe@example.com",
                "password": "securePass123",
                "first_name": "John",
                "last_name": "Doe",
                "role": "sales_rep",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
            }
        }
    }


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    password: Optional[str] = Field(None, min_length=8, description="User password (min 8 characters)")
    role: Optional[UserRole] = Field(None, description="User role")
    is_active: Optional[bool] = Field(None, description="Whether user account is active")
    company_id: Optional[UUID] = Field(None, description="Associated company ID")


class UserSelfUpdate(BaseModel):
    """Schema for users to update their own profile (excludes email, role, is_active, company_id)."""
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    password: Optional[str] = Field(None, min_length=8, description="User password (min 8 characters)")


class UserResponse(UserBase):
    """Schema for user API responses."""
    id: UUID = Field(..., description="User UUID")
    is_active: bool = Field(..., description="Whether user account is active")
    created_at: datetime = Field(..., description="Account creation timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "role": "sales_rep",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "is_active": True,
                "created_at": "2026-01-15T10:30:00+00:00",
            }
        }


# Authentication schemas
class LoginRequest(BaseModel):
    """Schema for login request."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "john.doe@example.com",
                "password": "securePass123",
            }
        }
    }


class LoginResponse(BaseModel):
    """Schema for login response."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    user: UserResponse = Field(..., description="User information")

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
                    "email": "john.doe@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "role": "sales_rep",
                    "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                    "is_active": True,
                    "created_at": "2026-01-15T10:30:00+00:00",
                },
            }
        }
    }


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str = Field(..., description="JWT refresh token")


class RefreshTokenResponse(BaseModel):
    """Schema for refresh token response."""
    access_token: str = Field(..., description="New JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenPayload(BaseModel):
    """Schema for JWT token payload (for internal use)."""
    user_id: UUID = Field(..., alias="sub", description="User ID")
    role: UserRole = Field(..., description="User role")
    type: str = Field(..., description="Token type (access or refresh)")
    name: Optional[str] = Field(None, description="User full name")

