"""
Appointment repository.
"""
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime, time, timezone

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.enums import UserRole
from app.domain.models.appointment import Appointment
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class AppointmentRepository(BaseRepository[AppointmentORM, Appointment]):
    """Repository for Appointment entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AppointmentORM, Appointment)

    async def get_by_company(
        self,
        company_id: UUID,
        start_date: Optional[datetime | date] = None,
        end_date: Optional[datetime | date] = None,
        past_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company, optionally filtered by scheduled datetime range or past only."""
        try:
            if start_date is not None or end_date is not None or past_only:
                query = select(AppointmentORM).where(AppointmentORM.company_id == company_id)
                if start_date is not None:
                    start_dt = start_date if isinstance(start_date, datetime) else datetime.combine(start_date, time.min, tzinfo=timezone.utc)
                    query = query.where(AppointmentORM.scheduled_start >= start_dt)
                if end_date is not None:
                    end_dt = end_date if isinstance(end_date, datetime) else datetime.combine(end_date, time.max, tzinfo=timezone.utc)
                    query = query.where(AppointmentORM.scheduled_start <= end_dt)
                if past_only:
                    query = query.where(AppointmentORM.scheduled_start < datetime.now(timezone.utc))
                query = query.offset(skip).limit(limit)
                result = await self.session.execute(query)
                orm_objs = result.scalars().all()
                return [self._to_domain(obj) for obj in orm_objs]
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting appointments by company: {e}")
            raise e

    async def count_by_company(
        self,
        company_id: UUID,
    ) -> int:
        """Count appointments for a company."""
        try:
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting appointments: {e}")
            raise e

    async def count_by_outcome(
        self,
        company_id: UUID,
        outcome: str,
    ) -> int:
        """Count appointments by outcome."""
        try:
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.outcome == outcome,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting appointments by outcome: {e}")
            raise e

    async def count_today(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
    ) -> int:
        """Count appointments scheduled for today."""
        try:
            today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
            today_end = datetime.combine(date.today(), time.max, tzinfo=timezone.utc)
            filters = [
                AppointmentORM.company_id == company_id,
                AppointmentORM.scheduled_start >= today_start,
                AppointmentORM.scheduled_start <= today_end,
            ]
            if assigned_rep_id:
                filters.append(AppointmentORM.assigned_rep_id == assigned_rep_id)
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*filters)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting today's appointments: {e}")
            raise e

    async def count_pending(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
    ) -> int:
        """Count appointments with pending outcome (not yet completed)."""
        try:
            filters = [
                AppointmentORM.company_id == company_id,
                or_(
                    AppointmentORM.outcome.is_(None),
                    AppointmentORM.outcome == "pending",
                ),
            ]
            if assigned_rep_id:
                filters.append(AppointmentORM.assigned_rep_id == assigned_rep_id)
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*filters)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting pending appointments: {e}")
            raise e

    async def count_closed(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
    ) -> int:
        """Count appointments with closed outcome (won or lost)."""
        try:
            filters = [
                AppointmentORM.company_id == company_id,
                AppointmentORM.outcome.in_(["won", "lost"]),
            ]
            if assigned_rep_id:
                filters.append(AppointmentORM.assigned_rep_id == assigned_rep_id)
            result = await self.session.execute(
                select(func.count(AppointmentORM.id)).where(*filters)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting closed appointments: {e}")
            raise e

    async def get_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        start_date: Optional[datetime | date] = None,
        end_date: Optional[datetime | date] = None,
        past_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company assigned to a specific sales rep, optionally filtered by scheduled datetime range or past only."""
        try:
            if start_date is not None or end_date is not None or past_only:
                query = (
                    select(AppointmentORM)
                    .where(AppointmentORM.company_id == company_id)
                    .where(AppointmentORM.assigned_rep_id == assigned_rep_id)
                )
                if start_date is not None:
                    start_dt = start_date if isinstance(start_date, datetime) else datetime.combine(start_date, time.min, tzinfo=timezone.utc)
                    query = query.where(AppointmentORM.scheduled_start >= start_dt)
                if end_date is not None:
                    end_dt = end_date if isinstance(end_date, datetime) else datetime.combine(end_date, time.max, tzinfo=timezone.utc)
                    query = query.where(AppointmentORM.scheduled_start <= end_dt)
                if past_only:
                    query = query.where(AppointmentORM.scheduled_start < datetime.now(timezone.utc))
                query = query.offset(skip).limit(limit)
                result = await self.session.execute(query)
                orm_objs = result.scalars().all()
                return [self._to_domain(obj) for obj in orm_objs]
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={
                    "company_id": company_id,
                    "assigned_rep_id": assigned_rep_id,
                },
            )
        except Exception as e:
            logger.error(f"Error getting appointments by assigned rep: {e}")
            raise e

    async def get_by_lead_id(self, lead_id: UUID) -> Optional[Appointment]:
        """Get appointment by lead ID."""
        try:
            result = await self.session.execute(
                select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
            )
            orm_obj = result.scalar_one_or_none()
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error getting appointment by lead ID: {e}")
            raise e

    async def get_by_interaction_id(self, interaction_id: UUID) -> Optional[Appointment]:
        """Get appointment by call/interaction ID (for appointments created from calls)."""
        try:
            result = await self.session.execute(
                select(AppointmentORM).where(AppointmentORM.interaction_id == interaction_id)
            )
            orm_obj = result.scalar_one_or_none()
            return self._to_domain(orm_obj) if orm_obj else None
        except Exception as e:
            logger.error(f"Error getting appointment by interaction ID: {e}")
            raise e

    async def get_ridealongs_filtered(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        ghost_mode: Optional[bool] = None,
        sales_rep_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        order_desc: bool = False,
    ) -> List[Appointment]:
        """
        Get appointments (ridealongs) with filters for dashboard.

        Args:
            company_id: Company UUID
            start_date: Filter scheduled on or after this date
            end_date: Filter scheduled on or before this date
            status: Filter by outcome (pending, won, lost, no_show, rescheduled)
            ghost_mode: Filter by assigned rep's ghost_mode_active (True/False)
            sales_rep_name: Filter by rep name (case-insensitive partial match)
            skip: Pagination offset
            limit: Max results
            order_desc: If True, order by scheduled_start desc (newest first)

        Returns:
            List of Appointment domain models
        """
        try:
            needs_user_join = ghost_mode is not None or (
                sales_rep_name is not None and sales_rep_name.strip()
            )

            # Join User so we only include appointments assigned to a sales rep
            query = (
                select(AppointmentORM)
                .where(AppointmentORM.company_id == company_id)
                .where(AppointmentORM.assigned_rep_id.isnot(None))
                .join(UserORM, AppointmentORM.assigned_rep_id == UserORM.id)
                .where(UserORM.role == UserRole.SALES_REP.value)
            )

            if start_date is not None:
                start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
                query = query.where(AppointmentORM.scheduled_start >= start_dt)
            if end_date is not None:
                end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
                query = query.where(AppointmentORM.scheduled_start <= end_dt)

            if status is not None:
                status_lower = status.lower().strip()
                outcome_map = {
                    "in progress": "pending",
                    "pending": "pending",
                    "won": "won",
                    "lost": "lost",
                    "no show": "no_show",
                    "no_show": "no_show",
                    "rescheduled": "rescheduled",
                }
                outcome_val = outcome_map.get(status_lower, status_lower)
                if outcome_val in ("pending", "won", "lost", "no_show", "rescheduled"):
                    query = query.where(AppointmentORM.outcome == outcome_val)

            if needs_user_join:
                if ghost_mode is not None:
                    dialect = self.session.get_bind().dialect.name
                    if dialect == "postgresql":
                        gm_key = UserORM.extra_metadata["ghost_mode_active"].astext
                        if ghost_mode:
                            query = query.where(gm_key == "true")
                        else:
                            query = query.where(
                                or_(gm_key.is_(None), gm_key != "true")
                            )

                if sales_rep_name is not None and sales_rep_name.strip():
                    name_pattern = f"%{sales_rep_name.strip()}%"
                    query = query.where(
                        or_(
                            func.coalesce(UserORM.first_name, "").ilike(name_pattern),
                            func.coalesce(UserORM.last_name, "").ilike(name_pattern),
                        )
                    )

            if order_desc:
                query = query.order_by(AppointmentORM.scheduled_start.desc())
            else:
                query = query.order_by(AppointmentORM.scheduled_start.asc())

            query = query.offset(skip).limit(limit)
            result = await self.session.execute(query)
            orm_objs = result.unique().scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting filtered ridealongs: {e}")
            raise e

    async def get_upcoming(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """
        Get upcoming appointments (future, pending status only).

        Returns appointments with:
        - scheduled_start >= now (future)
        - outcome is None or 'pending'
        - Sorted by scheduled_start ASC (soonest first)

        Args:
            company_id: Company UUID
            assigned_rep_id: Optional filter by assigned sales rep
            skip: Pagination offset
            limit: Max results

        Returns:
            List of upcoming appointments
        """
        try:
            query = (
                select(AppointmentORM)
                .where(AppointmentORM.company_id == company_id)
                .where(AppointmentORM.scheduled_start >= datetime.now(timezone.utc))
                .where(
                    or_(
                        AppointmentORM.outcome.is_(None),
                        AppointmentORM.outcome == "pending",
                    )
                )
            )

            if assigned_rep_id:
                query = query.where(AppointmentORM.assigned_rep_id == assigned_rep_id)

            query = query.order_by(AppointmentORM.scheduled_start.asc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting upcoming appointments: {e}")
            raise e

    async def update_appointment(self, appointment: Appointment) -> Appointment:
        """Update appointment."""
        try:
            orm_obj = self._to_orm(appointment)
            self.session.add(orm_obj)
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error updating appointment: {e}")
            raise e

    async def upsert_appointment(self, appointment: Appointment) -> Appointment:
        """Upsert appointment."""
        try:
            existing = await self.get_by_id(appointment.id)
            if existing:
                return await self.update(existing.id, appointment)
            else:
                return await self.create(appointment)
        except Exception as e:
            logger.error(f"Error upserting appointment: {e}")
            raise e

    def _to_domain(self, orm_obj: AppointmentORM) -> Appointment:
        """Convert ORM model to domain model."""
        return Appointment.model_validate(orm_obj)

    def _to_orm(self, appointment: Appointment) -> AppointmentORM:
        """Convert domain model to ORM model."""
        return AppointmentORM(**appointment.model_dump(exclude={"id"}))
