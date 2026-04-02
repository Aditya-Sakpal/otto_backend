"""
Appointments API routes.

Provides appointment management endpoints.
"""
import traceback
from datetime import date as date_type, datetime as datetime_type, time as time_type, timezone as tz
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.schemas.appointment import (
    APPOINTMENT_CONTEXT_RESPONSE_EXAMPLE,
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentLocationUpdate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentInsightSummary,
    AppointmentContextResponse,
    AppointmentsTodayResponse,
)
from app.infrastructure.integrations.google_geocoding import get_google_geocoding_client
from app.domain.users.models import User
from app.domain.users.repository import UserRepository
from app.services.appointment_service import AppointmentService

router = APIRouter()
logger = get_logger(__name__)


def _normalize_objections(raw_objections: list) -> list:
    """Convert plain-string objections to ObjectionDetail-compatible dicts."""
    normalized = []
    for item in raw_objections:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str):
            normalized.append({
                "category_id": 0,
                "category_text": item,
                "objection_text": item,
                "overcome": False,
                "severity": "medium",
                "confidence_score": 0.0,
                "response_suggestions": [],
            })
    return normalized


RESPONSES = {
    400: {"description": "Bad request (e.g. invalid date format)"},
    403: {"description": "Forbidden"},
    404: {"description": "Appointment not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}



@router.get("", response_model=List[AppointmentResponse], responses=RESPONSES)
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
    start_date: Optional[str] = Query(
        None,
        description="Filter appointments on or after this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="Filter appointments on or before this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
    outcome: Optional[str] = Query(
        None,
        description="Filter by outcome: pending, won, lost, no_show, rescheduled (case-insensitive; aliases: in progress, no show)",
    ),
    search: Optional[str] = Query(
        None,
        description="Search contact name/phone, assigned rep name, or location (whitespace-separated terms, all must match)",
    ),
    q: Optional[str] = Query(
        None,
        description="Alias for search (some clients use q=)",
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
    - start_date: Filter appointments on or after this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - end_date: Filter appointments on or before this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - outcome: Filter by appointment outcome (pending / won / lost / no_show / rescheduled)
    - search / q: Text search (contact, rep, location)
    - skip: Pagination offset
    - limit: Maximum number of results (1-1000)
    """
    try:
        from datetime import date as date_type, datetime as datetime_type, timezone as tz

        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime_type.fromisoformat(start_date)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=tz.utc)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="start_date must be ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )
        if end_date:
            try:
                end_dt = datetime_type.fromisoformat(end_date)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=tz.utc)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="end_date must be ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )

        service = AppointmentService(db)
        search_effective = (search or q or "").strip() or None

        # If lead_id is provided, return appointment for that lead
        if lead_id:
            appointment = await service.get_enriched_by_lead(lead_id)
            return [appointment] if appointment else []

        # Filter by assigned rep if provided — ensure user is a sales rep
        if assigned_rep_id:
            user_repo = UserRepository(db)
            rep_user = await user_repo.get_by_id(assigned_rep_id)
            if rep_user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="assigned_rep_id: user not found",
                )
            if rep_user.role != UserRole.SALES_REP:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="assigned_rep_id must be a user with role sales_rep",
                )
            return await service.list_enriched_by_assigned_rep(
                company_id=company_id,
                assigned_rep_id=assigned_rep_id,
                start_date=start_dt,
                end_date=end_dt,
                skip=skip,
                limit=limit,
                outcome=outcome,
                search=search_effective,
            )

        # Default: return all appointments for company
        return await service.list_enriched_by_company(
            company_id=company_id,
            start_date=start_dt,
            end_date=end_dt,
            skip=skip,
            limit=limit,
            outcome=outcome,
            search=search_effective,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing appointments: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/past", response_model=List[AppointmentResponse], responses=RESPONSES)
async def list_past_appointments(
    db: DbSession,
    company_id: UUID = Query(..., description="Company/tenant ID"),
    # RBAC DISABLED - user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),  # RBAC DISABLED - Returns dummy user
    assigned_rep_id: Optional[UUID] = Query(
        None,
        description="Filter appointments by assigned sales rep (user_id)",
    ),
    start_date: Optional[str] = Query(
        None,
        description="Filter appointments on or after this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="Filter appointments on or before this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
    outcome: Optional[str] = Query(
        None,
        description="Filter by outcome: pending, won, lost, no_show, rescheduled",
    ),
    search: Optional[str] = Query(None, description="Search contact, rep, or location"),
    q: Optional[str] = Query(None, description="Alias for search"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> List[AppointmentResponse]:
    """
    List past appointments (scheduled_start in the past) with optional filters.

    Access: Any authenticated user

    Query Parameters:
    - company_id: Filter by company/tenant
    - assigned_rep_id: Filter by assigned sales rep (user_id)
    - start_date: Filter appointments on or after this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - end_date: Filter appointments on or before this datetime (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - skip: Pagination offset
    - limit: Maximum number of results (1-1000)
    """
    try:
        from datetime import datetime as datetime_type, timezone as tz

        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime_type.fromisoformat(start_date)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=tz.utc)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="start_date must be ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )
        if end_date:
            try:
                end_dt = datetime_type.fromisoformat(end_date)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=tz.utc)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="end_date must be ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )

        service = AppointmentService(db)
        search_effective = (search or q or "").strip() or None

        if assigned_rep_id:
            user_repo = UserRepository(db)
            rep_user = await user_repo.get_by_id(assigned_rep_id)
            if rep_user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="assigned_rep_id: user not found",
                )
            if rep_user.role != UserRole.SALES_REP:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="assigned_rep_id must be a user with role sales_rep",
                )
            return await service.list_enriched_by_assigned_rep(
                company_id=company_id,
                assigned_rep_id=assigned_rep_id,
                start_date=start_dt,
                end_date=end_dt,
                past_only=True,
                skip=skip,
                limit=limit,
                outcome=outcome,
                search=search_effective,
            )

        return await service.list_enriched_by_company(
            company_id=company_id,
            start_date=start_dt,
            end_date=end_dt,
            past_only=True,
            skip=skip,
            limit=limit,
            outcome=outcome,
            search=search_effective,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing past appointments: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/upcoming", response_model=List[AppointmentResponse], responses=RESPONSES)
async def list_upcoming_appointments(
    db: DbSession,
    company_id: UUID = Query(..., description="Company/tenant ID"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    assigned_rep_id: Optional[UUID] = Query(
        None,
        description="Filter appointments by assigned sales rep (user_id)",
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> List[AppointmentResponse]:
    """
    List upcoming appointments (future, pending status only).

    Returns appointments with:
    - scheduled_start >= now (future)
    - outcome is None or 'pending'
    - Sorted by scheduled_start ASC (soonest first)

    Access: Any authenticated user

    Query Parameters:
    - company_id: Filter by company/tenant
    - assigned_rep_id: Filter by assigned sales rep (user_id)
    - skip: Pagination offset
    - limit: Maximum number of results (1-1000)
    """
    try:
        service = AppointmentService(db)

        if assigned_rep_id:
            user_repo = UserRepository(db)
            rep_user = await user_repo.get_by_id(assigned_rep_id)
            if rep_user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="assigned_rep_id: user not found",
                )
            if rep_user.role != UserRole.SALES_REP:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="assigned_rep_id must be a user with role sales_rep",
                )

        return await service.list_upcoming_appointments(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing upcoming appointments: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/today", response_model=AppointmentsTodayResponse, responses=RESPONSES)
async def get_appointments_today(
    db: DbSession,
    company_id: UUID = Query(..., description="Company/tenant ID"),
    assigned_rep_id: UUID = Query(..., description="Assigned sales rep user ID"),
    date: str = Query(..., description="Date in UTC (YYYY-MM-DD)"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    Get appointments and counts for a sales rep on a specific date.

    Returns the list of enriched appointments and counts (total, pending, closed)
    for the given rep on the given UTC date.

    Access: Any authenticated user
    """
    try:
        # Parse date
        try:
            parsed_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date must be YYYY-MM-DD format",
            )

        utc_start = datetime_type.combine(parsed_date, time_type.min, tzinfo=tz.utc)
        utc_end = datetime_type.combine(parsed_date, time_type.max, tzinfo=tz.utc)

        service = AppointmentService(db)
        return await service.get_today_summary(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            utc_start=utc_start,
            utc_end=utc_end,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting today's appointments: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/counts", responses=RESPONSES)
async def get_appointment_counts(
    db: DbSession,
    company_id: UUID = Query(..., description="Company/tenant ID"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
    assigned_rep_id: Optional[UUID] = Query(
        None,
        description="Filter by assigned sales rep (user_id)",
    ),
):
    """
    Get appointment counts: total today, pending, and closed.

    Returns:
    - total_today: Number of appointments scheduled for today
    - pending: Number of appointments with pending outcome
    - closed: Number of appointments with closed outcome (won or lost)

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)
        return await service.get_appointment_counts(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
        )
    except Exception as e:
        logger.error(f"Error getting appointment counts: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{appointment_id}", response_model=AppointmentResponse, responses=RESPONSES)
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
        appointment = await service.get_enriched_by_id(appointment_id)

        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

        insights_result = await service.get_appointment_insights(appointment_id)
        insights_payload = insights_result.get("insights") if insights_result else None

        insights_model = None
        if insights_payload:
            insights_model = AppointmentInsightSummary(
                summary=insights_payload.get("summary"),
                key_points=insights_payload.get("key_points") or [],
                sop_stages_completed=insights_payload.get("sop_stages_completed") or [],
                sop_stages_missed=insights_payload.get("sop_stages_missed") or [],
                objections=_normalize_objections(
                    insights_payload.get("objections")
                    or insights_payload.get("objections_found")
                    or []
                ),
                action_items=insights_payload.get("action_items") or [],
                follow_up_required=insights_payload.get("follow_up_required"),
                follow_up_reason=insights_payload.get("follow_up_reason"),
            )

        return appointment.model_copy(update={"insights": insights_model})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{appointment_id}/context",
    response_model=AppointmentContextResponse,
    responses={
        **RESPONSES,
        200: {
            "description": "Appointment context; `phases` sits after `audio_url`, before `appointment_analysis`",
            "content": {
                "application/json": {
                    "example": APPOINTMENT_CONTEXT_RESPONSE_EXAMPLE,
                }
            },
        },
    },
)
async def get_appointment_context(
    appointment_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get comprehensive appointment context for pre-meeting intelligence.

    Returns appointment details, lead info, contact info, CSR conversation history,
    previous objections, pending actions, AI-generated briefing, and optional **follow_up**
    (manual-review drafts from the contextual follow-up agent).

    **`phases`** (between `audio_url` and `appointment_analysis`): Shoonya conversation phases
    for the appointment **interaction** call (`interaction_id` → GET .../calls/{call_id}/phases).
    Omitted or null when there is no linked interaction or Shoonya is unavailable.

    **Example `follow_up` fragment (200)** — present when the company uses manual review and drafts exist:

    ```json
    "follow_up": {
      "manual_review_enabled": true,
      "pending_messages": [
        {
          "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
          "action_type": "sms_to_lead",
          "status": "proposed",
          "message_content": "Hi Jane — following up on your roof estimate.",
          "scheduled_at": "2026-03-27T18:00:00Z",
          "created_at": "2026-03-27T17:05:00Z",
          "queue_type": "appointment_ran",
          "attempt_number": 1
        }
      ]
    }
    ```

    **Wave 2: Pre-Meeting Intelligence**

    Access: Sales reps and executives only
    """
    try:
        service = AppointmentService(db)
        context = await service.get_appointment_context(appointment_id)

        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment {appointment_id} not found or missing required data",
            )

        return context
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching appointment context: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch appointment context: {str(e)}",
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


@router.put("/reschedule", response_model=AppointmentResponse, responses=RESPONSES)
async def reschedule_appointment(
    payload: AppointmentReschedule,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> AppointmentResponse:
    """
    Reschedule an appointment by updating its start and end times.

    Identify the appointment by providing either `appointment_id` or `lead_id`
    in the request body (exactly one required).

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)

        if payload.appointment_id:
            existing = await service.get_by_id(payload.appointment_id)
            not_found_msg = "Appointment not found"
        else:
            existing = await service.get_by_lead(payload.lead_id)
            not_found_msg = "No appointment found for this lead"

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=not_found_msg,
            )

        existing.scheduled_start = payload.scheduled_start
        existing.scheduled_end = payload.scheduled_end
        existing.mark_updated()

        updated = await service.appointment_repo.update(existing.id, existing)

        return AppointmentResponse.model_validate(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rescheduling appointment: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/location", response_model=AppointmentResponse, responses=RESPONSES)
async def update_appointment_location(
    payload: AppointmentLocationUpdate,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
) -> AppointmentResponse:
    """
    Update an appointment's location address and re-geocode coordinates.

    Identify the appointment by providing either `appointment_id` or `lead_id`
    in the request body (exactly one required).

    Access: Any authenticated user
    """
    try:
        service = AppointmentService(db)

        if payload.appointment_id:
            existing = await service.get_by_id(payload.appointment_id)
            not_found_msg = "Appointment not found"
        else:
            existing = await service.get_by_lead(payload.lead_id)
            not_found_msg = "No appointment found for this lead"

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=not_found_msg,
            )

        # Geocode the new address
        geocoding_client = get_google_geocoding_client()
        coords = await geocoding_client.geocode(address=payload.location_address)

        if coords:
            lat, lng = coords
            logger.info(f"Geocoded appointment {existing.id}: ({lat}, {lng})")
        else:
            lat, lng = None, None
            logger.warning(f"Geocoding returned no results for: {payload.location_address}")

        # Update address + coordinates in one shot
        existing.location_address = payload.location_address
        existing.latitude = lat
        existing.longitude = lng
        existing.mark_updated()

        updated = await service.appointment_repo.update(existing.id, existing)

        return AppointmentResponse.model_validate(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating appointment location: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/{appointment_id}", response_model=AppointmentResponse, responses=RESPONSES)
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
