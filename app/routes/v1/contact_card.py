"""
Contact Card API routes.

Provides endpoints for retrieving calls associated with contact cards.
"""
import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_manager_or_csr
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.contact import ContactCard
from app.domain.users.models import User
from app.services.call_service import CallService
from app.infrastructure.repositories.contact import ContactRepository

router = APIRouter()
logger = get_logger(__name__)

@router.get("/calls/{call_id}", response_model=Call)
async def get_contact_card_call_by_id(
    call_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> Call:
    """
    Get call by ID for any contact card.

    Access: CSR, EXECUTIVE

    Args:
        call_id: UUID of the call to retrieve
    """
    try:
        service = CallService(db)
        contact_repo = ContactRepository(db)

        call = await service.call_repo.get_by_id(call_id)

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        # If call has a contact_card_id, retrieve and validate the contact card
        if call.contact_card_id:
            contact_card = await contact_repo.get_by_id(call.contact_card_id)
            if not contact_card:
                logger.warning(f"Call {call_id} references non-existent contact_card_id {call.contact_card_id}")

        return call
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call by ID: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{contact_card_id}", response_model=ContactCard)
async def get_contact_card_by_id(
    contact_card_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),  # CSR or EXECUTIVE only
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> ContactCard:
    """
    Get contact card by ID.

    Access: CSR, EXECUTIVE

    Args:
        contact_card_id: UUID of the contact card to retrieve
    """
    try:
        contact_repo = ContactRepository(db)
        contact_card = await contact_repo.get_by_id(contact_card_id)

        if not contact_card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact card with ID {contact_card_id} not found",
            )

        return contact_card
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting contact card by ID: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
