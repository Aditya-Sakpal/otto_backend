"""
Appointments API routes.

Provides appointment management endpoints.
"""
import traceback
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.models.appointment import Appointment
from app.domain.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
)
from app.domain.users.models import User
from app.services.appointment_service import AppointmentService
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    db: DbSession,
    company_id: UUID = Query(..., description="Company/tenant ID"),
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
    assigned_rep_id: Optional[UUID] = Query(
        None,
        description="Filter appointments by assigned sales rep (user_id)",
    ),
    lead_id: Optional[UUID] = Query(
        None,
        description="Filter by associated lead ID (overrides company filter if provided)",
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> List[AppointmentResponse]:
    """
    List appointments with optional filters.

    Access: Any authenticated user

    Query Parameters:
    - company_id: Filter by company/tenant
    - assigned_rep_id: Filter by assigned sales rep (user_id)
    - lead_id: Filter by associated lead (if provided, company filter is ignored)
    - skip: Pagination offset
    - limit: Maximum number of results (1-1000)
    """
    try:
        service = AppointmentService(db)

        # If lead_id is provided, return appointment for that lead
        if lead_id:
            appointment = await service.get_by_lead(lead_id)
            return (
                [AppointmentResponse.model_validate(appointment)]
                if appointment
                else []
            )

        # Filter by assigned rep if provided
        if assigned_rep_id:
            appointments = await service.get_by_assigned_rep(
                company_id=company_id,
                assigned_rep_id=assigned_rep_id,
                skip=skip,
                limit=limit,
            )
            return [AppointmentResponse.model_validate(a) for a in appointments]

        # Default: return all appointments for company
        appointments = await service.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
        return [AppointmentResponse.model_validate(a) for a in appointments]
    except Exception as e:
        logger.error(f"Error listing appointments: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> AppointmentResponse:
    """
    Get appointment by ID.

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)
        appointment = await service.get_by_id(appointment_id)

        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        return AppointmentResponse.model_validate(appointment)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    appointment_data: AppointmentCreate,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> AppointmentResponse:
    """
    Create a new appointment.

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)
        appointment = await service.create_from_schema(appointment_data)
        return AppointmentResponse.model_validate(appointment)
    except Exception as e:
        logger.error(f"Error creating appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    appointment_data: AppointmentUpdate,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> AppointmentResponse:
    """
    Update an existing appointment.

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)
        updated = await service.update(appointment_id, appointment_data)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        return AppointmentResponse.model_validate(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
) -> None:
    """
    Delete an appointment.

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)
        deleted = await service.delete(appointment_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{appointment_id}/insights")
async def get_appointment_insights(
    appointment_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
):
    """
    Get insights for an appointment.

    Returns call analysis insights for the appointment's associated call/interaction.
    If no interaction_id exists or no analysis is available, returns appropriate status.

    Access: Any authenticated user

    Returns:
        {
            "appointment_id": "...",
            "status": "completed" | "pending" | "processing" | "not_found",
            "insights": {
                "summary": "...",
                "sentiment": 0.85,
                "sop_score": 0.9,
                "objections_found": ["Price", "Competitor"]
            } | null
        }
    """
    try:
        appointment_repo = AppointmentRepository(db)
        analysis_repo = CallAnalysisRepository(db)
        
        # Get appointment
        appointment = await appointment_repo.get_by_id(appointment_id)
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )
        
        # Check if appointment has an interaction_id
        if not appointment.interaction_id:
            return {
                "appointment_id": str(appointment_id),
                "status": "not_found",
                "insights": None,
            }
        
        # Get call analysis by call_id (interaction_id)
        analysis = await analysis_repo.get_by_call_id(appointment.interaction_id)
        
        if not analysis:
            # Check if call exists and its status
            from app.infrastructure.repositories.call import CallRepository
            call_repo = CallRepository(db)
            call = await call_repo.get_by_id(appointment.interaction_id)
            
            if call:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "pending",  # Default status since field doesn't exist in DB
                    "insights": None,
                }
            else:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "not_found",
                    "insights": None,
                }
        
        # Build insights response
        insights = {
            "summary": analysis.summary or "",
            "sentiment": analysis.sentiment_score if analysis.sentiment_score is not None else None,
            "sop_score": analysis.sop_compliance_score if analysis.sop_compliance_score is not None else None,
            "objections_found": [obj.value if hasattr(obj, 'value') else str(obj) for obj in analysis.objections] if analysis.objections else [],
        }
        
        return {
            "appointment_id": str(appointment_id),
            "status": analysis.status.value if hasattr(analysis.status, 'value') else str(analysis.status),
            "insights": insights,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting appointment insights: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

