"""
Users API routes.

Provides user management endpoints for Team Management.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role, require_executive
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.users.service import UserService
from app.domain.users.schemas import UserCreate, UserUpdate, UserResponse
from app.domain.enums import UserRole

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    company_id: Optional[UUID] = Query(None, description="Filter by company ID"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> List[UserResponse]:
    """
    List users with optional filters.

    Access: Any authenticated user

    Query Parameters:
    - company_id: Filter by company ID
    - role: Filter by user role (csr, sales_rep, executive)
    - is_active: Filter by active status (true/false)
    - skip: Pagination offset
    - limit: Maximum number of results (1-1000)
    """
    try:
        service = UserService(db)
        users = await service.list_users(
            company_id=company_id,
            role=role,
            is_active=is_active,
            skip=skip,
            limit=limit,
        )
        return [UserResponse.model_validate(u) for u in users]
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> UserResponse:
    """
    Get user by ID.

    Access: Any authenticated user

    Args:
        user_id: User UUID
    """
    try:
        service = UserService(db)
        user = await service.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: DbSession,
    current_user: User = Depends(require_executive),
) -> UserResponse:
    """
    Create a new user.

    Access: EXECUTIVE only

    Args:
        user_data: User creation data
    """
    try:
        service = UserService(db)
        user = await service.create(user_data)
        return UserResponse.model_validate(user)
    except ValueError as e:
        logger.warning(f"Validation error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: DbSession,
    current_user: User = Depends(require_executive),
) -> UserResponse:
    """
    Update user.

    Access: EXECUTIVE only

    Note: This endpoint is for administrators to update any user.

    Args:
        user_id: User UUID
        user_data: User update data
    """
    try:
        service = UserService(db)
        user = await service.update(user_id, user_data)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_executive),
) -> None:
    """
    Delete a user.

    Access: EXECUTIVE only

    Args:
        user_id: User UUID to delete
    """
    try:
        # Prevent self-deletion
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )

        service = UserService(db)
        deleted = await service.delete(user_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
