"""
User service.

Business logic layer for User operations.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, get_password_hash
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.users.repository import UserRepository
from app.domain.users.schemas import UserCreate, UserUpdate
from app.domain.enums import UserRole

logger = get_logger(__name__)


class UserService:
    """Service for User business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_by_id(self, user_id: str | UUID) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User ID (UUID or string)

        Returns:
            User or None
        """
        try:
            if isinstance(user_id, str):
                return await self.user_repo.get_by_id_str(user_id)
            return await self.user_repo.get_by_id(user_id)
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            raise e

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: User email

        Returns:
            User or None
        """
        try:
            user_orm = await self.user_repo.get_by_email(email)
            if user_orm:
                return self.user_repo._to_domain(user_orm)
            return None
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            raise e

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User if authentication succeeds, None otherwise
        """
        try:
            user_orm = await self.user_repo.get_by_email(email)

            if not user_orm:
                logger.warning(f"Authentication failed: User not found - {email}")
                return None

            if not user_orm.is_active:
                logger.warning(f"Authentication failed: User inactive - {email}")
                return None

            # Check if user has a password
            if not user_orm.password_hash:
                logger.warning(f"Authentication failed: User has no password set - {email}")
                return None

            if not verify_password(password, user_orm.password_hash):
                logger.warning(f"Authentication failed: Invalid password - {email}")
                return None

            return self.user_repo._to_domain(user_orm)
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            raise e

    async def create(self, user_data: UserCreate) -> User:
        """
        Create a new user.

        Args:
            user_data: User creation data

        Returns:
            Created user
        """
        try:
            # Check if user already exists
            existing = await self.user_repo.get_by_email(user_data.email)
            if existing:
                raise ValueError(f"User with email {user_data.email} already exists")

            # Hash password
            password_hash = get_password_hash(user_data.password)

            # Validate company_id if provided
            if user_data.company_id:
                from app.infrastructure.database.models.company import CompanyORM
                company = await self.session.get(CompanyORM, user_data.company_id)
                if not company:
                    raise ValueError(f"Company with ID {user_data.company_id} does not exist")

            # Create ORM model
            from app.infrastructure.database.models.user import UserORM
            user_orm = UserORM(
                email=user_data.email,
                password_hash=password_hash,
                role=user_data.role.value,  # Convert enum to string value for database
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                company_id=user_data.company_id,
                is_active=True,
            )

            self.session.add(user_orm)
            await self.session.flush()
            await self.session.refresh(user_orm)

            return self.user_repo._to_domain(user_orm)
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise e

    async def update(self, user_id: UUID, user_data: UserUpdate) -> Optional[User]:
        """
        Update user.

        Args:
            user_id: User ID
            user_data: User update data

        Returns:
            Updated user or None if not found
        """
        try:
            user_orm = await self.session.get(
                self.user_repo.orm_model,
                user_id
            )

            if not user_orm:
                return None

            # Update fields
            update_data = user_data.model_dump(exclude_unset=True)

            # Handle password update separately (if provided)
            if "password" in update_data:
                update_data["password_hash"] = get_password_hash(update_data.pop("password"))

            for key, value in update_data.items():
                if hasattr(user_orm, key):
                    setattr(user_orm, key, value)

            await self.session.flush()
            await self.session.refresh(user_orm)

            return self.user_repo._to_domain(user_orm)
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            raise e

    async def list_users(
        self,
        company_id: Optional[UUID] = None,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[User]:
        """
        List users with optional filters.

        Args:
            company_id: Optional company ID filter
            role: Optional role filter
            is_active: Optional active status filter
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of User domain models
        """
        try:
            # If role filter is specified, use role-specific method
            if role:
                return await self.user_repo.get_by_role(
                    role=role,
                    company_id=company_id,
                    skip=skip,
                    limit=limit,
                )

            # Build filters dict
            filters = {}
            if company_id:
                filters["company_id"] = company_id
            if is_active is not None:
                filters["is_active"] = is_active

            # Use get_all with filters
            return await self.user_repo.get_all(
                skip=skip,
                limit=limit,
                filters=filters if filters else None,
            )
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            raise e

    async def delete(self, user_id: UUID) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID to delete

        Returns:
            True if user was deleted, False if not found
        """
        try:
            return await self.user_repo.delete(user_id)
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            raise e

