"""
User repository.

Data access layer for User entities.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.users.models import User
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class UserRepository(BaseRepository[UserORM, User]):
    """Repository for User entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, UserORM, User)
    
    async def get_by_email(self, email: str) -> Optional[UserORM]:
        """
        Get user by email.
        
        Returns ORM model (not domain model) because we need password_hash.
        This is a security measure - password_hash should not be in domain layer.
        
        Args:
            email: User email
            
        Returns:
            UserORM or None
        """
        try:
            result = await self.session.execute(
                select(UserORM).where(UserORM.email == email)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            raise e
    
    async def get_by_id_str(self, user_id: str) -> Optional[User]:
        """
        Get user by ID as string (for JWT token parsing).
        
        Args:
            user_id: User ID as string
            
        Returns:
            User domain model or None
        """
        try:
            user_uuid = UUID(user_id)
            return await self.get_by_id(user_uuid)
        except ValueError:
            return None
        except Exception as e:
            logger.error(f"Error getting user by ID string: {e}")
            raise e
    
    def _to_domain(self, orm_obj: UserORM) -> User:
        """
        Convert ORM model to domain model.
        
        Excludes password_hash for security.
        """
        return User(
            id=orm_obj.id,
            email=orm_obj.email,
            role=orm_obj.role,
            is_active=orm_obj.is_active,
            first_name=orm_obj.first_name,
            last_name=orm_obj.last_name,
            company_id=orm_obj.company_id,
            created_at=orm_obj.created_at,
            extra_metadata=orm_obj.extra_metadata,
        )

