"""
Users API routes.

Provides user management endpoints for Team Management.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role, require_executive
from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.users.service import UserService
from app.domain.users.schemas import UserCreate, UserUpdate, UserSelfUpdate, UserResponse
from app.domain.enums import UserRole

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
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


@router.get("/companies", response_model=List[dict])
async def list_companies(
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> List[dict]:
    """
    List all companies.
    
    Access: Any authenticated user
    """
    try:
        from app.infrastructure.database.models.company import CompanyORM
        from sqlalchemy import select
        
        result = await db.execute(select(CompanyORM))
        companies = result.scalars().all()
        
        return [
            {
                "id": str(company.id),
                "name": company.name,
                "phone_number": company.phone_number,
                "address": company.address,
            }
            for company in companies
        ]
    except Exception as e:
        logger.error(f"Error listing companies: {e}")

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get current user's profile.

    Access: Any authenticated user

    Returns the authenticated user's own profile information.
    """
    try:
        return UserResponse.model_validate(current_user)
    except Exception as e:
        logger.error(f"Error getting current user profile: {e}")
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
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
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


@router.put("/me", response_model=UserResponse)
async def update_self(
    user_data: UserSelfUpdate,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> UserResponse:
    """
    Update current user's own profile.

    Access: Any authenticated user

    Note: This endpoint allows users to update their own profile data.
    Users cannot update their email, role, is_active status, or company_id through this endpoint.

    Args:
        user_data: User update data (excludes email, role, is_active, company_id)
    """
    try:
        service = UserService(db)
        # Convert UserSelfUpdate to UserUpdate (excluding email, role, is_active, company_id)
        # Only include fields that are set in user_data
        update_dict = user_data.model_dump(exclude_unset=True)
        # Create UserUpdate with only allowed fields (exclude email, role, is_active, company_id)
        update_data = UserUpdate(**update_dict)
        user = await service.update(current_user.id, update_data)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
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
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
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
