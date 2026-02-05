"""
Appointment service.

Provides business logic for managing appointments:
- CRUD operations
- Listing by company, lead, or assigned sales rep
- Enriched responses with contact and user details
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.appointment import Appointment
from app.domain.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
)
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.domain.users.repository import UserRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.call import CallRepository

logger = get_logger(__name__)


class AppointmentService:
    """Service for appointment-related operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.appointment_repo = AppointmentRepository(session)
        self.contact_repo = ContactRepository(session)
        self.user_repo = UserRepository(session)
        self.analysis_repo = CallAnalysisRepository(session)
        self.call_repo = CallRepository(session)

    async def get_by_id(self, appointment_id: UUID) -> Optional[Appointment]:
        """Get appointment by ID."""
        return await self.appointment_repo.get_by_id(appointment_id)

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company."""
        return await self.appointment_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """
        Get all appointments for a company assigned to a specific sales rep.

        Args:
            company_id: Company/tenant ID
            assigned_rep_id: Assigned sales rep user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
        """
        return await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_lead(
        self,
        lead_id: UUID,
    ) -> Optional[Appointment]:
        """Get appointment by associated lead ID."""
        return await self.appointment_repo.get_by_lead_id(lead_id)

    async def create(self, appointment: Appointment) -> Appointment:
        """Create a new appointment from a domain model."""
        try:
            return await self.appointment_repo.create(appointment)
        except Exception as e:
            logger.error(f"Error creating appointment: {e}")
            raise

    async def create_from_schema(
        self,
        data: AppointmentCreate,
    ) -> Appointment:
        """Create a new appointment from an API schema."""
        try:
            appointment = Appointment(
                **data.model_dump(),
            )
            return await self.appointment_repo.create(appointment)
        except Exception as e:
            logger.error(f"Error creating appointment from schema: {e}")
            raise

    async def update(
        self,
        appointment_id: UUID,
        data: AppointmentUpdate,
    ) -> Optional[Appointment]:
        """Update an existing appointment from an API schema."""
        try:
            existing = await self.appointment_repo.get_by_id(appointment_id)
            if not existing:
                return None

            update_dict = data.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                setattr(existing, key, value)
            existing.mark_updated()

            return await self.appointment_repo.update(appointment_id, existing)
        except Exception as e:
            logger.error(f"Error updating appointment: {e}")
            raise

    async def delete(self, appointment_id: UUID) -> bool:
        """Delete an appointment."""
        try:
            return await self.appointment_repo.delete(appointment_id)
        except Exception as e:
            logger.error(f"Error deleting appointment: {e}")
            raise

    async def _enrich_appointment_response(
        self,
        appointment: Appointment,
        include_full_details: bool = False,
    ) -> AppointmentResponse:
        """
        Enrich appointment with contact and user details.

        Args:
            appointment: Appointment domain model
            include_full_details: If True, includes full contact_details and assigned_rep_details

        Returns:
            Enriched AppointmentResponse
        """
        response_data = AppointmentResponse.model_validate(appointment).model_dump()

        # Get contact details
        if appointment.contact_card_id:
            contact_card = await self.contact_repo.get_by_id(appointment.contact_card_id)
            if contact_card:
                first_name = contact_card.first_name or ""
                last_name = contact_card.last_name or ""
                response_data["appointment_name"] = f"{first_name} {last_name}".strip() or None

                if include_full_details:
                    response_data["contact_details"] = {
                        "id": str(contact_card.id),
                        "first_name": contact_card.first_name,
                        "last_name": contact_card.last_name,
                        "email": contact_card.email,
                        "primary_phone": contact_card.primary_phone,
                        "secondary_phone": contact_card.secondary_phone,
                        "address": contact_card.address,
                        "city": contact_card.city,
                        "state": contact_card.state,
                        "postal_code": contact_card.postal_code,
                    }

        # Get assigned rep details
        if appointment.assigned_rep_id:
            rep_user = await self.user_repo.get_by_id(appointment.assigned_rep_id)
            if rep_user:
                first_name = rep_user.first_name or ""
                last_name = rep_user.last_name or ""
                response_data["sales_rep_name"] = f"{first_name} {last_name}".strip() or None

                if include_full_details:
                    response_data["assigned_rep_details"] = {
                        "id": str(rep_user.id),
                        "email": rep_user.email,
                        "first_name": rep_user.first_name,
                        "last_name": rep_user.last_name,
                        "role": rep_user.role.value if hasattr(rep_user.role, 'value') else str(rep_user.role),
                        "is_active": rep_user.is_active,
                    }

        return AppointmentResponse(**response_data)

    async def get_enriched_by_id(self, appointment_id: UUID) -> Optional[AppointmentResponse]:
        """
        Get appointment by ID with enriched contact and rep details.

        Args:
            appointment_id: Appointment UUID

        Returns:
            Enriched AppointmentResponse or None if not found
        """
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return None

        return await self._enrich_appointment_response(appointment, include_full_details=True)

    async def list_enriched_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AppointmentResponse]:
        """
        Get all appointments for a company with enriched names.

        Args:
            company_id: Company UUID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of enriched AppointmentResponse objects
        """
        appointments = await self.appointment_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )

        return [
            await self._enrich_appointment_response(appointment, include_full_details=False)
            for appointment in appointments
        ]

    async def list_enriched_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AppointmentResponse]:
        """
        Get all appointments for a company assigned to a specific sales rep with enriched names.

        Args:
            company_id: Company UUID
            assigned_rep_id: Assigned sales rep user ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of enriched AppointmentResponse objects
        """
        appointments = await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )

        return [
            await self._enrich_appointment_response(appointment, include_full_details=False)
            for appointment in appointments
        ]

    async def get_enriched_by_lead(self, lead_id: UUID) -> Optional[AppointmentResponse]:
        """
        Get appointment by lead ID with enriched names.

        Args:
            lead_id: Lead UUID

        Returns:
            Enriched AppointmentResponse or None if not found
        """
        appointment = await self.appointment_repo.get_by_lead_id(lead_id)
        if not appointment:
            return None

        return await self._enrich_appointment_response(appointment, include_full_details=False)

    async def get_appointment_insights(self, appointment_id: UUID) -> Dict[str, Any]:
        """
        Get insights for an appointment.

        Returns call analysis insights for the appointment's associated call/interaction.

        Args:
            appointment_id: Appointment UUID

        Returns:
            Dictionary with appointment_id, status, and insights
        """
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return {
                "appointment_id": str(appointment_id),
                "status": "not_found",
                "insights": None,
            }

        # Check if appointment has an interaction_id
        if not appointment.interaction_id:
            return {
                "appointment_id": str(appointment_id),
                "status": "not_found",
                "insights": None,
            }

        # Get call analysis by call_id (interaction_id)
        analysis = await self.analysis_repo.get_by_call_id(appointment.interaction_id)

        if not analysis:
            # Check if call exists and its status
            call = await self.call_repo.get_by_id(appointment.interaction_id)

            if call:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "pending",
                    "insights": None,
                }
            else:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "not_found",
                    "insights": None,
                }

        # Build insights response
        objections = [
            obj.value if hasattr(obj, "value") else str(obj) for obj in analysis.objections
        ] if analysis.objections else []

        insights = {
            "summary": analysis.summary or "",
            "key_points": analysis.key_points or [],
            "sop_stages_completed": analysis.sop_stages_completed or [],
            "sop_stages_missed": analysis.sop_stages_missed or [],
            "objections": objections,
            "objections_found": objections,  # Backwards compatibility
            "action_items": analysis.action_items or [],
            "tasks": analysis.action_items or [],  # Alias for action_items
            "follow_up_required": analysis.follow_up_required,
            "follow_up_reason": analysis.follow_up_reason,
            "sentiment": analysis.sentiment_score if analysis.sentiment_score is not None else None,
            "sop_score": analysis.sop_compliance_score if analysis.sop_compliance_score is not None else None,
        }

        return {
            "appointment_id": str(appointment_id),
            "status": analysis.status.value if hasattr(analysis.status, 'value') else str(analysis.status),
            "insights": insights,
        }

