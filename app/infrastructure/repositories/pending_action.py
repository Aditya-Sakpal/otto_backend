"""
Pending action repository.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_, or_, func as sql_func, desc
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
            query = query.offset(skip).limit(limit).order_by(desc(self.orm_model.due_at))
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
            query = query.order_by(desc(self.orm_model.due_at))
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
            query = query.offset(skip).limit(limit).order_by(desc(self.orm_model.due_at))
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
            query = query.order_by(
                PendingActionORM.due_at.asc().nulls_last(),
                desc(PendingActionORM.created_at),
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
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """Get task counts by status for summary cards (optionally filtered by created_at range)."""
        try:
            query = select(
                PendingActionORM.status,
                sql_func.count(PendingActionORM.id).label("count"),
            ).where(PendingActionORM.company_id == company_id)
            if start_date is not None:
                query = query.where(PendingActionORM.created_at >= start_date)
            if end_date is not None:
                query = query.where(PendingActionORM.created_at <= end_date)
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
