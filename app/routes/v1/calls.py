"""
Call API routes.

Thin layer that delegates to services.
"""
import traceback
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession, CurrentUser
from app.core.permissions import require_manager_or_csr, require_any_role
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.services.call_service import CallService
from app.services.analytics_service import AnalyticsService

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[Call])
async def list_calls(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),  # CSR or EXECUTIVE only
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
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
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{call_id}", response_model=Call)
async def get_call(
    call_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),  # CSR or EXECUTIVE only
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
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
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/by-objection/self")
async def get_calls_by_objection_self(
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),
    user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    objection: str = Query(..., description="Objection type (e.g., authority, price, timing)"),
    company_id: Optional[UUID] = Query(None, description="Company UUID"),
):
    """
    Get comprehensive objection details data for the objection details page.
    
    Returns data for three tabs:
    1. Calls: List of calls with that objection (with contact name and recording URL)
    2. Unbooked leads: Leads that are unbooked and have that objection
    3. Most coaching need: CSRs with unbooked calls for that objection
    
    Query Parameters:
    - objection: Objection type (required) - e.g., 'authority', 'price', 'timing', 'competitor', 'need'
    - company_id: Company UUID (optional, defaults to user's company)
    
    Access: CSR, EXECUTIVE
    """
    try:
        # Use company_id from query or fall back to current user's company
        if not company_id and user.company_id:
            company_id = user.company_id
        
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_id is required. Either provide it as a query parameter or ensure user has a company_id."
            )
        
        service = AnalyticsService(db)
        result = await service.get_calls_by_objection_self(
            company_id=company_id,
            objection=objection,
            user_id=user.id if user.role == UserRole.CSR else None,  # Filter by user if CSR
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting calls by objection self: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get calls by objection: {str(e)}",
        )


@router.get("/by-objection/{objection}/details")
async def get_objection_details(
    objection: str,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),
    user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    company_id: Optional[UUID] = Query(None, description="Company UUID"),
    start_date: Optional[str] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get comprehensive objection details for a single objection.
    
    Returns all details for the objection details modal including:
    1. Unbooked leads tab: Booking rate improvement, graph data, and unbooked leads list
    2. Most coaching need tab: CSRs with unbooked calls count
    3. Calls tab: Call recordings with contact names
    
    Query Parameters:
    - objection: Objection type (required) - e.g., 'authority', 'price', 'timing', 'competitor', 'need'
    - company_id: Company UUID (optional, defaults to user's company)
    - start_date: Start date for filtering (YYYY-MM-DD, optional, defaults to 30 days ago)
    - end_date: End date for filtering (YYYY-MM-DD, optional, defaults to today)
    
    Access: CSR, EXECUTIVE
    """
    try:
        # Use company_id from query or fall back to current user's company
        if not company_id and user.company_id:
            company_id = user.company_id
        
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_id is required. Either provide it as a query parameter or ensure user has a company_id."
            )
        
        service = AnalyticsService(db)
        result = await service.get_objection_details(
            company_id=company_id,
            objection=objection,
            start_date=start_date,
            end_date=end_date,
            user_id=user.id if user.role == UserRole.CSR else None,  # Filter by user if CSR
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting objection details: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get objection details: {str(e)}",
        )

