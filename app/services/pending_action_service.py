"""
Pending action service.

Provides business logic for managing pending actions:
- Fetching by urgency
- Marking as completed/converted
- Conversion metrics
- Task management (list with summary, detail, update, create manual)
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID

from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.pending_action import PendingAction
from app.domain.enums import PendingActionStatus
from app.domain.schemas.tasks import (
    TaskListItem,
    TaskListSummary,
    TaskListResponse,
    TaskDetailResponse,
    AssigneeInfo,
    SourceCallInfo,
)
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.call import CallORM

logger = get_logger(__name__)


def _owner_to_assignee(owner_orm) -> Optional[AssigneeInfo]:
    if not owner_orm:
        return None
    first = getattr(owner_orm, "first_name", None) or ""
    last = getattr(owner_orm, "last_name", None) or ""
    full = f"{first} {last}".strip() or None
    return AssigneeInfo(
        user_id=owner_orm.id,
        first_name=getattr(owner_orm, "first_name", None),
        last_name=getattr(owner_orm, "last_name", None),
        full_name=full,
        role=getattr(owner_orm, "role", None),
        email=getattr(owner_orm, "email", None),
    )


def _build_source_call(call_orm) -> Optional[SourceCallInfo]:
    if not call_orm:
        return None
    contact = getattr(call_orm, "contact_card", None)
    customer_name = None
    customer_phone = None
    if contact:
        first = getattr(contact, "first_name", None) or ""
        last = getattr(contact, "last_name", None) or ""
        customer_name = f"{first} {last}".strip() or None
        customer_phone = getattr(contact, "primary_phone", None)
    return SourceCallInfo(
        call_id=getattr(call_orm, "id", None),
        customer_name=customer_name,
        customer_phone=customer_phone,
        call_date=getattr(call_orm, "answered_at", None) or getattr(call_orm, "created_at", None),
        call_created_at=getattr(call_orm, "created_at", None),
    )


class PendingActionService:
    """Service for pending action operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.pending_action_repo = PendingActionRepository(session)
    
    async def fetch_by_urgency(
        self,
        company_id: UUID,
        limit: int = 100,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Fetch pending actions sorted by urgency (due_at + priority).
        
        Args:
            company_id: Company ID
            limit: Maximum number of actions to return
            status: Optional status filter (defaults to PENDING)
            
        Returns:
            List of pending actions sorted by urgency
        """
        try:
            return await self.pending_action_repo.get_by_urgency(
                company_id=company_id,
                limit=limit,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error fetching pending actions by urgency: {e}")
            raise e
    
    async def mark_completed(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as completed.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.COMPLETED,
            )
        except Exception as e:
            logger.error(f"Error marking action as completed: {e}", action_id=str(action_id))
            raise e
    
    async def reopen(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Reopen a pending action (set status back to pending).
        Use when a CSR or sales rep mistakenly marked an action as complete.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.PENDING,
            )
        except Exception as e:
            logger.error(f"Error reopening pending action: {e}", action_id=str(action_id))
            raise e
    
    async def mark_converted(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as converted.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.CONVERTED,
            )
        except Exception as e:
            logger.error(f"Error marking action as converted: {e}", action_id=str(action_id))
            raise e
    
    async def get_conversion_metrics(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get conversion metrics (pending → converted).
        
        Args:
            company_id: Company ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dict with conversion metrics
        """
        try:
            # Convert dates to datetimes if provided
            start_dt = None
            end_dt = None
            if start_date:
                start_dt = datetime.combine(start_date, datetime.min.time())
            if end_date:
                end_dt = datetime.combine(end_date, datetime.max.time())
            
            return await self.pending_action_repo.get_conversion_metrics(
                company_id=company_id,
                start_date=start_dt,
                end_date=end_dt,
            )
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            raise e
    
    async def get_by_company(
        self,
        company_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a company.
        
        Args:
            company_id: Company ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_company(
                company_id=company_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by company: {e}")
            raise e
    
    async def get_by_lead(
        self,
        lead_id: UUID,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a lead.
        
        Args:
            lead_id: Lead ID
            status: Optional status filter
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_lead(
                lead_id=lead_id,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by lead: {e}")
            raise e
    
    async def get_by_owner(
        self,
        owner_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for an owner/user.
        
        Args:
            owner_id: Owner/user ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_owner(
                owner_id=owner_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by owner: {e}")
            raise e

    async def create_from_call(
        self,
        call_id: UUID,
        company_id: UUID,
        lead_id: Optional[UUID],
        owner_id: UUID,
        assigned_by_id: UUID,
        action_type: str,
        raw_text: Optional[str] = None,
        due_at: Optional[datetime] = None,
        priority: Optional[int] = None,
    ) -> PendingAction:
        """
        Create a pending action linked to a call, assigned to a user (e.g. executive assigning to CSR).
        
        Args:
            call_id: Call this action is tied to
            company_id: Company ID
            lead_id: Lead ID from the call (optional)
            owner_id: User to assign the action to (CSR)
            assigned_by_id: User creating/assigning the action (e.g. executive)
            action_type: Type of action
            raw_text: Optional description
            due_at: Optional due date
            priority: Optional priority
        Returns:
            Created PendingAction
        """
        pending = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            call_id=call_id,
            appointment_id=None,
            action_type=action_type,
            raw_text=raw_text,
            status=PendingActionStatus.PENDING,
            due_at=due_at,
            priority=priority,
            owner_id=owner_id,
            assigned_by_id=assigned_by_id,
            source="manual",
            extra_metadata=None,
        )
        return await self.pending_action_repo.create(pending)

    async def list_tasks_with_summary(
        self,
        company_id: UUID,
        *,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[UUID] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        due_date_from: Optional[datetime] = None,
        due_date_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """List tasks with filters and summary counts for Task Management page (CSR 'My Tasks' uses assignee_id=current user)."""
        # Query pending_actions for task management summaries
        counts_query = (
            select(PendingActionORM.status, func.count(PendingActionORM.id).label("count"))
            .where(PendingActionORM.company_id == company_id)
            .group_by(PendingActionORM.status)
        )
        res = await self.session.execute(counts_query)
        counts_rows = res.fetchall()
        counts = {row[0]: row[1] for row in counts_rows}
        # Build summary from pending_actions counts
        summary = TaskListSummary(
            total_tasks=sum(counts.values()),
            pending=counts.get(PendingActionStatus.PENDING.value, 0),
            in_progress=counts.get(PendingActionStatus.IN_PROGRESS.value, 0),
            completed=counts.get(PendingActionStatus.COMPLETED.value, 0),
            cancelled=counts.get(PendingActionStatus.CANCELLED.value, 0),
        )
        # Build base filter conditions
        filters = [PendingActionORM.company_id == company_id]

        if status:
            filters.append(PendingActionORM.status == status)
        if priority is not None:
            filters.append(PendingActionORM.priority == priority)
        if assignee_id:
            filters.append(PendingActionORM.owner_id == assignee_id)
        if start_date:
            filters.append(PendingActionORM.created_at >= start_date)
        if end_date:
            filters.append(PendingActionORM.created_at <= end_date)
        if due_date_from:
            filters.append(PendingActionORM.due_at >= due_date_from)
        if due_date_to:
            filters.append(PendingActionORM.due_at <= due_date_to)
        if search:
            search_term = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(PendingActionORM.raw_text).like(search_term),
                    func.lower(PendingActionORM.action_type).like(search_term),
                )
            )

        query = (
            select(PendingActionORM)
            .options(
                selectinload(PendingActionORM.call).selectinload(CallORM.contact_card),
                selectinload(PendingActionORM.owner),
                selectinload(PendingActionORM.assigned_by),
            )
            .where(*filters)
            .order_by(PendingActionORM.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        orm_list = result.scalars().all()
        # total count (with same filters applied)
        total_res = await self.session.execute(select(func.count(PendingActionORM.id)).where(*filters))
        total = total_res.scalar() or 0
        tasks = []
        for row in orm_list:
            owner = getattr(row, "owner", None)
            assigned_by = getattr(row, "assigned_by", None)
            call = getattr(row, "call", None)
            tasks.append(TaskListItem(
                id=row.id,
                company_id=row.company_id,
                action_type=row.action_type,
                raw_text=row.raw_text,
                status=row.status,
                priority=row.priority,
                due_at=row.due_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
                owner_id=row.owner_id,
                assigned_to=_owner_to_assignee(owner),
                assigned_by=_owner_to_assignee(assigned_by),
                source_call=_build_source_call(call),
                call_id=row.call_id,
                lead_id=row.lead_id,
                assigned_by_id=row.assigned_by_id,
            ))
        return {
            "summary": summary,
            "tasks": tasks,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def get_task_detail(self, task_id: UUID) -> Optional[Dict[str, Any]]:
        """Get single task with full details (owner, assigned_by, source call)."""
        query = (
            select(PendingActionORM)
            .where(PendingActionORM.id == task_id)
            .options(
                selectinload(PendingActionORM.owner),
                selectinload(PendingActionORM.assigned_by),
                selectinload(PendingActionORM.call).selectinload(CallORM.contact_card),
            )
        )
        result = await self.session.execute(query)
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "company_id": row.company_id,
            "lead_id": row.lead_id,
            "call_id": row.call_id,
            "appointment_id": row.appointment_id,
            "action_type": row.action_type,
            "raw_text": row.raw_text,
            "status": row.status,
            "priority": row.priority,
            "due_at": row.due_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "owner_id": row.owner_id,
            "assigned_to": _owner_to_assignee(getattr(row, "owner", None)),
            "assigned_by_id": row.assigned_by_id,
            "assigned_by": _owner_to_assignee(getattr(row, "assigned_by", None)),
            "source_call": _build_source_call(getattr(row, "call", None)),
            "source": row.source,
        }

    async def update_task(
        self,
        task_id: UUID,
        *,
        owner_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        raw_text: Optional[str] = None,
        assigned_by_id: Optional[UUID] = None,
    ) -> Optional[PendingAction]:
        """Update task (reassign, status, priority, due_at, raw_text)."""
        # Update the pending_action fields directly
        orm_obj = await self.session.get(PendingActionORM, task_id)
        if not orm_obj:
            return None
        if owner_id is not None:
            orm_obj.owner_id = owner_id
        if status is not None:
            orm_obj.status = status
        if priority is not None:
            orm_obj.priority = priority
        if due_at is not None:
            orm_obj.due_at = due_at
        if raw_text is not None:
            orm_obj.raw_text = raw_text
        if assigned_by_id is not None:
            orm_obj.assigned_by_id = assigned_by_id
        await self.session.flush()
        await self.session.refresh(orm_obj)

        updated = PendingAction(
            id=orm_obj.id,
            company_id=orm_obj.company_id,
            lead_id=orm_obj.lead_id,
            call_id=orm_obj.call_id,
            appointment_id=orm_obj.appointment_id,
            action_type=orm_obj.action_type,
            raw_text=orm_obj.raw_text,
            status=orm_obj.status,
            priority=orm_obj.priority,
            due_at=orm_obj.due_at,
            owner_id=orm_obj.owner_id,
            assigned_by_id=orm_obj.assigned_by_id,
            source=orm_obj.source,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

        # If an owner (sales rep) was provided and the action item is linked to a lead,
        # ensure the lead is assigned to that rep and create an appointment record if the lead
        # is already booked (or deal_status indicates 'booked').
        try:
            if owner_id is not None:
                lead_id = orm_obj.lead_id
                company_id = orm_obj.company_id
                if lead_id and company_id:
                    from app.infrastructure.repositories.lead import LeadRepository
                    from app.infrastructure.repositories.appointment import AppointmentRepository
                    from app.domain.models.appointment import Appointment as AppointmentDomain
                    from datetime import datetime as dt_cls, timezone

                    lead_repo = LeadRepository(self.session)
                    appointment_repo = AppointmentRepository(self.session)

                    # Assign the lead to the sales rep
                    await lead_repo.assign_to_rep(lead_id=lead_id, sales_rep_id=owner_id, assigned_by_user_id=assigned_by_id)

                    # Reload lead to check status and contact_card
                    lead = await lead_repo.get_by_id(lead_id)
                    lead_deal_status = getattr(lead, "deal_status", None)
                    lead_status = getattr(lead, "status", None)
                    contact_card_id = getattr(lead, "contact_card_id", None)

                    is_booked = False
                    if lead_status and str(lead_status).lower() == "qualified_booked":
                        is_booked = True
                    if lead_deal_status and str(lead_deal_status).lower() == "booked":
                        is_booked = True

                    if is_booked and contact_card_id:
                        existing_appt = await appointment_repo.get_by_lead_id(lead_id)
                        if not existing_appt:
                            appt = AppointmentDomain(
                                company_id=company_id,
                                lead_id=lead_id,
                                contact_card_id=contact_card_id,
                                scheduled_start=dt_cls.now(timezone.utc),
                                scheduled_end=None,
                                location_address=None,
                                latitude=None,
                                longitude=None,
                                outcome=None,
                                assigned_rep_id=owner_id,
                                interaction_id=None,
                                audio_url=None,
                                extra_metadata={"created_from": "csr_assignment", "assigned_via": "task_update"},
                            )
                            await appointment_repo.create(appt)
        except Exception as e:
            logger.warning(f"Could not create appointment on assignment: {e}")

        return updated

    async def create_task_manual(
        self,
        company_id: UUID,
        assigned_by_id: UUID,
        action_type: str,
        *,
        raw_text: Optional[str] = None,
        status: Optional[str] = "pending",
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        owner_id: Optional[UUID] = None,
        lead_id: Optional[UUID] = None,
        call_id: Optional[UUID] = None,
        appointment_id: Optional[UUID] = None,
    ) -> PendingAction:
        """Create a task manually (not from a call)."""
        status_enum = PendingActionStatus.PENDING
        if status:
            try:
                status_enum = PendingActionStatus(status)
            except ValueError:
                pass
        pending = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            call_id=call_id,
            appointment_id=appointment_id,
            action_type=action_type,
            raw_text=raw_text,
            status=status_enum,
            due_at=due_at,
            priority=priority,
            owner_id=owner_id,
            assigned_by_id=assigned_by_id,
            source="manual",
            extra_metadata=None,
        )
        return await self.pending_action_repo.create(pending)
