"""
Invitations API routes.

Provides endpoints for creating and accepting invitations.
"""
import traceback
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_executive, require_any_role
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.enums import UserRole
from app.domain.schemas.invitation import InvitationCreate, InvitationResponse, InvitationAcceptResponse
from app.services.invitation_service import InvitationService

router = APIRouter()
logger = get_logger(__name__)


@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    invitation_data: InvitationCreate,
    db: DbSession,
    current_user: User = Depends(require_executive),
) -> InvitationResponse:
    """
    Create and send an invitation.

    Access: EXECUTIVE only

    Args:
        invitation_data: Invitation creation data (email and company_id)
        current_user: Current authenticated user (must be EXECUTIVE)

    Returns:
        Created invitation details
    """
    try:
        service = InvitationService(db)
        invitation = await service.create_invitation(
            invitation_data=invitation_data,
            inviter_id=current_user.id,
        )
        return InvitationResponse.model_validate(invitation)
    except ValueError as e:
        logger.warning(f"Validation error creating invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error creating invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation",
        )


@router.post("/accept/{token}", response_model=InvitationAcceptResponse)
async def accept_invitation(
    token: str,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> InvitationAcceptResponse:
    """
    Accept an invitation by token.

    Access: Any authenticated user

    Args:
        token: Invitation token
        current_user: Current authenticated user

    Returns:
        Acceptance confirmation with invitation details
    """
    try:
        service = InvitationService(db)
        invitation = await service.accept_invitation(
            token=token,
            accepting_user_email=current_user.email,
        )

        return InvitationAcceptResponse(
            message="Invitation accepted successfully",
            invitation=InvitationResponse.model_validate(invitation),
        )
    except ValueError as e:
        logger.warning(f"Validation error accepting invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error accepting invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation",
        )
