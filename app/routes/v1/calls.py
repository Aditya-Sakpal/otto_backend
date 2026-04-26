"""
Call API routes.

Thin layer that delegates to services.
"""
import traceback
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body

from app.core.dependencies import DbSession, CurrentUser
from app.core.permissions import require_manager_or_csr, require_any_role
from app.core.logging import get_logger
from app.domain.models.call import Call
from app.domain.models.pending_action import PendingAction
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.schemas.calls import CallLogsResponse
from app.services.call_service import CallService
from app.services.analytics_service import AnalyticsService
from app.services.pending_action_service import PendingActionService
from pydantic import BaseModel, Field

router = APIRouter()

# Common response descriptions for Swagger
RESPONSES = {
    400: {"description": "Bad request (e.g. missing company_id or user_id)"},
    403: {"description": "Forbidden"},
    404: {"description": "Resource not found"},
    500: {"description": "Internal server error"},
}
logger = get_logger(__name__)


class CreateActionItemRequest(BaseModel):
    """Request to create an action item from a call (executive assigning to CSR)."""
    owner_id: UUID = Field(..., description="User UUID to assign the action to (CSR or Sales Rep)")
    action_type: str = Field(..., description="Type of action (e.g. follow_up_call, send_quote, schedule_appointment)")
    raw_text: Optional[str] = Field(None, description="Optional description/notes for the action item")
    due_at: Optional[datetime] = Field(None, description="When the action is due (ISO 8601)")
    priority: Optional[int] = Field(None, description="Priority level (higher = more urgent, e.g. 1=low, 5=critical)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "owner_id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
                "action_type": "follow_up_call",
                "raw_text": "Follow up with customer about the pricing concern",
                "due_at": "2026-03-22T14:00:00Z",
                "priority": 3,
            }
        }
    }


@router.get("", response_model=List[Call], responses=RESPONSES)
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


@router.get("/logs", response_model=CallLogsResponse, responses=RESPONSES)
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
    existing_customer: Optional[bool] = Query(None, description="Filter by existing customer (true=only existing, false=only non-existing, omit=all)"),
    quick_filter: Optional[str] = Query(None, description="Quick filter (hot_lead, qualified_unbooked, qualified_booked, abandoned, residential, commercial, etc.)"),
    scope_filter: Optional[str] = Query(None, description="Filter by scope (in_scope/out_scope/all). Defaults to in_scope if not provided."),
    objection_filter: Optional[str] = Query(None, description="Filter by CSR objection (e.g. 'service_fee_concerns', 'scheduling_conflicts'). Matches any call where the objections array contains this value."),
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
            existing_customer=existing_customer,
            quick_filter=quick_filter,
            scope_filter=scope_filter,
            objection_filter=objection_filter,
            skip=skip,
            limit=limit,
            current_user=user,
        )
        return result
    except Exception as e:
        logger.error(f"Error getting call logs: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call logs: {str(e)}",
        )


@router.post(
    "/{call_id}/action-items",
    response_model=PendingAction,
    status_code=status.HTTP_201_CREATED,
    responses={**RESPONSES, 404: {"description": "Call not found"}},
)
async def create_call_action_items(
    call_id: UUID,
    request: CreateActionItemRequest,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
) -> PendingAction:
    """
    Create an action item linked to a call and assign it to a user (e.g. executive assigning to CSR).
    
    Access: EXECUTIVE, CSR, SALES_REP
    """
    try:
        call_service = CallService(db)
        call = await call_service.call_repo.get_by_id(call_id)
        if not call:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
        pending_service = PendingActionService(db)
        action = await pending_service.create_from_call(
            call_id=call_id,
            company_id=call.company_id,
            lead_id=call.lead_id,
            owner_id=request.owner_id,
            assigned_by_id=user.id,
            action_type=request.action_type,
            raw_text=request.raw_text,
            due_at=request.due_at,
            priority=request.priority,
        )
        return action
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating action item for call: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{call_id}", response_model=Call, responses=RESPONSES)
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

        # CL-44 parity: surface the Shoonya analysis state directly on the
        # Call detail response so the frontend can distinguish "analysis
        # missing" from "call genuinely has no data". Non-blocking lookup —
        # on error we leave analysis_status None and still return the call.
        try:
            analysis = await service.analysis_repo.get_by_call_id(call_id)
            if analysis is None:
                call.analysis_status = "not_analyzed"
            else:
                raw_status = getattr(analysis, "status", None)
                if raw_status is None or str(raw_status).strip() == "":
                    call.analysis_status = "completed"
                else:
                    call.analysis_status = (
                        raw_status.value if hasattr(raw_status, "value") else str(raw_status)
                    ).lower()
        except Exception as analysis_err:
            logger.warning(
                "Could not resolve analysis_status for call",
                call_id=str(call_id),
                error=str(analysis_err),
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


@router.get("/by-objection/self", responses=RESPONSES)
async def get_calls_by_objection_self(
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE])),
    user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),  # RBAC DISABLED - Returns dummy user
    objection: str = Query(..., description="Objection type (e.g., authority, price, timing)"),
    company_id: Optional[UUID] = Query(None, description="Company UUID"),
):
    """
    Get comprehensive objection details data for the objection details page.

    Returns data for three tabs:
    1. Calls: List of calls with that objection (with contact name and recording URL)
    2. Unbooked leads: Leads that are unbooked and have that objection
    3. Most coaching need: CSRs/Sales Reps with unbooked calls for that objection

    Query Parameters:
    - objection: Objection type (required) - e.g., 'authority', 'price', 'timing', 'competitor', 'need'
    - company_id: Company UUID (optional, defaults to user's company)

    Access: CSR, SALES_REP, EXECUTIVE
    
    Note: For CSR and SALES_REP roles, results are filtered to the current user's calls only.
    For EXECUTIVE role, results show company-wide data.
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
        # Filter by user if CSR or SALES_REP, otherwise show company-wide data
        user_id = None
        user_role = None
        if user.role in [UserRole.CSR, UserRole.SALES_REP]:
            user_id = user.id
            # Safely get role value - handle both enum and string cases
            if hasattr(user.role, 'value'):
                user_role = user.role.value
            else:
                user_role = str(user.role)
        
        result = await service.get_calls_by_objection_self(
            company_id=company_id,
            objection=objection,
            user_id=user_id,
            user_role=user_role,
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


@router.get("/by-objection/{objection}/details", responses=RESPONSES)
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


class CallRetryResponse(BaseModel):
    """Response for a call analysis retry submission."""
    call_id: UUID = Field(..., description="Call ID")
    analysis_status: str = Field(
        ...,
        description="New state after retry — 'processing' on success, 'failed' if Shoonya rejected the re-submission immediately.",
    )
    processing_job_id: Optional[str] = Field(
        None,
        description="Shunya job ID for the new retry submission (null if Shoonya immediately rejected).",
    )


@router.post(
    "/{call_id}/retry",
    response_model=CallRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **RESPONSES,
        409: {"description": "Analysis already in progress for this call"},
        503: {"description": "Shunya service not available"},
    },
)
async def retry_call_analysis(
    call_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
) -> CallRetryResponse:
    """
    Retry Shoonya analysis for a call.

    Preconditions:
    - Call exists and has an ``audio_url`` (404 otherwise — nothing to
      re-submit).
    - Current ``CallAnalysisORM.status`` is NOT ``"processing"``
      (409 — would cause a duplicate in-flight Shunya job).
    - Caller belongs to the same company as the call (403).
    - Shoonya client is available (503).

    Behavior:
    - Resets the call's ``CallAnalysisORM.status`` to ``"pending"`` so the
      next Shoonya webhook completion overwrites the failed row cleanly.
    - Re-submits via ``CallService.trigger_analysis`` using the stored
      ``audio_url`` and call metadata.
    - Returns 202 with the new state.
    """
    try:
        service = CallService(db)
        call = await service.call_repo.get_by_id(call_id)
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        # Tenant isolation — don't let a caller re-trigger another tenant's
        # call analysis.
        if current_user.company_id is not None and call.company_id != current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: cross-tenant request",
            )

        if not call.audio_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call has no audio_url to retry against",
            )

        existing_analysis = await service.analysis_repo.get_by_call_id(call_id)
        if existing_analysis is not None:
            raw_status = getattr(existing_analysis, "status", None)
            current_status = (
                raw_status.value if hasattr(raw_status, "value") else str(raw_status)
            ).lower() if raw_status is not None else None
            if current_status == "processing":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Analysis is already in progress for this call",
                )

        from app.infrastructure.integrations.shoonya import get_shoonya_client

        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )

        # Reset the existing analysis row to "pending" so the next Shoonya
        # webhook completion overwrites it. We keep the row rather than
        # delete it so foreign keys from other tables (coaching rows, etc.)
        # remain intact.
        if existing_analysis is not None:
            from app.domain.enums import AnalysisStatus

            existing_analysis.status = AnalysisStatus.PENDING
            try:
                await service.analysis_repo.update(existing_analysis.id, existing_analysis)
                await db.commit()
            except Exception as reset_err:
                logger.warning(
                    "Could not reset CallAnalysis status before retry",
                    call_id=str(call_id),
                    error=str(reset_err),
                )
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Re-submit via the existing trigger. Capture the new job_id via a
        # small inline call to shoonya so the response can report it.
        from datetime import datetime as _dt
        from app.core.config import settings as _settings
        from app.domain.enums import CallType

        submission_error: Optional[str] = None
        processing_job_id: Optional[str] = None
        try:
            call_type_str = "csr_call"
            if call.call_type:
                call_type_str = (
                    call.call_type.value
                    if hasattr(call.call_type, "value")
                    else str(call.call_type)
                )
            call_metadata = {
                "call_type": call_type_str,
                **(call.extra_metadata or {}),
                "retry": True,
            }
            call_metadata["agent"] = (
                {"id": str(call.handled_by_user_id)} if call.handled_by_user_id else None
            )

            webhook_url = f"{_settings.API_URL}/api/v1/webhooks/shoonya/job-complete"
            result = await shoonya.process_call(
                call_id=str(call.id),
                company_id=str(call.company_id),
                audio_url=call.audio_url,
                phone_number=call.phone_number,
                duration=call.duration_seconds or 0,
                call_date=(
                    call.created_at.isoformat()
                    if call.created_at
                    else _dt.utcnow().isoformat()
                ),
                webhook_url=webhook_url,
                metadata=call_metadata,
            )
            processing_job_id = result.get("job_id")
            logger.info(
                "Call retry submitted to Shoonya",
                call_id=str(call_id),
                job_id=processing_job_id,
            )
        except Exception as e:
            submission_error = str(e)
            logger.error(
                f"Retry submission to Shoonya failed for call {call_id}: {e}",
                exc_info=True,
            )

        if submission_error is not None:
            # Mark failed via the same helper the webhook uses, so the
            # state is consistent regardless of which code path noticed it.
            from app.routes.v1.webhooks import _mark_call_analysis_failed

            await _mark_call_analysis_failed(
                db=db,
                call_id=call_id,
                company_id=call.company_id,
                error_detail=submission_error,
            )
            return CallRetryResponse(
                call_id=call_id,
                analysis_status="failed",
                processing_job_id=None,
            )

        return CallRetryResponse(
            call_id=call_id,
            analysis_status="processing",
            processing_job_id=processing_job_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying call analysis: {e}")
        traceback.print_exc()
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
