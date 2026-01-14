"""
User repository.

Data access layer for User entities.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
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
            query = select(UserORM).where(UserORM.role == role)
            
            if company_id:
                query = query.where(UserORM.company_id == company_id)
            
            query = query.offset(skip).limit(limit)
            result = await self.session.execute(query)
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting users by role: {e}")
            raise e
    
    def _to_domain(self, orm_obj: UserORM) -> User:
        """
        Convert ORM model to domain model.
        
        Excludes password_hash for security.
        Handles role conversion from database string to enum.
        """
        # Handle role conversion - database might have string, ensure it's converted to enum
        role = orm_obj.role
        
        # If it's already a UserRole enum, use it directly
        if isinstance(role, UserRole):
            pass  # Already correct
        elif isinstance(role, str):
            # Try to convert string to enum (handle case variations)
            role_lower = role.lower().strip()
            if role_lower == "csr":
                role = UserRole.CSR
            elif role_lower in ("sales_rep", "salesrep", "sales rep"):
                role = UserRole.SALES_REP
            elif role_lower == "executive":
                role = UserRole.EXECUTIVE
            else:
                # Try to match by enum value
                try:
                    # Try to find enum by value
                    for enum_member in UserRole:
                        if enum_member.value.lower() == role_lower:
                            role = enum_member
                            break
                    else:
                        # Default to SALES_REP if unknown
                        logger.warning(f"Unknown role value '{role}', defaulting to SALES_REP")
                        role = UserRole.SALES_REP
                except Exception as e:
                    logger.warning(f"Error converting role '{role}': {e}, defaulting to SALES_REP")
                    role = UserRole.SALES_REP
        else:
            # Unknown type, default to SALES_REP
            logger.warning(f"Unknown role type '{type(role)}' with value '{role}', defaulting to SALES_REP")
            role = UserRole.SALES_REP
        
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

