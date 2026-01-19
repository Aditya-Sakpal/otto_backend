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
from app.domain.models.lead_detail import LeadDetail
from app.domain.users.models import User
from app.services.lead_service import LeadService
from pydantic import BaseModel, Field

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[Lead])
async def list_leads(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
    status_filter: Optional[str] = Query(None, alias="status"),
    nurturing: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
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
    """
    try:
        service = LeadService(db)
        
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
            
            # If nurturing is specified, add those statuses
            if nurturing:
                nurturing_statuses = [s.strip() for s in nurturing.split(",")]
                statuses.extend(nurturing_statuses)
                statuses = list(set(statuses))  # Remove duplicates
            
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


@router.get("/{lead_id}", response_model=Lead)
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


@router.get("/{lead_id}/details", response_model=LeadDetail)
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


class AssignLeadRequest(BaseModel):
    """Request to assign a lead to a sales rep."""
    sales_rep_id: UUID = Field(..., description="Sales rep user ID to assign the lead to")


class AssignLeadResponse(BaseModel):
    """Response from lead assignment."""
    lead: Lead
    assigned_by: UUID = Field(..., description="User ID who made the assignment")
    assigned_at: str = Field(..., description="ISO timestamp of assignment")


@router.post("/{lead_id}/assign", response_model=AssignLeadResponse, status_code=status.HTTP_200_OK)
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
        
        return AssignLeadResponse(
            lead=assigned_lead,
            assigned_by=user.id,
            assigned_at=assigned_at,
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

