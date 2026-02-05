"""
Ghost Mode API routes.

Provides endpoints for managing ghost mode settings:
- Check ghost mode status
- Toggle user ghost mode
- Toggle company ghost mode
"""
import traceback

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role, require_executive
from app.core.logging import get_logger
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.schemas.ghost_mode import (
    GhostModeStatusResponse,
    UpdateGhostModeRequest,
    UpdateCompanyGhostModeRequest,
    GhostModeToggleResponse,
)
from app.services.ghost_mode_service import GhostModeService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/status", response_model=GhostModeStatusResponse)
async def get_ghost_mode_status(
    db: DbSession,
    current_user: User = Depends(
        require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """
    Get current ghost mode status for the user.

    Returns:
    - company_ghost_mode_enabled: Whether the company has enabled ghost mode
    - user_ghost_mode_active: Whether the user has enabled ghost mode
    - effective_ghost_mode: True if both company and user settings are enabled

    Access: CSR, SALES_REP, EXECUTIVE
    """
    try:
        service = GhostModeService(db)
        status_data = await service.get_user_ghost_mode_status(current_user)

        return GhostModeStatusResponse(**status_data)
    except Exception as e:
        logger.error(f"Error getting ghost mode status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ghost mode status: {str(e)}",
        )


@router.put("/toggle", response_model=GhostModeToggleResponse)
async def toggle_user_ghost_mode(
    request: UpdateGhostModeRequest,
    db: DbSession,
    current_user: User = Depends(
        require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])
    ),
):
    """
    Toggle ghost mode for the current user.

    When enabled, meeting recordings owned by this user will have their
    audio_url and transcript hidden from other users (including executives).

    Note: Ghost mode can only be enabled if the company has allowed it.

    Args:
        request.active: True to enable ghost mode, False to disable

    Returns:
        Current ghost mode settings after the update

    Raises:
        400: If trying to enable ghost mode but company hasn't allowed it

    Access: CSR, SALES_REP, EXECUTIVE
    """
    try:
        service = GhostModeService(db)
        result = await service.set_user_ghost_mode(current_user, request.active)
        await db.commit()

        return GhostModeToggleResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error toggling user ghost mode: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle ghost mode: {str(e)}",
        )


@router.put("/company", response_model=GhostModeToggleResponse)
async def toggle_company_ghost_mode(
    request: UpdateCompanyGhostModeRequest,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Toggle ghost mode availability for the company.

    When enabled, sales reps in this company can activate ghost mode
    to hide their meeting recordings from executives.

    Note: Only executives can toggle this setting.

    Args:
        request.enabled: True to allow ghost mode, False to disallow

    Returns:
        Current ghost mode settings after the update

    Raises:
        400: If user is not an executive
        403: Forbidden if not an executive

    Access: EXECUTIVE only
    """
    try:
        service = GhostModeService(db)
        result = await service.set_company_ghost_mode(current_user, request.enabled)
        await db.commit()

        return GhostModeToggleResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error toggling company ghost mode: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle company ghost mode: {str(e)}",
        )
