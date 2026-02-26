"""
Leads API routes.

Provides lead management endpoints.
"""
import traceback
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_manager_or_csr, require_manager_or_sales_rep
from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import LeadDetail, PipelineLeadDetail
from app.domain.users.models import User
from app.services.lead_service import LeadService
from pydantic import BaseModel, Field
from typing import Dict

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request (e.g. invalid date format)"},
    403: {"description": "Forbidden"},
    404: {"description": "Lead not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


@router.get("", response_model=List[Lead], responses=RESPONSES)
async def list_leads(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
    status_filter: Optional[str] = Query(None, alias="status"),
    nurturing: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="Filter leads created on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter leads created on or before this date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by contact name or phone number"),
    skip: int = 0,
    limit: int = 100,
) -> List[Lead]:
    """
    List leads for a company with optional filters.
    
    Access: EXECUTIVE, CSR
    
    Query Parameters:
    - status: Filter by status (comma-separated for multiple, e.g., "qualified_unbooked" or "closed_lost,abandoned,dormant")
    - nurturing: Filter nurturing leads (comma-separated, e.g., "new,warm,hot")
    - sort: Sort option (e.g., "priority")
    - start_date: Filter leads created on or after this date (YYYY-MM-DD)
    - end_date: Filter leads created on or before this date (YYYY-MM-DD)
    - search: Search by contact name or phone number
    """
    try:
        from datetime import date as date_type
        service = LeadService(db)
        start_d = None
        end_d = None
        if start_date:
            try:
                start_d = date_type.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be YYYY-MM-DD")
        if end_date:
            try:
                end_d = date_type.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be YYYY-MM-DD")
        use_filters = start_d is not None or end_d is not None or (search and search.strip())
        if use_filters:
            statuses = None
            if status_filter:
                statuses = [s.strip() for s in status_filter.split(",")]
                if nurturing:
                    statuses.extend([s.strip() for s in nurturing.split(",")])
                    statuses = list(set(statuses))
            elif nurturing:
                statuses = [s.strip() for s in nurturing.split(",")]
            return await service.list_with_filters(
                company_id=company_id,
                start_date=start_d,
                end_date=end_d,
                search=search.strip() if search else None,
                statuses=statuses,
                skip=skip,
                limit=limit,
            )
        # Sort by priority
        if sort == "priority":
            return await service.get_by_priority(
                company_id=company_id,
                skip=skip,
                limit=limit,
            )
        # Filter by status
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",")]
            if nurturing:
                nurturing_statuses = [s.strip() for s in nurturing.split(",")]
                statuses.extend(nurturing_statuses)
                statuses = list(set(statuses))
            return await service.get_by_statuses(
                company_id=company_id,
                statuses=statuses,
                skip=skip,
                limit=limit,
            )
        # Filter by nurturing only
        if nurturing:
            nurturing_statuses = [s.strip() for s in nurturing.split(",")]
            return await service.get_nurturing(
                company_id=company_id,
                statuses=nurturing_statuses,
                skip=skip,
                limit=limit,
            )
        # Default: return all leads
        return await service.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Error listing leads: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/pipeline", response_model=Dict[str, List[Lead]], responses=RESPONSES)
async def get_pipeline_view(
    company_id: UUID,
    db: DbSession,
    limit: int = Query(20, ge=1, le=500, description="Max leads per pipeline stage"),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> Dict[str, List[Lead]]:
    """
    Get leads grouped by pipeline stage.

    Returns a dictionary with all pipeline stages as keys
    (qualified, unqualified, service_not_offered, booked, appointment_ran, won, lost, review),
    each containing an array of leads in that stage (capped by `limit`).

    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        return await service.get_pipeline_view(company_id=company_id, limit=limit)
    except Exception as e:
        logger.error(f"Error getting pipeline view: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}", response_model=Lead, responses=RESPONSES)
async def get_lead(
    lead_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> Lead:
    """
    Get lead by ID.
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        lead = await service.get_by_id(lead_id)
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return lead
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lead: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}/details", response_model=LeadDetail, responses=RESPONSES)
async def get_lead_details(
    lead_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> LeadDetail:
    """
    Get detailed lead information for lead details page.
    
    Returns comprehensive lead information including:
    - Contact information (name, phone, email)
    - Assigned agent information
    - Overall engagement (summary, key points, action items, appointment status)
    - Conversations array (all calls with this lead, sorted by most recent first)
      Each conversation includes:
      - Call details (type, phone number, duration, transcript, recording URL)
      - Analysis data (summary, key points, objections, sentiment, SOP compliance)
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        lead_detail = await service.get_detail_by_id(lead_id)
        
        if not lead_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return lead_detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lead details: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}/pipeline-detail", response_model=PipelineLeadDetail, responses=RESPONSES)
async def get_pipeline_lead_detail(
    lead_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> PipelineLeadDetail:
    """
    Get 3-tab pipeline lead detail view.

    Returns structured data for the three tabs shown in the pipeline card detail:

    - **lead** (always present): CSR stage — overall engagement (last touched, next move,
      summary, key points) and all conversations (calls) with their analysis data.
    - **appointment** (present when a linked appointment exists): appointment details
      including contact name, assigned sales rep, status, location, date/time, meeting URL.
    - **result** (present when appointment has been conducted): outcome engagement
      (last touched, next move, summary, key points) and the appointment call conversation.

    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        detail = await service.get_pipeline_detail_by_id(lead_id)

        if not detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )

        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pipeline lead detail: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


class AssignLeadRequest(BaseModel):
    """Request to assign a lead to a sales rep."""
    sales_rep_id: UUID = Field(..., description="Sales rep user ID to assign the lead to")


class AssignLeadResponse(BaseModel):
    """Response from lead assignment."""
    lead: Lead
    assigned_by: UUID = Field(..., description="User ID who made the assignment")
    assigned_at: str = Field(..., description="ISO timestamp of assignment")
    assigned_rep_name: Optional[str] = Field(None, description="Name of the assigned sales rep")


class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status."""
    status: str = Field(..., description="New lead status")
    reason: Optional[str] = Field(None, description="Optional reason for the change (audit)")


@router.post("/{lead_id}/assign", response_model=AssignLeadResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def assign_lead(
    lead_id: UUID,
    request: AssignLeadRequest,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> AssignLeadResponse:
    """
    Assign a lead to a sales rep.
    
    A CSR or Executive can assign a lead to a sales rep. The assignment is tracked
    in the lead's metadata, including who assigned it and when.
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        
        # Assign the lead (user.id is the CSR/Executive making the assignment)
        assigned_lead = await service.assign_to_rep(
            lead_id=lead_id,
            sales_rep_id=request.sales_rep_id,
            assigned_by_user_id=user.id,
        )
        
        if not assigned_lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        # Extract assignment info from metadata
        assignment_info = assigned_lead.extra_metadata.get("last_assignment", {}) if assigned_lead.extra_metadata else {}
        assigned_at = assignment_info.get("assigned_at", "")
        
        # Get assigned rep name
        assigned_rep_name = None
        if assigned_lead.assigned_rep_id:
            from app.domain.users.service import UserService
            user_service = UserService(db)
            rep_user = await user_service.get_by_id(assigned_lead.assigned_rep_id)
            if rep_user:
                first_name = rep_user.first_name or ""
                last_name = rep_user.last_name or ""
                assigned_rep_name = f"{first_name} {last_name}".strip() or None
        
        return AssignLeadResponse(
            lead=assigned_lead,
            assigned_by=user.id,
            assigned_at=assigned_at,
            assigned_rep_name=assigned_rep_name,
        )
    except ValueError as e:
        # Validation error (e.g., sales rep not found, wrong company)
        logger.error(f"Validation error assigning lead: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning lead: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign lead: {str(e)}",
        )


@router.put("/{lead_id}/status", response_model=Lead, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def update_lead_status(
    lead_id: UUID,
    request: UpdateLeadStatusRequest,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> Lead:
    """
    Update lead status.
    
    Updates the status of a lead. Valid status values are defined in LeadStatus enum.
    When called by an EXECUTIVE, the change is logged in lead_status_changes (audit).
    
    Access: EXECUTIVE (audit logged), CSR (no audit)
    
    Args:
        lead_id: Lead ID to update
        request: Status update request (status, optional reason)
    """
    try:
        from app.domain.enums import UserRole
        service = LeadService(db)
        # Log to audit table only when changed by executive (admin)
        changed_by = user.id if getattr(user, "role", None) == UserRole.EXECUTIVE.value else None
        updated_lead = await service.update_status(
            lead_id=lead_id,
            status=request.status,
            changed_by_user_id=changed_by,
            reason=request.reason,
        )
        
        if not updated_lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return updated_lead
    except ValueError as e:
        # Validation error (e.g., invalid status)
        logger.error(f"Validation error updating lead status: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update lead status: {str(e)}",
        )

