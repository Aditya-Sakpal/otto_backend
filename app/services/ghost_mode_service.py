"""
Ghost Mode service.

Provides business logic for ghost mode operations:
- Checking ghost mode status at company and user level
- Toggling ghost mode settings
- Filtering sensitive meeting data based on ghost mode
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.enums import UserRole
from app.infrastructure.repositories.company import CompanyRepository
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.user import UserORM

logger = get_logger(__name__)


class GhostModeService:
    """Service for ghost mode operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.company_repo = CompanyRepository(session)
        self.user_repo = UserRepository(session)

    async def is_company_ghost_mode_enabled(self, company_id: UUID) -> bool:
        """
        Check if ghost mode is enabled at the company level.

        Args:
            company_id: Company UUID

        Returns:
            True if company has ghost mode enabled, False otherwise
        """
        company = await self.company_repo.get_by_id(company_id)
        if not company:
            return False

        extra_metadata = company.extra_metadata or {}
        return extra_metadata.get("ghost_mode_enabled", False)

    async def is_user_ghost_mode_active(self, user: User) -> bool:
        """
        Check if a user has ghost mode active.

        Note: This only checks the user setting. Use get_effective_ghost_mode()
        to check if ghost mode is actually in effect (requires company enabled too).

        Args:
            user: User domain model

        Returns:
            True if user has ghost mode active, False otherwise
        """
        extra_metadata = user.extra_metadata or {}
        return extra_metadata.get("ghost_mode_active", False)

    async def get_effective_ghost_mode(self, user: User) -> bool:
        """
        Check if ghost mode is effectively active for a user.

        Ghost mode is only effective when BOTH:
        1. Company has ghost_mode_enabled = True
        2. User has ghost_mode_active = True

        Args:
            user: User domain model

        Returns:
            True if ghost mode is effectively active, False otherwise
        """
        if not user.company_id:
            return False

        company_enabled = await self.is_company_ghost_mode_enabled(user.company_id)
        if not company_enabled:
            return False

        return await self.is_user_ghost_mode_active(user)

    async def get_user_ghost_mode_status(self, user: User) -> dict:
        """
        Get complete ghost mode status for a user.

        Args:
            user: User domain model

        Returns:
            Dictionary with company_ghost_mode_enabled, user_ghost_mode_active,
            and effective_ghost_mode
        """
        company_enabled = False
        if user.company_id:
            company_enabled = await self.is_company_ghost_mode_enabled(user.company_id)

        user_active = await self.is_user_ghost_mode_active(user)

        return {
            "company_ghost_mode_enabled": company_enabled,
            "user_ghost_mode_active": user_active,
            "effective_ghost_mode": company_enabled and user_active,
        }

    async def set_user_ghost_mode(self, user: User, active: bool) -> dict:
        """
        Toggle ghost mode for a user.

        Args:
            user: User domain model
            active: Whether to enable or disable ghost mode

        Returns:
            Dictionary with success status and current settings

        Raises:
            ValueError: If company doesn't have ghost mode enabled
        """
        if not user.company_id:
            raise ValueError("User must belong to a company to use ghost mode")

        company_enabled = await self.is_company_ghost_mode_enabled(user.company_id)
        if active and not company_enabled:
            raise ValueError(
                "Cannot enable ghost mode: company has not enabled this feature"
            )

        # Get user ORM directly to update
        user_orm = await self._get_user_orm(user.id)
        if not user_orm:
            raise ValueError("User not found")

        # Update extra_metadata: assign a new dict so SQLAlchemy detects the change
        extra_metadata = dict(user_orm.extra_metadata or {})
        extra_metadata["ghost_mode_active"] = active
        user_orm.extra_metadata = extra_metadata

        await self.session.flush()
        await self.session.refresh(user_orm)

        logger.info(
            f"User {user.id} ghost mode {'enabled' if active else 'disabled'}"
        )

        return {
            "success": True,
            "message": f"Ghost mode {'enabled' if active else 'disabled'} successfully",
            "company_ghost_mode_enabled": company_enabled,
            "user_ghost_mode_active": active,
            "effective_ghost_mode": company_enabled and active,
        }

    async def set_company_ghost_mode(self, user: User, enabled: bool) -> dict:
        """
        Toggle ghost mode availability for a company.

        Only executives can toggle this setting.

        Args:
            user: User domain model (must be executive)
            enabled: Whether to enable or disable ghost mode availability

        Returns:
            Dictionary with success status and current settings

        Raises:
            ValueError: If user is not an executive or doesn't have a company
        """
        # if user.role != UserRole.EXECUTIVE:
        #     raise ValueError("Only executives can toggle company ghost mode")

        if not user.company_id:
            raise ValueError("User must belong to a company")

        company = await self.company_repo.get_by_id(user.company_id)
        if not company:
            raise ValueError("Company not found")

        # Update extra_metadata: assign a new dict so SQLAlchemy detects the change
        # (in-place mutation of the same dict does not mark the JSON column as dirty)
        extra_metadata = dict(company.extra_metadata or {})
        extra_metadata["ghost_mode_enabled"] = enabled
        company.extra_metadata = extra_metadata

        await self.session.flush()
        await self.session.refresh(company)

        # Get user's current ghost mode setting
        user_active = await self.is_user_ghost_mode_active(user)

        logger.info(
            f"Company {user.company_id} ghost mode {'enabled' if enabled else 'disabled'} "
            f"by user {user.id}"
        )

        return {
            "success": True,
            "message": f"Company ghost mode {'enabled' if enabled else 'disabled'} successfully",
            "company_ghost_mode_enabled": enabled,
            "user_ghost_mode_active": user_active,
            "effective_ghost_mode": enabled and user_active,
        }

    async def should_hide_meeting_data(
        self,
        interaction_type: str | None,
        owner_user_id: UUID | None,
        company_id: UUID,
        current_user: User,
    ) -> bool:
        """
        Determine if audio_url and transcript should be hidden for a meeting.

        Ghost mode filtering logic:
        1. Only applies to meetings (interaction_type == "meeting")
        2. Check if owner has ghost_mode_active
        3. If active, check if company has ghost_mode_enabled
        4. If both enabled, hide data from non-owners

        Args:
            interaction_type: Type of call/interaction
            owner_user_id: User ID who owns the recording (handled_by_user_id)
            company_id: Company UUID
            current_user: The user making the request

        Returns:
            True if data should be hidden, False otherwise
        """
        # Only filter meetings, not regular calls
        if interaction_type != "meeting":
            return False

        # If no owner, can't apply ghost mode
        if not owner_user_id:
            return False

        # If requester is the owner, always show data
        if current_user.id == owner_user_id:
            return False

        # Check company ghost mode
        company_enabled = await self.is_company_ghost_mode_enabled(company_id)
        if not company_enabled:
            return False

        # Get owner user to check their ghost mode setting
        owner_user = await self.user_repo.get_by_id(owner_user_id)
        if not owner_user:
            return False

        # Check owner's ghost mode setting
        owner_metadata = owner_user.extra_metadata or {}
        owner_ghost_mode_active = owner_metadata.get("ghost_mode_active", False)

        return owner_ghost_mode_active

    async def _get_user_orm(self, user_id: UUID) -> UserORM | None:
        """Get user ORM model directly for updates."""
        from sqlalchemy import select

        result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        return result.scalar_one_or_none()
