"""
Leads API routes.

Provides lead management endpoints.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_manager_or_csr, require_manager_or_sales_rep
from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.users.models import User
from app.services.lead_service import LeadService

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

