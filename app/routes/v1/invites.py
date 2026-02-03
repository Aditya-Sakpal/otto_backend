"""
Invitations API routes.

Provides endpoints for creating and accepting invitations.
"""
import traceback
from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_executive
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.schemas.invitation import (
    InvitationCreate,
    InvitationResponse,
    InvitationValidateResponse,
    InvitationSignupRequest,
    InvitationSignupResponse,
)
from app.services.invitation_service import InvitationService

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request (e.g. invalid token or validation error)"},
    403: {"description": "Forbidden"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def create_invitation(
    db: DbSession,
    invitation_data: InvitationCreate = Body(...),
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


@router.get("/validate/{token}", response_model=InvitationValidateResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_invitation_token(
    token: str,
    db: DbSession,
) -> InvitationValidateResponse:
    """
    Validate an invitation token.

    Access: Public

    Args:
        token: Invitation token

    Returns:
        Validation result and invitation details
    """
    try:
        service = InvitationService(db)
        invitation = await service.validate_token(token)
        return InvitationValidateResponse(
            valid=True,
            invitation=InvitationResponse.model_validate(invitation),
        )
    except ValueError as e:
        logger.warning(f"Validation error validating invitation token: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error validating invitation token: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate invitation token",
        )


@router.post("/invite/complete", response_model=InvitationSignupResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def accept_invitation_and_signup(
    body: InvitationSignupRequest,
    db: DbSession,
) -> InvitationSignupResponse:
    """
    Accept an invitation by creating a user account.

    Access: Public

    Body:
        token, password, first_name, last_name

    Returns:
        Created user details and accepted invitation details
    """
    try:
        service = InvitationService(db)
        accepted_invitation, created_user = await service.accept_invitation_signup(
            token=body.token,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
        )

        await db.commit()

        return InvitationSignupResponse(
            message="Invitation accepted and user created successfully",
            invitation=InvitationResponse.model_validate(accepted_invitation),
            user=created_user,  # already domain model
        )
    except ValueError as e:
        await db.rollback()
        logger.warning(f"Validation error accepting invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error accepting invitation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation",
        )
