"""
Post service for sales rep posts.
"""
from typing import Optional, List, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.repositories.post import PostRepository
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.post import PostTag
from sqlalchemy import select

logger = get_logger(__name__)


def _post_to_dict(post) -> dict[str, Any]:
    """Convert PostORM to response dict."""
    return {
        "id": str(post.id),
        "appointment_id": str(post.appointment_id),
        "poster_id": str(post.poster_id),
        "note": post.note,
        "tags": post.tags.value if post.tags else None,
        "likes": post.likes or 0,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


class PostService:
    """Service for sales rep posts."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PostRepository(session)

    async def list_posts(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[dict[str, Any]]:
        """List posts for a company, sorted by date, likes, etc."""
        posts = await self.repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return [_post_to_dict(p) for p in posts]

    async def get_post(self, post_id: UUID) -> Optional[dict[str, Any]]:
        """Get a single post by ID."""
        post = await self.repo.get_by_id(post_id)
        if not post:
            return None
        return _post_to_dict(post)

    async def create_post(
        self,
        appointment_id: UUID,
        poster_id: UUID,
        note: Optional[str] = None,
        tags: Optional[PostTag] = None,
    ) -> Optional[dict[str, Any]]:
        """Create a post linked to an appointment. Verifies appointment belongs to poster's company."""
        # Verify appointment exists and poster has access (e.g. same company)
        from app.infrastructure.database.models.user import UserORM
        user_result = await self.session.execute(select(UserORM).where(UserORM.id == poster_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.company_id:
            return None
        appt_result = await self.session.execute(
            select(AppointmentORM).where(
                AppointmentORM.id == appointment_id,
                AppointmentORM.company_id == user.company_id,
            )
        )
        if not appt_result.scalar_one_or_none():
            return None
        post = await self.repo.create(
            appointment_id=appointment_id,
            poster_id=poster_id,
            note=note,
            tags=tags,
        )
        return _post_to_dict(post)

    async def update_post(
        self,
        post_id: UUID,
        note: Optional[str] = None,
        tags: Optional[PostTag] = None,
    ) -> Optional[dict[str, Any]]:
        """Update a post."""
        post = await self.repo.update(post_id, note=note, tags=tags)
        if not post:
            return None
        return _post_to_dict(post)

    async def delete_post(self, post_id: UUID) -> bool:
        """Delete a post."""
        return await self.repo.delete(post_id)

    async def like_post(self, post_id: UUID) -> Optional[dict[str, Any]]:
        """Increment likes for a post."""
        post = await self.repo.increment_likes(post_id)
        if not post:
            return None
        return _post_to_dict(post)
