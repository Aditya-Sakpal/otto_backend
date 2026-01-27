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


@router.get("/logs")
async def get_call_logs(
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    db: DbSession = None,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    search: Optional[str] = Query(None, description="Search by customer name, CSR name, or phone number"),
    csr_id: Optional[UUID] = Query(None, description="Filter by CSR/owner UUID"),
    user_id: Optional[UUID] = Query(None, description="Filter by user UUID (alias for csr_id; also allows deriving company_id)"),
    status_filter: Optional[str] = Query(None, description="Filter by qualification status (qualified/unqualified/all)"),
    booking_filter: Optional[str] = Query(None, description="Filter by booking status (booked/unbooked/all)"),
    quick_filter: Optional[str] = Query(None, description="Quick filter (hot_lead, qualified_unbooked, qualified_booked, abandoned, residential, commercial, etc.)"),
    skip: int = Query(0, ge=0, description="Number of records to skip (for pagination)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
):
    """
    Get call logs with summary statistics and filtered call list.

    Returns:
    - summary: Statistics (total_calls, qualified, booked, abandoned)
    - calls: List of call log entries with all details:
      - call_id: UUID of the call
      - call_received: Formatted date/time when call was received
      - duration: Call duration (e.g., "2m 13s")
      - csr_name: Name of the CSR who handled the call
      - customer_name: Customer name (uppercase)
      - phone_number: Formatted phone number
      - is_qualified: Whether call was qualified (boolean)
      - is_booked: Whether call resulted in booking (boolean)
      - score: Call score (SOP compliance or sentiment score)
      - objections: Comma-separated list of objections
      - tags: Comma-separated list of tags
    - total: Total count of calls matching filters
    - skip: Number of records skipped
    - limit: Maximum number of records returned

    Query Parameters:
    - company_id: Company UUID (optional if user_id is provided). Either company_id or user_id is required.
    - user_id: User UUID (optional). If provided, call logs are scoped to this user. If both company_id and user_id are provided, user_id is used.
    - search: Search by customer name, CSR name, or phone number
    - csr_id: Filter by specific CSR/owner UUID (alternative to user_id)
    - status_filter: Filter by qualification status (qualified/unqualified/all)
    - booking_filter: Filter by booking status (booked/unbooked/all)
    - quick_filter: Quick filter options:
      - hot_lead: Hot leads
      - qualified_unbooked: Qualified but not booked
      - qualified_booked: Qualified and booked
      - abandoned: Abandoned leads
      - residential: Residential properties
      - commercial: Commercial properties
    - skip: Number of records to skip (default: 0)
    - limit: Maximum number of records to return (default: 100, max: 1000)

    Resolution Rules:
    - If user_id is provided: prefer user_id (even if company_id is also provided)
    - Else if company_id is provided: use company_id
    - Else: return 400 error "Either company_id or user_id is required"

    Access: CSR, SALES_REP, EXECUTIVE
    """
    try:
        service = CallService(db)

        # Resolution rules:
        # - If user_id is provided: prefer user_id (even if company_id is also provided)
        # - Else if company_id is provided: use company_id
        # - Else: error
        if user_id:
            csr_id = user_id  # enforce preference for user_id
            db_user = await service.user_repo.get_by_id(user_id)
            if not db_user or not getattr(db_user, "company_id", None):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either provide company_id, or provide user_id that belongs to a user with a company_id",
                )
            company_id = db_user.company_id
        elif not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either company_id or user_id is required",
            )

        result = await service.get_call_logs(
            company_id=company_id,
            search=search,
            csr_id=csr_id,
            status_filter=status_filter,
            booking_filter=booking_filter,
            quick_filter=quick_filter,
            skip=skip,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.error(f"Error getting call logs: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call logs: {str(e)}",
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
    company_id: Optional[UUID] = Query(None, description="Company UUID (optional if user_id is provided)"),
    user_id: Optional[UUID] = Query(None, description="User UUID to scope objection details to a single user (optional)"),
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
    - company_id: Company UUID (optional if user_id is provided)
    - user_id: User UUID (optional). If provided, objection details are scoped to that user. If both company_id and user_id are provided, user_id is used.
    - start_date: Start date for filtering (YYYY-MM-DD, optional, defaults to 30 days ago)
    - end_date: End date for filtering (YYYY-MM-DD, optional, defaults to today)

    Access: CSR, EXECUTIVE
    """
    try:
        # Resolution rules:
        # - If user_id is provided: prefer user_id (even if company_id is also provided)
        # - Else if company_id is provided: use company_id
        # - Else: try to use current user's company_id
        # - Else: error
        if user_id:
            # user_id takes precedence - derive company_id from user
            service = CallService(db)
            db_user = await service.user_repo.get_by_id(user_id)
            if not db_user or not getattr(db_user, "company_id", None):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either provide company_id, or provide user_id that belongs to a user with a company_id",
                )
            company_id = db_user.company_id
            # Use the provided user_id for filtering
            filter_user_id = user_id
        elif company_id:
            # Use company_id, and if current user is CSR, filter by their user_id
            filter_user_id = user.id if user.role == UserRole.CSR else None
        elif user.company_id:
            # Fall back to current user's company_id
            company_id = user.company_id
            filter_user_id = user.id if user.role == UserRole.CSR else None
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either company_id or user_id is required",
            )

        service = AnalyticsService(db)
        result = await service.get_objection_details(
            company_id=company_id,
            objection=objection,
            start_date=start_date,
            end_date=end_date,
            user_id=filter_user_id,
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
