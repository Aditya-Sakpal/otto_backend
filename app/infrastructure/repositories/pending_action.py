"""
Pending action repository.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_, or_, func as sql_func, desc, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.pending_action import PendingAction
from app.domain.enums import PendingActionStatus
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class PendingActionRepository(BaseRepository[PendingActionORM, PendingAction]):
    """Repository for PendingAction entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, PendingActionORM, PendingAction)

    async def create(self, domain_obj: PendingAction) -> PendingAction:
        """Create pending action and mirror to action_items table for visibility."""
        try:
            created = await super().create(domain_obj)
            # Mirror into action_items (non-fatal)
            try:
                import json

                insert_sql = text("INSERT INTO action_items (id, company_id, lead_id, call_id, appointment_id, action_type, raw_text, status, due_at, priority, owner_id, source, extra_metadata, created_at, assigned_by_id) VALUES (uuid_generate_v4(), :company_id, :lead_id, :call_id, :appointment_id, :action_type, :raw_text, :status, :due_at, :priority, :owner_id, :source, :extra_metadata, CURRENT_TIMESTAMP, :assigned_by_id)")

                await self.session.execute(
                    insert_sql,
                    {
                        "company_id": str(created.company_id) if getattr(created, "company_id", None) else None,
                        "lead_id": str(created.lead_id) if getattr(created, "lead_id", None) else None,
                        "call_id": str(created.call_id) if getattr(created, "call_id", None) else None,
                        "appointment_id": str(created.appointment_id) if getattr(created, "appointment_id", None) else None,
                        "action_type": created.action_type,
                        "raw_text": created.raw_text,
                        "status": created.status.value if hasattr(created.status, "value") else str(created.status),
                        "due_at": created.due_at,
                        "priority": created.priority,
                        "owner_id": str(created.owner_id) if getattr(created, "owner_id", None) else None,
                        "source": created.source if getattr(created, "source", None) else "shunya",
                        "extra_metadata": json.dumps(created.extra_metadata) if getattr(created, "extra_metadata", None) else None,
                        "assigned_by_id": str(created.assigned_by_id) if getattr(created, "assigned_by_id", None) else None,
                    },
                )
            except Exception:
                logger.exception("Failed to mirror pending action into action_items; continuing")

            return created
        except Exception as e:
            logger.error(f"Error creating pending action: {e}")
            raise

    async def bulk_create(self, domain_objs: list[PendingAction]) -> int:
        """Create many pending actions in one flush + one action_items insert batch.

        Per-row create() does add+flush+refresh plus a mirror INSERT — ~4 round
        trips each, which is prohibitively slow for large batches (e.g. a full
        rehash scan creating ~1k rows against a remote DB). This adds all ORM rows,
        flushes once, then mirrors them into action_items with a single
        executemany. The action_items mirror is best-effort (non-fatal), matching
        create(). Returns the number created.
        """
        if not domain_objs:
            return 0
        try:
            import json

            orm_objs = [self._to_orm(obj) for obj in domain_objs]
            self.session.add_all(orm_objs)
            await self.session.flush()  # single flush for the whole batch

            # Mirror into action_items in one executemany (non-fatal).
            try:
                insert_sql = text(
                    "INSERT INTO action_items (id, company_id, lead_id, call_id, "
                    "appointment_id, action_type, raw_text, status, due_at, priority, "
                    "owner_id, source, extra_metadata, created_at, assigned_by_id) "
                    "VALUES (uuid_generate_v4(), :company_id, :lead_id, :call_id, "
                    ":appointment_id, :action_type, :raw_text, :status, :due_at, "
                    ":priority, :owner_id, :source, :extra_metadata, CURRENT_TIMESTAMP, "
                    ":assigned_by_id)"
                )
                params = []
                for o in orm_objs:
                    status_val = o.status.value if hasattr(o.status, "value") else str(o.status)
                    params.append({
                        "company_id": str(o.company_id) if getattr(o, "company_id", None) else None,
                        "lead_id": str(o.lead_id) if getattr(o, "lead_id", None) else None,
                        "call_id": str(o.call_id) if getattr(o, "call_id", None) else None,
                        "appointment_id": str(o.appointment_id) if getattr(o, "appointment_id", None) else None,
                        "action_type": o.action_type,
                        "raw_text": o.raw_text,
                        "status": status_val,
                        "due_at": o.due_at,
                        "priority": o.priority,
                        "owner_id": str(o.owner_id) if getattr(o, "owner_id", None) else None,
                        "source": o.source if getattr(o, "source", None) else "shunya",
                        "extra_metadata": json.dumps(o.extra_metadata) if getattr(o, "extra_metadata", None) else None,
                        "assigned_by_id": str(o.assigned_by_id) if getattr(o, "assigned_by_id", None) else None,
                    })
                if params:
                    await self.session.execute(insert_sql, params)
            except Exception:
                logger.exception("Failed to mirror bulk pending actions into action_items; continuing")

            return len(orm_objs)
        except Exception as e:
            logger.error(f"Error bulk-creating pending actions: {e}")
            raise

    async def exists_pending_call_back(
        self,
        company_id: UUID,
        call_id: UUID,
    ) -> bool:
        """Return True if a pending call_back already exists for this call."""
        try:
            query = select(self.orm_model.id).where(
                and_(
                    self.orm_model.company_id == company_id,
                    self.orm_model.call_id == call_id,
                    self.orm_model.action_type == "call_back",
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            ).limit(1)
            result = await self.session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking pending call_back existence: {e}")
            raise

    async def get_pending_call_back(
        self,
        company_id: UUID,
        call_id: UUID,
    ) -> Optional[PendingAction]:
        """Return existing pending call_back for a call, if any."""
        try:
            query = select(self.orm_model).where(
                and_(
                    self.orm_model.company_id == company_id,
                    self.orm_model.call_id == call_id,
                    self.orm_model.action_type == "call_back",
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            ).limit(1)
            result = await self.session.execute(query)
            orm_obj = result.scalar_one_or_none()
            return self._to_domain(orm_obj) if orm_obj else None
        except Exception as e:
            logger.error(f"Error fetching pending call_back: {e}")
            raise

    async def exists_pending_appointment_follow_up(
        self,
        appointment_id: UUID,
        source: str | None = None,
    ) -> bool:
        """Return True if a pending appointment follow-up task already exists."""
        try:
            filters = [
                self.orm_model.appointment_id == appointment_id,
                self.orm_model.action_type == "follow_up",
                self.orm_model.status == PendingActionStatus.PENDING.value,
            ]
            if source is not None:
                filters.append(self.orm_model.source == source)
            query = select(self.orm_model.id).where(and_(*filters)).limit(1)
            result = await self.session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking appointment follow-up existence: {e}")
            raise

    async def exists_appointment_ai_action(
        self,
        appointment_id: UUID,
        dedup_key: str,
    ) -> bool:
        """Return True if a materialized post-meeting AI action already exists.

        Idempotency for tasks materialized from Shunya's pending_actions list:
        one task per (appointment, normalized action text), keyed by an
        ai_dedup_key stored in extra_metadata. Filters dedup_key in Python to
        stay dialect-agnostic for the generic JSON column.
        """
        try:
            query = select(self.orm_model).where(
                and_(
                    self.orm_model.appointment_id == appointment_id,
                    self.orm_model.source == "ai_analysis",
                    self.orm_model.status.in_(
                        (
                            PendingActionStatus.PENDING.value,
                            PendingActionStatus.IN_PROGRESS.value,
                            PendingActionStatus.COMPLETED.value,
                        )
                    ),
                )
            )
            result = await self.session.execute(query)
            for row in result.scalars().all():
                if (row.extra_metadata or {}).get("ai_dedup_key") == dedup_key:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking appointment AI action existence: {e}")
            raise

    # ── Appointment reminders ────────────────────────────────────────────
    APPOINTMENT_REMINDER_ACTION_TYPE = "appointment_reminder"
    APPOINTMENT_REMINDER_SOURCE = "appointment_reminder"

    async def list_pending_appointment_reminders(
        self,
        appointment_id: UUID,
    ) -> List[PendingActionORM]:
        """Return pending appointment_reminder ORM rows for an appointment."""
        try:
            query = select(self.orm_model).where(
                and_(
                    self.orm_model.appointment_id == appointment_id,
                    self.orm_model.action_type == self.APPOINTMENT_REMINDER_ACTION_TYPE,
                    self.orm_model.source == self.APPOINTMENT_REMINDER_SOURCE,
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error listing pending appointment reminders: {e}")
            raise

    async def exists_appointment_reminder(
        self,
        appointment_id: UUID,
        reminder_kind: str,
    ) -> bool:
        """Return True if a pending reminder of this kind already exists.

        Filters reminder_kind in Python to stay dialect-agnostic for the
        generic JSON extra_metadata column.
        """
        try:
            rows = await self.list_pending_appointment_reminders(appointment_id)
            return any(
                (row.extra_metadata or {}).get("reminder_kind") == reminder_kind
                for row in rows
            )
        except Exception as e:
            logger.error(f"Error checking appointment reminder existence: {e}")
            raise

    async def cancel_pending_appointment_reminders(
        self,
        appointment_id: UUID,
    ) -> int:
        """Set status=cancelled on all pending reminders for an appointment.

        Returns the number of rows updated.
        """
        try:
            rows = await self.list_pending_appointment_reminders(appointment_id)
            count = 0
            for row in rows:
                row.status = PendingActionStatus.CANCELLED.value
                count += 1
            if count:
                await self.session.flush()
            return count
        except Exception as e:
            logger.error(f"Error cancelling appointment reminders: {e}")
            raise

    async def mark_appointment_reminder_notified(
        self,
        pending_action_id: UUID,
        notified_at: datetime,
    ) -> None:
        """Persist notified_at in extra_metadata and mark the row completed."""
        try:
            query = select(self.orm_model).where(self.orm_model.id == pending_action_id).limit(1)
            result = await self.session.execute(query)
            row = result.scalar_one_or_none()
            if row is None:
                return
            meta = dict(row.extra_metadata or {})
            meta["notified_at"] = notified_at.isoformat()
            row.extra_metadata = meta
            row.status = PendingActionStatus.COMPLETED.value
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error marking appointment reminder notified: {e}")
            raise

    async def mark_task_notified(
        self,
        pending_action_id: UUID,
        notified_at: datetime,
    ) -> None:
        """Stamp notified_at on a generic task WITHOUT changing its status.

        Used for call_back / follow_up / post-meeting reminders: these are real
        rep tasks the rep completes manually, so the reminder must be DB-idempotent
        (restart/multi-replica safe) but must NOT auto-complete the task.
        """
        try:
            query = select(self.orm_model).where(self.orm_model.id == pending_action_id).limit(1)
            result = await self.session.execute(query)
            row = result.scalar_one_or_none()
            if row is None:
                return
            meta = dict(row.extra_metadata or {})
            meta["notified_at"] = notified_at.isoformat()
            row.extra_metadata = meta  # status intentionally unchanged
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error marking task notified: {e}")
            raise

    # ── Rehash (missed-revenue opportunities) ────────────────────────────
    REHASH_ACTION_TYPE = "rehash"
    REHASH_SOURCE = "rehash"

    async def list_pending_rehash(
        self,
        lead_id: UUID,
    ) -> List[PendingActionORM]:
        """Return pending rehash ORM rows for a lead."""
        try:
            query = select(self.orm_model).where(
                and_(
                    self.orm_model.lead_id == lead_id,
                    self.orm_model.action_type == self.REHASH_ACTION_TYPE,
                    self.orm_model.source == self.REHASH_SOURCE,
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error listing pending rehash actions: {e}")
            raise

    async def list_active_rehash(
        self,
        lead_id: UUID,
    ) -> List[PendingActionORM]:
        """Return pending OR completed rehash rows for a lead.

        Completed = already notified this eligibility episode. Both states
        suppress re-creation so a fired rehash is not re-surfaced daily.
        """
        try:
            query = select(self.orm_model).where(
                and_(
                    self.orm_model.lead_id == lead_id,
                    self.orm_model.action_type == self.REHASH_ACTION_TYPE,
                    self.orm_model.source == self.REHASH_SOURCE,
                    self.orm_model.status.in_(
                        (
                            PendingActionStatus.PENDING.value,
                            PendingActionStatus.COMPLETED.value,
                        )
                    ),
                )
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error listing active rehash actions: {e}")
            raise

    async def exists_active_rehash(
        self,
        lead_id: UUID,
        category: str,
    ) -> bool:
        """Return True if a pending OR completed rehash of this category exists.

        Filters rehash_category in Python to stay dialect-agnostic for the
        generic JSON extra_metadata column.
        """
        try:
            rows = await self.list_active_rehash(lead_id)
            return any(
                (row.extra_metadata or {}).get("rehash_category") == category
                for row in rows
            )
        except Exception as e:
            logger.error(f"Error checking active rehash existence: {e}")
            raise

    async def cancel_pending_rehash(
        self,
        lead_id: UUID,
        category: str | None = None,
    ) -> int:
        """Cancel pending rehash rows for a lead.

        If category is provided, only that category is cancelled; otherwise all
        pending rehash rows for the lead. Returns the number of rows updated.
        """
        try:
            rows = await self.list_pending_rehash(lead_id)
            count = 0
            for row in rows:
                if category is not None and (row.extra_metadata or {}).get("rehash_category") != category:
                    continue
                row.status = PendingActionStatus.CANCELLED.value
                count += 1
            if count:
                await self.session.flush()
            return count
        except Exception as e:
            logger.error(f"Error cancelling rehash actions: {e}")
            raise

    async def mark_rehash_notified(
        self,
        pending_action_id: UUID,
        notified_at: datetime,
    ) -> None:
        """Persist notified_at in extra_metadata and mark the rehash completed."""
        try:
            query = select(self.orm_model).where(self.orm_model.id == pending_action_id).limit(1)
            result = await self.session.execute(query)
            row = result.scalar_one_or_none()
            if row is None:
                return
            meta = dict(row.extra_metadata or {})
            meta["notified_at"] = notified_at.isoformat()
            row.extra_metadata = meta
            row.status = PendingActionStatus.COMPLETED.value
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error marking rehash notified: {e}")
            raise

    async def active_rehash_categories_for_leads(
        self,
        lead_ids: list[UUID],
    ) -> dict[UUID, set[str]]:
        """Batch: map each lead_id → set of categories with an active rehash.

        Active = pending OR completed (already notified) rehash. One query for the
        whole candidate set, replacing the per-lead `exists_active_rehash` N+1 in
        the rehash scan. rehash_category is read from extra_metadata in Python to
        stay dialect-agnostic for the generic JSON column.
        """
        out: dict[UUID, set[str]] = {}
        if not lead_ids:
            return out
        try:
            query = select(
                self.orm_model.lead_id, self.orm_model.extra_metadata
            ).where(
                and_(
                    self.orm_model.lead_id.in_(lead_ids),
                    self.orm_model.action_type == self.REHASH_ACTION_TYPE,
                    self.orm_model.source == self.REHASH_SOURCE,
                    self.orm_model.status.in_(
                        (
                            PendingActionStatus.PENDING.value,
                            PendingActionStatus.COMPLETED.value,
                        )
                    ),
                )
            )
            result = await self.session.execute(query)
            for lead_id, meta in result.all():
                category = (meta or {}).get("rehash_category")
                if category:
                    out.setdefault(lead_id, set()).add(category)
            return out
        except Exception as e:
            logger.error(f"Error batching active rehash categories: {e}")
            raise

    async def leads_with_pending_action_of_types(
        self,
        lead_ids: list[UUID],
        action_types: tuple[str, ...],
    ) -> set[UUID]:
        """Batch: subset of lead_ids that have a pending action of the given types.

        One query for the whole candidate set, replacing the per-lead
        `exists_pending_action_of_types` N+1 in the rehash noise-suppression step.
        """
        if not lead_ids:
            return set()
        try:
            query = select(self.orm_model.lead_id).where(
                and_(
                    self.orm_model.lead_id.in_(lead_ids),
                    self.orm_model.action_type.in_(action_types),
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            ).distinct()
            result = await self.session.execute(query)
            return {row[0] for row in result.all()}
        except Exception as e:
            logger.error(f"Error batching pending actions of types: {e}")
            raise

    async def exists_pending_action_of_types(
        self,
        lead_id: UUID,
        action_types: tuple[str, ...],
    ) -> bool:
        """Return True if the lead has any pending action of the given types.

        Used for rehash noise-reduction: skip creating a rehash when a pending
        call_back / follow_up already covers the same revenue intent.
        """
        try:
            query = select(self.orm_model.id).where(
                and_(
                    self.orm_model.lead_id == lead_id,
                    self.orm_model.action_type.in_(action_types),
                    self.orm_model.status == PendingActionStatus.PENDING.value,
                )
            ).limit(1)
            result = await self.session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking pending action of types: {e}")
            raise

    async def list_for_action_center(
        self,
        *,
        company_id: UUID,
        owner_id: UUID,
        statuses: List[str],
        limit: Optional[int] = None,
    ) -> List[PendingActionORM]:
        """Fetch owner-scoped pending actions for the Action Center.

        Filters to the four automated revenue families (call_back, follow_up*,
        appointment_reminder, rehash). Final ranking/grouping is done in Python;
        SQL only pre-orders by due_at and caps row count. Eagerly loads call →
        contact_card and owner for item enrichment (same as the task list).
        """
        try:
            lower_type = sql_func.lower(self.orm_model.action_type)
            whitelist = or_(
                lower_type.in_(("call_back", "callback", "appointment_reminder", "rehash")),
                lower_type.like("follow_up%"),
            )
            query = (
                select(self.orm_model)
                .options(
                    selectinload(self.orm_model.call).selectinload(CallORM.contact_card),
                    selectinload(self.orm_model.owner),
                )
                .where(
                    and_(
                        self.orm_model.company_id == company_id,
                        self.orm_model.owner_id == owner_id,
                        self.orm_model.status.in_(statuses),
                        whitelist,
                    )
                )
                .order_by(self.orm_model.due_at.asc().nulls_last())
            )
            if limit is not None:
                query = query.limit(limit)
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error listing action center rows: {e}")
            raise

    async def get_by_company(
        self,
        company_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """Get all pending actions for a company."""
        try:
            query = select(self.orm_model).where(self.orm_model.company_id == company_id)
            if status:
                query = query.where(self.orm_model.status == status.value)
            # Order by most recently created first for task management views.
            query = query.offset(skip).limit(limit).order_by(desc(self.orm_model.created_at))
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting pending actions by company: {e}")
            raise e
    
    async def get_by_lead(
        self,
        lead_id: UUID,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """Get all pending actions for a lead."""
        try:
            query = select(self.orm_model).where(self.orm_model.lead_id == lead_id)
            if status:
                query = query.where(self.orm_model.status == status.value)
            # Order by most recently created first for task management views.
            query = query.order_by(desc(self.orm_model.created_at))
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
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
        """Get all pending actions for an owner/user."""
        try:
            query = select(self.orm_model).where(self.orm_model.owner_id == owner_id)
            if status:
                query = query.where(self.orm_model.status == status.value)
            # Order by most recently created first for task management views.
            query = query.offset(skip).limit(limit).order_by(desc(self.orm_model.created_at))
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting pending actions by owner: {e}")
            raise e
    
    async def get_by_urgency(
        self,
        company_id: UUID,
        limit: int = 100,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Get pending actions sorted by urgency (due_at + priority).
        
        Urgency is calculated as: actions with due_at closest to now, 
        with higher priority breaking ties.
        """
        try:
            query = select(self.orm_model).where(self.orm_model.company_id == company_id)
            if status:
                query = query.where(self.orm_model.status == status.value)
            else:
                # Default to pending status if not specified
                query = query.where(self.orm_model.status == PendingActionStatus.PENDING.value)
            
            # Order by due_at (NULLS LAST), then by priority (DESC), then by created_at
            query = query.order_by(
                self.orm_model.due_at.asc().nulls_last(),
                desc(self.orm_model.priority),
                self.orm_model.created_at.asc()
            ).limit(limit)
            
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting pending actions by urgency: {e}")
            raise e
    
    async def update_status(
        self,
        action_id: UUID,
        status: PendingActionStatus,
    ) -> Optional[PendingAction]:
        """Update the status of a pending action."""
        try:
            orm_obj = await self.session.get(self.orm_model, action_id)
            if not orm_obj:
                return None
            
            orm_obj.status = status.value
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error updating pending action status: {e}")
            raise e

    async def update_fields(
        self,
        action_id: UUID,
        *,
        owner_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        raw_text: Optional[str] = None,
        assigned_by_id: Optional[UUID] = None,
    ) -> Optional[PendingAction]:
        """Partially update a pending action (for reassign, status, priority, due_at, raw_text)."""
        try:
            orm_obj = await self.session.get(self.orm_model, action_id)
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
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error updating pending action fields: {e}")
            raise e

    async def list_with_filters(
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
    ) -> List[PendingActionORM]:
        """
        List pending actions with filters and relationships loaded (owner, call, contact).
        Returns ORM list for service to build response (owner name, source call info).
        """
        try:
            query = (
                select(PendingActionORM)
                .options(
                    selectinload(PendingActionORM.owner),
                    selectinload(PendingActionORM.assigned_by),
                    selectinload(PendingActionORM.call).selectinload(CallORM.contact_card),
                )
                .where(PendingActionORM.company_id == company_id)
            )
            if status:
                query = query.where(PendingActionORM.status == status)
            if priority is not None:
                query = query.where(PendingActionORM.priority == priority)
            if assignee_id is not None:
                query = query.where(PendingActionORM.owner_id == assignee_id)
            if search and search.strip():
                term = f"%{search.strip()}%"
                query = query.outerjoin(PendingActionORM.call).outerjoin(CallORM.contact_card)
                query = query.where(
                    or_(
                        PendingActionORM.raw_text.ilike(term),
                        ContactCardORM.first_name.ilike(term),
                        ContactCardORM.last_name.ilike(term),
                        ContactCardORM.primary_phone.ilike(term),
                        ContactCardORM.email.ilike(term),
                    )
                )
            if start_date is not None:
                query = query.where(PendingActionORM.created_at >= start_date)
            if end_date is not None:
                query = query.where(PendingActionORM.created_at <= end_date)
            if due_date_from is not None:
                query = query.where(PendingActionORM.due_at >= due_date_from)
            if due_date_to is not None:
                query = query.where(PendingActionORM.due_at <= due_date_to)
            # Default task listing: recent first, then by due date (soonest)
            query = query.order_by(
                desc(PendingActionORM.created_at),
                PendingActionORM.due_at.asc().nulls_last(),
            ).offset(skip).limit(limit)
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error listing pending actions with filters: {e}")
            raise e

    async def count_with_filters(
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
    ) -> int:
        """Count pending actions matching the same filters as list_with_filters (for pagination total)."""
        try:
            query = select(sql_func.count(PendingActionORM.id)).where(
                PendingActionORM.company_id == company_id
            )
            if status:
                query = query.where(PendingActionORM.status == status)
            if priority is not None:
                query = query.where(PendingActionORM.priority == priority)
            if assignee_id is not None:
                query = query.where(PendingActionORM.owner_id == assignee_id)
            if search and search.strip():
                term = f"%{search.strip()}%"
                query = (
                    query.outerjoin(PendingActionORM.call)
                    .outerjoin(CallORM.contact_card)
                    .where(
                        or_(
                            PendingActionORM.raw_text.ilike(term),
                            ContactCardORM.first_name.ilike(term),
                            ContactCardORM.last_name.ilike(term),
                            ContactCardORM.primary_phone.ilike(term),
                            ContactCardORM.email.ilike(term),
                        )
                    )
                )
            if start_date is not None:
                query = query.where(PendingActionORM.created_at >= start_date)
            if end_date is not None:
                query = query.where(PendingActionORM.created_at <= end_date)
            if due_date_from is not None:
                query = query.where(PendingActionORM.due_at >= due_date_from)
            if due_date_to is not None:
                query = query.where(PendingActionORM.due_at <= due_date_to)
            result = await self.session.execute(query)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting pending actions: {e}")
            raise e

    async def get_counts_by_status(
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
    ) -> Dict[str, int]:
        """Get task counts by status for summary cards (same filters as list for CSR 'My Tasks')."""
        try:
            query = select(
                PendingActionORM.status,
                sql_func.count(PendingActionORM.id).label("count"),
            ).where(PendingActionORM.company_id == company_id)
            if status:
                query = query.where(PendingActionORM.status == status)
            if priority is not None:
                query = query.where(PendingActionORM.priority == priority)
            if assignee_id is not None:
                query = query.where(PendingActionORM.owner_id == assignee_id)
            if search and search.strip():
                term = f"%{search.strip()}%"
                query = (
                    query.outerjoin(PendingActionORM.call)
                    .outerjoin(CallORM.contact_card)
                    .where(
                        or_(
                            PendingActionORM.raw_text.ilike(term),
                            ContactCardORM.first_name.ilike(term),
                            ContactCardORM.last_name.ilike(term),
                            ContactCardORM.primary_phone.ilike(term),
                            ContactCardORM.email.ilike(term),
                        )
                    )
                )
            if start_date is not None:
                query = query.where(PendingActionORM.created_at >= start_date)
            if end_date is not None:
                query = query.where(PendingActionORM.created_at <= end_date)
            if due_date_from is not None:
                query = query.where(PendingActionORM.due_at >= due_date_from)
            if due_date_to is not None:
                query = query.where(PendingActionORM.due_at <= due_date_to)
            query = query.group_by(PendingActionORM.status)
            result = await self.session.execute(query)
            rows = result.fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting counts by status: {e}")
            raise e
    
    async def get_conversion_metrics(
        self,
        company_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get conversion metrics (pending → converted).
        
        Returns counts of actions by status and conversion rate.
        """
        try:
            query = select(
                self.orm_model.status,
                sql_func.count(self.orm_model.id).label("count")
            ).where(self.orm_model.company_id == company_id)
            
            if start_date:
                query = query.where(self.orm_model.created_at >= start_date)
            if end_date:
                query = query.where(self.orm_model.created_at <= end_date)
            
            query = query.group_by(self.orm_model.status)
            result = await self.session.execute(query)
            rows = result.fetchall()
            
            counts = {row[0]: row[1] for row in rows}
            total = sum(counts.values())
            converted = counts.get(PendingActionStatus.CONVERTED.value, 0)
            pending = counts.get(PendingActionStatus.PENDING.value, 0)
            conversion_rate = (converted / total * 100) if total > 0 else 0.0
            
            return {
                "total": total,
                "pending": pending,
                "completed": counts.get(PendingActionStatus.COMPLETED.value, 0),
                "converted": converted,
                "cancelled": counts.get(PendingActionStatus.CANCELLED.value, 0),
                "conversion_rate": conversion_rate,
            }
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            raise e
    
    def _to_domain(self, orm_obj: PendingActionORM) -> PendingAction:
        """Convert ORM model to domain model."""
        domain_obj = super()._to_domain(orm_obj)
        # Convert status string to enum
        if isinstance(domain_obj.status, str):
            domain_obj.status = PendingActionStatus(domain_obj.status)
        return domain_obj
    
    def _to_orm(self, domain_obj: PendingAction) -> PendingActionORM:
        """Convert domain model to ORM model."""
        data = domain_obj.model_dump(exclude={"id"} if domain_obj.id else set())
        # Convert enum to string for database storage
        if "status" in data and isinstance(data["status"], PendingActionStatus):
            data["status"] = data["status"].value
        return self.orm_model(**data)

