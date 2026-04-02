"""
User repository.

Data access layer for User entities.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.enums import UserRole
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

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[User]:
        """
        Get all users for a company.

        Args:
            company_id: Company UUID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of User domain models
        """
        try:
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting users by company: {e}")
            raise e

    async def get_by_role(
        self,
        role: UserRole,
        company_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[User]:
        """
        Get users by role, optionally filtered by company.

        Args:
            role: User role
            company_id: Optional company UUID filter
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of User domain models
        """
        try:
            # Convert enum to string value for comparison (ORM stores role as string)
            role_value = role.value if isinstance(role, UserRole) else role
            query = select(UserORM).where(
                UserORM.role == role_value,
                UserORM.is_active == True,
            )

            if company_id:
                query = query.where(UserORM.company_id == company_id)

            query = query.offset(skip).limit(limit)
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting users by role: {e}")
            raise e

    async def find_by_name(
        self,
        company_id: UUID,
        first_name: str,
        last_name: str,
    ) -> Optional[UserORM]:
        """
        Find a user by first/last name within a company (case-insensitive).

        Returns the first matching UserORM or None.
        """
        try:
            query = (
                select(UserORM)
                .where(UserORM.company_id == company_id)
                .where(func.lower(UserORM.first_name) == first_name.lower())
                .where(func.lower(UserORM.last_name) == last_name.lower())
                .limit(1)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding user by name: {e}")
            return None

    def _to_domain(self, orm_obj: UserORM) -> User:
        """
        Convert ORM model to domain model.

        Excludes password_hash for security.
        Handles case-insensitive role conversion for enum compatibility.
        """
        # Handle role conversion with case-insensitive matching
        role = self._normalize_user_role(orm_obj.role)

        return User(
            id=orm_obj.id,
            email=orm_obj.email,
            role=role,
            is_active=orm_obj.is_active,
            first_name=orm_obj.first_name,
            last_name=orm_obj.last_name,
            company_id=orm_obj.company_id,
            created_at=orm_obj.created_at,
            extra_metadata=orm_obj.extra_metadata,
        )

    @staticmethod
    def _normalize_user_role(role_value: UserRole | str) -> UserRole:
        """
        Normalize user role to UserRole enum with case-insensitive matching.

        Handles cases where the database might store:
        - Enum values: "csr", "sales_rep", "executive"
        - Enum names: "CSR", "SALES_REP", "EXECUTIVE"
        - Mixed case: "Sales_Rep", "Csr", etc.

        Args:
            role_value: UserRole enum or string value

        Returns:
            UserRole enum

        Raises:
            ValueError: If role value cannot be matched
        """
        # If already a UserRole enum, return it
        if isinstance(role_value, UserRole):
            return role_value

        # Convert to lowercase string for comparison
        role_str = str(role_value).lower().strip()

        # Try to match by enum value (case-insensitive)
        for enum_member in UserRole:
            if enum_member.value.lower() == role_str:
                return enum_member

        # Try to match by enum name (case-insensitive)
        # Handle both underscore and no-underscore formats
        role_str_normalized = role_str.replace("_", "").replace("-", "")
        for enum_member in UserRole:
            enum_name_normalized = enum_member.name.lower().replace("_", "")
            if enum_name_normalized == role_str_normalized:
                return enum_member

        # If no match found, raise error with helpful message
        valid_values = [f"{e.name} ({e.value})" for e in UserRole]
        raise ValueError(
            f"Invalid user role: '{role_value}'. "
            f"Valid roles: {', '.join(valid_values)}"
        )

