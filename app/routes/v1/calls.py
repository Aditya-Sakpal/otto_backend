"""
Call API routes.

Thin layer that delegates to services.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbSession, CurrentUser
from app.core.permissions import require_manager_or_csr
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.users.models import User
from app.services.call_service import CallService

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[Call])
async def list_calls(
    company_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),  # CSR or EXECUTIVE only
    skip: int = 0,
    limit: int = 100,
) -> List[Call]:
    """
    List calls for a specific company.
    
    Access: CSR, EXECUTIVE
    
    Args:
        company_id: UUID of the company to retrieve calls for
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
    """
    try:
        service = CallService(db)
        calls = await service.call_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
        return calls
    except Exception as e:
        logger.error(f"Error listing calls: {e}")
        raise e


@router.get("/{call_id}", response_model=Call)
async def get_call(
    call_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),  # CSR or EXECUTIVE only
) -> Call:
    """
    Get call by ID.
    
    Access: CSR, EXECUTIVE
    
    Args:
        call_id: UUID of the call to retrieve (unique identifier)
    """
    try:
        service = CallService(db)
        call = await service.call_repo.get_by_id(call_id)
        
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )
        
        return call
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call: {e}")
        raise e

