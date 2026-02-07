"""
Post repository.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.post import PostORM, PostTag
from app.infrastructure.database.models.appointment import AppointmentORM

logger = get_logger(__name__)


class PostRepository:
    """Repository for Post entities."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, post_id: UUID) -> Optional[PostORM]:
        """Get post by ID."""
        result = await self.session.execute(select(PostORM).where(PostORM.id == post_id))
        return result.scalar_one_or_none()

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[PostORM]:
        """Get all posts for a company (via appointment -> company_id)."""
        order_col = getattr(PostORM, sort_by, PostORM.created_at)
        if sort_order == "asc":
            order_col = order_col.asc()
        else:
            order_col = order_col.desc()
        query = (
            select(PostORM)
            .join(AppointmentORM, PostORM.appointment_id == AppointmentORM.id)
            .where(AppointmentORM.company_id == company_id)
            .order_by(order_col)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        appointment_id: UUID,
        poster_id: UUID,
        note: Optional[str] = None,
        tags: Optional[PostTag] = None,
    ) -> PostORM:
        """Create a new post."""
        post = PostORM(
            appointment_id=appointment_id,
            poster_id=poster_id,
            note=note,
            tags=tags,
        )
        self.session.add(post)
        await self.session.flush()
        await self.session.refresh(post)
        return post

    async def update(self, post_id: UUID, note: Optional[str] = None, tags: Optional[PostTag] = None) -> Optional[PostORM]:
        """Update a post."""
        post = await self.get_by_id(post_id)
        if not post:
            return None
        if note is not None:
            post.note = note
        if tags is not None:
            post.tags = tags
        await self.session.flush()
        await self.session.refresh(post)
        return post

    async def delete(self, post_id: UUID) -> bool:
        """Delete a post."""
        post = await self.get_by_id(post_id)
        if not post:
            return False
        await self.session.delete(post)
        await self.session.flush()
        return True

    async def increment_likes(self, post_id: UUID) -> Optional[PostORM]:
        """Increment likes count for a post."""
        post = await self.get_by_id(post_id)
        if not post:
            return None
        post.likes = (post.likes or 0) + 1
        await self.session.flush()
        await self.session.refresh(post)
        return post
