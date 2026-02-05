"""
Sales rep service.

Provides follow-ups and tasks for appointments from call analysis.
"""
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.analysis import CallAnalysisORM

logger = get_logger(__name__)


class SalesRepService:
    """Service for sales rep–specific data (follow-ups, tasks from analysis)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_follow_up_for_appointment(self, appointment_id: UUID) -> Optional[dict[str, Any]]:
        """
        Get follow-ups needed for an appointment from the call analysis.

        Uses appointment.interaction_id (call_id) to find analysis, then returns
        follow_up_required, follow_up_reason, and follow_ups (next_steps).
        """
        appointment = await self._get_appointment_with_analysis(appointment_id)
        if not appointment:
            return None
        analysis = appointment.get("analysis")
        if not analysis:
            return None
        next_steps = getattr(analysis, "next_steps", None) or []
        follow_ups = list(next_steps) if next_steps else []
        return {
            "appointment_id": str(appointment_id),
            "follow_up_required": getattr(analysis, "follow_up_required", False),
            "follow_up_reason": getattr(analysis, "follow_up_reason", None),
            "follow_ups": follow_ups,
        }

    async def get_tasks_for_appointment(self, appointment_id: UUID) -> Optional[dict[str, Any]]:
        """
        Get tasks for an appointment from the call analysis.

        Returns action_items, next_steps, and pending_actions.
        """
        appointment = await self._get_appointment_with_analysis(appointment_id)
        if not appointment:
            return None
        analysis = appointment.get("analysis")
        if not analysis:
            return None
        action_items = getattr(analysis, "action_items", None) or []
        next_steps = getattr(analysis, "next_steps", None) or []
        pending_actions = getattr(analysis, "pending_actions", None) or []
        return {
            "appointment_id": str(appointment_id),
            "action_items": list(action_items),
            "next_steps": list(next_steps),
            "pending_actions": list(pending_actions) if isinstance(pending_actions, list) else pending_actions,
        }

    async def _get_appointment_with_analysis(
        self, appointment_id: UUID
    ) -> Optional[dict[str, Any]]:
        """Load appointment and its analysis (via interaction_id -> call -> analysis)."""
        result = await self.session.execute(
            select(AppointmentORM).where(AppointmentORM.id == appointment_id)
        )
        appointment = result.scalar_one_or_none()
        if not appointment or not appointment.interaction_id:
            return None
        call_id = appointment.interaction_id
        analysis_result = await self.session.execute(
            select(CallAnalysisORM).where(CallAnalysisORM.call_id == call_id)
        )
        analysis = analysis_result.scalar_one_or_none()
        if not analysis:
            return None
        return {"appointment": appointment, "analysis": analysis}
