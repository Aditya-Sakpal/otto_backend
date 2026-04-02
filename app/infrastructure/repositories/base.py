"""
Base repository.

All repositories inherit from this base class.
"""
import traceback
from typing import Generic, TypeVar, Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

T = TypeVar("T")  # ORM model type
D = TypeVar("D")  # Domain model type

logger = get_logger(__name__)


class BaseRepository(Generic[T, D]):
    """
    Base repository with common CRUD operations.

    Args:
        session: Async database session
        orm_model: SQLAlchemy ORM model class
        domain_model: Pydantic domain model class
    """

    def __init__(
        self,
        session: AsyncSession,
        orm_model: type[T],
        domain_model: type[D],
    ):
        self.session = session
        self.orm_model = orm_model
        self.domain_model = domain_model

    async def get_by_id(self, id: UUID) -> Optional[D]:
        """Get entity by ID."""
        try:
            result = await self.session.execute(
                select(self.orm_model).where(self.orm_model.id == id)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting entity by ID: {e}")
            traceback.print_exc()
            raise

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None,
    ) -> List[D]:
        """Get all entities with pagination and filters."""
        try:
            query = select(self.orm_model)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(self.orm_model, key):
                        query = query.where(getattr(self.orm_model, key) == value)

            query = query.offset(skip).limit(limit)
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting all entities: {e}")
            traceback.print_exc()
            raise

    async def create(self, domain_obj: D) -> D:
        """Create new entity."""
        try:
            orm_obj = self._to_orm(domain_obj)
            self.session.add(orm_obj)
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error creating entity: {e}")
            traceback.print_exc()
            raise

    async def update(self, id: UUID, domain_obj: D) -> Optional[D]:
        """Update entity."""
        try:
            orm_obj = await self.session.get(self.orm_model, id)
            if not orm_obj:
                return None

            # Update fields
            for key, value in domain_obj.model_dump(exclude={"id", "created_at"}).items():
                if hasattr(orm_obj, key):
                    setattr(orm_obj, key, value)

            await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._to_domain(orm_obj)
        except Exception as e:
            logger.error(f"Error updating entity: {e}")
            traceback.print_exc()
            raise

    async def delete(self, id: UUID) -> bool:
        """Delete entity."""
        try:
            orm_obj = await self.session.get(self.orm_model, id)
            if not orm_obj:
                return False

            await self.session.delete(orm_obj)
            await self.session.flush()
            return True
        except Exception as e:
            logger.error(f"Error deleting entity: {e}")
            traceback.print_exc()
            raise

    def _to_domain(self, orm_obj: T) -> D:
        """Convert ORM model to domain model."""
        return self.domain_model.model_validate(orm_obj)

    def _to_orm(self, domain_obj: D) -> T:
        """Convert domain model to ORM model."""
        # If domain_obj has an ID, include it when constructing the ORM object.
        # Previously this excluded the id when present which caused FK mismatches
        # when callers supplied a pre-generated UUID (e.g. creating a Call with a given id).
        data = domain_obj.model_dump(exclude=set() if domain_obj.id else {"id"})
        return self.orm_model(**data)

