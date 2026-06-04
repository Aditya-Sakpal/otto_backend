"""
Unified rep work queue service.

Composes three EXISTING rep-scoped surfaces into a single response so a rep can
see their entire actionable workload in one call:

  1. Action Center tasks  → PendingActionService.get_action_center
  2. Unresolved appointments (ran/past, outcome still open)
     → AppointmentRepository.get_by_assigned_rep(past_only=True, outcome="pending")
  3. Pending leads → LeadService.get_pending_leads

Pure composition — no new ranking, scoring, AI, tables, schedulers, or queries.
Reuses ActionCenter* and PendingLeadResultItem response models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.schemas.sales_rep import (
    UnresolvedAppointmentItem,
    WorkQueueResponse,
    WorkQueueSectionCounts,
)
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.services.pending_action_service import PendingActionService
from app.services.lead_service import LeadService

logger = get_logger(__name__)


def build_section_counts(tasks_groups, unresolved, leads) -> WorkQueueSectionCounts:
    """Derive per-section counts from the composed pieces (pure)."""
    task_count = sum(len(g.items) for g in (tasks_groups or []))
    return WorkQueueSectionCounts(
        tasks=task_count,
        unresolved_appointments=len(unresolved or []),
        pending_leads=len(leads or []),
    )


class WorkQueueService:
    """Assembles the unified rep work queue from existing surfaces."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.appointment_repo = AppointmentRepository(session)

    async def _unresolved_appointments(
        self, company_id: UUID, owner_id: UUID, limit: int
    ) -> list[UnresolvedAppointmentItem]:
        """Past appointments still open (outcome pending) for the rep."""
        appts = await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=owner_id,
            past_only=True,
            outcome="pending",
            limit=limit,
        )
        if not appts:
            return []

        # Batch-fetch contact names (single query, no N+1).
        contact_ids = list({a.contact_card_id for a in appts if a.contact_card_id})
        names: dict[UUID, str] = {}
        if contact_ids:
            rows = await self.session.execute(
                select(ContactCardORM).where(ContactCardORM.id.in_(contact_ids))
            )
            for c in rows.scalars().all():
                full = f"{c.first_name or ''} {c.last_name or ''}".strip() or None
                names[c.id] = full

        items: list[UnresolvedAppointmentItem] = []
        for a in appts:
            outcome = a.outcome.value if hasattr(a.outcome, "value") else a.outcome
            items.append(UnresolvedAppointmentItem(
                appointment_id=a.id,
                lead_id=a.lead_id,
                contact_card_id=a.contact_card_id,
                customer_name=names.get(a.contact_card_id),
                scheduled_start=a.scheduled_start,
                outcome=outcome,
                analysis_status=a.analysis_status,
                location_address=a.location_address,
            ))
        return items

    async def get_work_queue(
        self,
        *,
        company_id: UUID,
        owner_id: UUID,
        limit: int = 50,
    ) -> WorkQueueResponse:
        """Compose tasks + unresolved appointments + pending leads for one rep."""
        # 1. Tasks (Action Center) — reuses ranking + next pointer.
        action_center = await PendingActionService(self.session).get_action_center(
            company_id=company_id, owner_id=owner_id, limit=limit
        )

        # 2. Unresolved appointments (ran/past, outcome open).
        unresolved = await self._unresolved_appointments(company_id, owner_id, limit)

        # 3. Pending leads (rep-scoped).
        leads_resp = await LeadService(self.session).get_pending_leads(
            company_id=company_id, rep_id=owner_id, limit=limit, offset=0
        )
        pending_leads = leads_resp.results if leads_resp else []

        return WorkQueueResponse(
            generated_at=datetime.now(ZoneInfo("UTC")),
            company_id=company_id,
            owner_id=owner_id,
            next_action=action_center.next,
            task_summary=action_center.summary,
            tasks=action_center.groups,
            unresolved_appointments=unresolved,
            pending_leads=pending_leads,
            section_counts=build_section_counts(action_center.groups, unresolved, pending_leads),
        )
