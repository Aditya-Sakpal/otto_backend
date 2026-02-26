"""
Lead service.

Orchestrates lead-related business logic.
"""
from datetime import date, datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import LeadDetail, PipelineLeadDetail
from app.domain.schemas.sales_rep import (
    PendingLeadsResponse,
    PendingLeadResultItem,
    PendingLeadCustomer,
    PendingLeadSalesContext,
    PendingLeadAppointment,
    PendingLeadWorkflow,
)
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.pending_action import PendingActionORM

logger = get_logger(__name__)


class LeadService:
    """Service for lead-related operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.lead_repo = LeadRepository(session)
    
    async def get_by_id(self, lead_id: UUID) -> Optional[Lead]:
        """Get lead by ID."""
        return await self.lead_repo.get_by_id(lead_id)
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get all leads for a company."""
        return await self.lead_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )

    async def list_with_filters(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads with optional date range, search (name/phone), and status filters."""
        return await self.lead_repo.get_list_with_filters(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            search=search,
            statuses=statuses,
            skip=skip,
            limit=limit,
        )
    
    async def get_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads by status filter."""
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=statuses,
            skip=skip,
            limit=limit,
        )
    
    async def get_unbooked(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get qualified_unbooked leads."""
        return await self.lead_repo.get_unbooked(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    
    async def get_by_priority(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads sorted by priority."""
        return await self.lead_repo.get_by_priority(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    
    async def get_nurturing(
        self,
        company_id: UUID,
        statuses: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get nurturing leads (new, warm, hot)."""
        if statuses is None:
            statuses = ["new", "warm", "hot"]
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=statuses,
            skip=skip,
            limit=limit,
        )
    
    async def get_lost(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get lost leads (closed_lost, abandoned, dormant)."""
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=["closed_lost", "abandoned", "dormant"],
            skip=skip,
            limit=limit,
        )
    
    async def get_pipeline_view(
        self,
        company_id: UUID,
        limit: int = 20,
    ) -> dict:
        """
        Get leads grouped by pipeline stage.

        Returns a dictionary with all pipeline stages as keys,
        each containing an array of leads in that stage (capped by limit).
        """
        from app.domain.enums import PipelineStage

        # Initialize all stages with empty lists
        pipeline: dict = {stage.value: [] for stage in PipelineStage}

        # Fetch all leads that have a pipeline_stage
        leads = await self.lead_repo.get_by_pipeline_stages(company_id=company_id)

        for lead in leads:
            ps = lead.pipeline_stage
            stage_value = ps.value if hasattr(ps, "value") else ps
            if stage_value and stage_value in pipeline:
                if len(pipeline[stage_value]) < limit:
                    pipeline[stage_value].append(lead)

        return pipeline

    async def get_detail_by_id(self, lead_id: UUID) -> Optional[LeadDetail]:
        """Get detailed lead information for lead details page."""
        return await self.lead_repo.get_detail_by_id(lead_id)

    async def get_pipeline_detail_by_id(self, lead_id: UUID) -> Optional[PipelineLeadDetail]:
        """Get 3-tab pipeline lead detail (lead, appointment, result)."""
        return await self.lead_repo.get_pipeline_detail_by_id(lead_id)

    async def get_pending_leads(
        self,
        company_id: UUID,
        rep_id: UUID,
        status_filter: Optional[str] = None,
        urgency_only: bool = False,
        sort_by: str = "last_touched",
        limit: int = 10,
        offset: int = 0,
    ) -> PendingLeadsResponse:
        """
        Get pending leads for a sales rep with filters and pagination.

        Returns structured response with customer, sales_context, appointment, workflow per lead.
        """
        lead_orms, total = await self.lead_repo.get_pending_leads_for_rep(
            company_id=company_id,
            rep_id=rep_id,
            status_filter=status_filter,
            urgency_only=urgency_only,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )
        if not lead_orms:
            return PendingLeadsResponse(total_count=total, count=0, results=[])

        lead_ids = [l.id for l in lead_orms]
        appointments_result = await self.session.execute(
            select(AppointmentORM)
            .where(AppointmentORM.lead_id.in_(lead_ids))
            .order_by(AppointmentORM.scheduled_start.asc())
        )
        appointments_all = appointments_result.scalars().all()
        lead_to_appointment: dict = {}
        for appt in appointments_all:
            if appt.lead_id not in lead_to_appointment:
                lead_to_appointment[appt.lead_id] = appt

        rep_name = None
        rep_result = await self.session.execute(
            select(UserORM).where(UserORM.id == rep_id)
        )
        rep_orm = rep_result.scalar_one_or_none()
        if rep_orm:
            first_name = rep_orm.first_name or ""
            last_name = rep_orm.last_name or ""
            rep_name = f"{first_name} {last_name}".strip() or None

        pending_counts: dict = {}
        if lead_ids:
            count_result = await self.session.execute(
                select(PendingActionORM.lead_id, sql_func.count(PendingActionORM.id))
                .where(
                    PendingActionORM.lead_id.in_(lead_ids),
                    PendingActionORM.status == "pending",
                )
                .group_by(PendingActionORM.lead_id)
            )
            for row in count_result:
                pending_counts[row[0]] = row[1]

        results: List[PendingLeadResultItem] = []
        for lead_orm in lead_orms:
            contact = lead_orm.contact_card
            full_name = None
            phone = None
            address = None
            if contact:
                first_name = contact.first_name or ""
                last_name = contact.last_name or ""
                full_name = f"{first_name} {last_name}".strip() or None
                phone = contact.primary_phone
                parts = [contact.address] if contact.address else []
                if contact.city or contact.state or contact.postal_code:
                    parts.append(
                        ", ".join(
                            filter(
                                None,
                                [contact.city, contact.state, contact.postal_code],
                            )
                        )
                    )
                address = ", ".join(filter(None, parts)) if parts else None

            calls = []
            try:
                mapper = inspect(lead_orm)
                calls_attr = mapper.attrs.get("calls")
                if calls_attr and calls_attr.loaded_value is not None:
                    calls = list(calls_attr.loaded_value or [])
            except (AttributeError, KeyError, TypeError):
                pass
            _min_dt = datetime.min.replace(tzinfo=timezone.utc)
            sorted_calls = sorted(
                calls,
                key=lambda c: c.answered_at or c.created_at or _min_dt,
                reverse=True,
            )
            latest_analysis = None
            for call in sorted_calls:
                if hasattr(call, "analysis") and call.analysis:
                    latest_analysis = call.analysis
                    break
            intent = None
            primary_objection = None
            if latest_analysis:
                intent = getattr(latest_analysis, "appointment_intent", None) or getattr(
                    latest_analysis, "service_requested", None
                )
                if getattr(latest_analysis, "objections", None) and len(latest_analysis.objections) > 0:
                    primary_objection = str(latest_analysis.objections[0])
                elif getattr(latest_analysis, "objection_texts", None) and len(latest_analysis.objection_texts) > 0:
                    primary_objection = latest_analysis.objection_texts[0]
            last_touched = lead_orm.updated_at or lead_orm.created_at
            follow_up_count = pending_counts.get(lead_orm.id, 0)

            appt = lead_to_appointment.get(lead_orm.id)
            assigned_rep = rep_name
            scheduled_for = None
            recording_url = None
            transcript_id = None
            if appt:
                scheduled_for = appt.scheduled_start
                if appt.interaction_id:
                    call_for_appt = next(
                        (c for c in calls if c.id == appt.interaction_id),
                        None,
                    )
                    if call_for_appt:
                        recording_url = call_for_appt.audio_url
                        transcript_id = str(call_for_appt.id)
                if appt.assigned_rep_id and appt.assigned_rep_id != rep_id:
                    rep_result2 = await self.session.execute(
                        select(UserORM).where(UserORM.id == appt.assigned_rep_id)
                    )
                    appt_rep = rep_result2.scalar_one_or_none()
                    if appt_rep:
                        fn = appt_rep.first_name or ""
                        ln = appt_rep.last_name or ""
                        assigned_rep = f"{fn} {ln}".strip() or None

            tasks_list: List[str] = []
            summary_notes = None
            if latest_analysis:
                next_steps = getattr(latest_analysis, "next_steps", None) or []
                action_items = getattr(latest_analysis, "action_items", None) or []
                tasks_list = list(next_steps) if next_steps else list(action_items)
                summary_notes = getattr(latest_analysis, "summary", None)

            urgency_level = None
            if lead_orm.extra_metadata and isinstance(lead_orm.extra_metadata, dict):
                urgency_level = lead_orm.extra_metadata.get("urgency_level")
            if not urgency_level and latest_analysis and getattr(latest_analysis, "urgency_signals", None):
                signals = latest_analysis.urgency_signals
                if signals and any("high" in (s or "").lower() for s in signals):
                    urgency_level = "high"

            results.append(
                PendingLeadResultItem(
                    id=lead_orm.id,
                    urgency_level=urgency_level,
                    customer=PendingLeadCustomer(
                        full_name=full_name,
                        phone=phone,
                        address=address,
                    ),
                    sales_context=PendingLeadSalesContext(
                        intent=intent,
                        primary_objection=primary_objection,
                        last_touched=last_touched,
                        follow_up_count=follow_up_count,
                    ),
                    appointment=PendingLeadAppointment(
                        assigned_rep=assigned_rep,
                        scheduled_for=scheduled_for,
                        recording_url=recording_url,
                        transcript_id=transcript_id,
                    ),
                    workflow=PendingLeadWorkflow(
                        tasks=tasks_list,
                        summary_notes=summary_notes,
                    ),
                )
            )

        return PendingLeadsResponse(total_count=total, count=len(results), results=results)
    
    async def assign_to_rep(
        self,
        lead_id: UUID,
        sales_rep_id: UUID,
        assigned_by_user_id: UUID,
    ) -> Optional[Lead]:
        """
        Assign a lead to a sales rep.
        
        Validates that:
        - Lead exists
        - Sales rep exists and has sales_rep role
        - Both belong to the same company
        """
        from app.infrastructure.database.models.user import UserORM
        from app.infrastructure.database.models.lead import LeadORM
        from sqlalchemy import select
        
        # Get the lead to verify it exists and get company_id
        lead_result = await self.session.execute(
            select(LeadORM).where(LeadORM.id == lead_id)
        )
        lead_orm = lead_result.scalar_one_or_none()
        
        if not lead_orm:
            return None
        
        # Get the sales rep to verify they exist and have the correct role
        rep_result = await self.session.execute(
            select(UserORM).where(
                UserORM.id == sales_rep_id,
                UserORM.role == "sales_rep",
                UserORM.is_active == True,
            )
        )
        rep_orm = rep_result.scalar_one_or_none()
        
        if not rep_orm:
            raise ValueError(f"Sales rep with ID {sales_rep_id} not found or not active")
        
        # Verify both belong to the same company
        if lead_orm.company_id != rep_orm.company_id:
            raise ValueError("Lead and sales rep must belong to the same company")
        
        # Assign the lead
        return await self.lead_repo.assign_to_rep(
            lead_id=lead_id,
            sales_rep_id=sales_rep_id,
            assigned_by_user_id=assigned_by_user_id,
        )
    
    @staticmethod
    def _derive_pipeline_stage(lead_status: "LeadStatus") -> Optional[str]:
        """Derive pipeline_stage from a LeadStatus value."""
        from app.domain.enums import LeadStatus, PipelineStage
        mapping = {
            LeadStatus.QUALIFIED_UNBOOKED: PipelineStage.QUALIFIED,
            LeadStatus.QUALIFIED_BOOKED: PipelineStage.BOOKED,
            LeadStatus.QUALIFIED_SERVICE_NOT_OFFERED: PipelineStage.SERVICE_NOT_OFFERED,
            LeadStatus.ABANDONED: PipelineStage.UNQUALIFIED,
            LeadStatus.CLOSED_WON: PipelineStage.WON,
            LeadStatus.CLOSED_LOST: PipelineStage.LOST,
        }
        stage = mapping.get(lead_status)
        return stage.value if stage else None

    async def update_status(
        self,
        lead_id: UUID,
        status: str,
        changed_by_user_id: Optional[UUID] = None,
        reason: Optional[str] = None,
    ) -> Optional[Lead]:
        """
        Update lead status and optionally log to lead_status_changes audit table.
        Also auto-derives pipeline_stage from the new status.

        Args:
            lead_id: Lead ID
            status: New status value
            changed_by_user_id: User making the change (for audit; if provided, audit row is created)
            reason: Optional reason for the change

        Returns:
            Updated lead or None if not found
        """
        from app.domain.enums import LeadStatus

        try:
            lead_status_enum = LeadStatus(status)
        except ValueError:
            raise ValueError(f"Invalid lead status: {status}")

        # Derive pipeline_stage from the new status
        pipeline_stage = self._derive_pipeline_stage(lead_status_enum)

        return await self.lead_repo.update_status(
            lead_id=lead_id,
            status=status,
            changed_by_user_id=changed_by_user_id,
            reason=reason,
            pipeline_stage=pipeline_stage,
        )

