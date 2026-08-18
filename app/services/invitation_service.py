"""
Invitation service.

Business logic layer for Invitation operations.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.email_controller import EmailController
from app.core.config import settings
from app.domain.models.invitation import Invitation
from app.domain.schemas.invitation import InvitationCreate
from app.domain.enums import InvitationStatus, UserRole
from app.infrastructure.repositories.invitation import InvitationRepository
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.database.models.user import UserORM
from app.domain.users.service import UserService
from app.domain.users.schemas import UserCreate
from app.domain.enums import UserRole

logger = get_logger(__name__)


class InvitationNotFoundError(ValueError):
    """Raised when an invitation token does not match any record."""


class InvitationService:
    """Service for Invitation business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.invitation_repo = InvitationRepository(session)
        self.user_repo = UserRepository(session)
        self.email_controller = EmailController()

    async def create_invitation(
        self,
        invitation_data: InvitationCreate,
        inviter_id: UUID,
    ) -> Invitation:
        """
        Create and send an invitation.

        Args:
            invitation_data: Invitation creation data
            inviter_id: ID of the user sending the invitation

        Returns:
            Created invitation

        Raises:
            ValueError: If company doesn't exist or validation fails
        """
        try:
            # Validate company exists
            company = await self.session.get(CompanyORM, invitation_data.company_id)
            if not company:
                raise ValueError(f"Company with ID {invitation_data.company_id} does not exist")

            # Validate inviter exists
            inviter = await self.session.get(UserORM, inviter_id)
            if not inviter:
                raise ValueError(f"Inviter with ID {inviter_id} does not exist")

            # # Check if there's already a pending invitation for this email and company
            # existing = await self.invitation_repo.get_by_email_and_company(
            #     email=invitation_data.email,
            #     company_id=invitation_data.company_id,
            #     status=InvitationStatus.PENDING,
            # )

            # if existing:
            #     # Check if any are not expired
            #     now = datetime.now(timezone.utc)
            #     valid_invitations = [inv for inv in existing if inv.expires_at > now]
            #     if valid_invitations:
            #         raise ValueError(
            #             f"A pending invitation already exists for {invitation_data.email} "
            #             f"to company {company.name}"
            #         )

            # Generate secure token
            token = secrets.token_urlsafe(32)

            # Set expiration (7 days from now)
            expires_at = datetime.now(timezone.utc) + timedelta(days=3)

            # Create invitation ORM model
            from app.infrastructure.database.models.invitation import InvitationORM
            invitation_orm = InvitationORM(
                email=invitation_data.email,
                company_id=invitation_data.company_id,
                inviter_id=inviter_id,
                token=token,
                role=invitation_data.role.value,
                status=InvitationStatus.PENDING.value,
                expires_at=expires_at,
            )

            self.session.add(invitation_orm)
            await self.session.flush()
            await self.session.refresh(invitation_orm)

            invitation = self.invitation_repo._to_domain(invitation_orm)

            # Send invitation email
            inviter_name = f"{inviter.first_name or ''} {inviter.last_name or ''}".strip() or inviter.email
            accept_url = f"{settings.APP_URL}/accept-invite?token={token}"

            email_sent = await self.email_controller.send_invitation_email(
                to=invitation_data.email,
                inviter_name=inviter_name,
                company_name=company.name,
                accept_url=accept_url,
            )

            if not email_sent:
                logger.warning(
                    f"Invitation created but email failed to send for {invitation_data.email}"
                )

            return invitation

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error creating invitation: {e}")
            raise e

    async def validate_token(self, token: str) -> Invitation:
        """
        Validate an invitation token without accepting it.

        Args:
            token: Invitation token

        Returns:
            Invitation if valid (exists, not accepted/expired, not past expiration)

        Raises:
            ValueError: If invitation not found, expired, or already accepted
        """
        # Get invitation by token
        invitation = await self.invitation_repo.get_by_token(token)

        if not invitation:
            raise InvitationNotFoundError("Invitation not found")

        # Check if already accepted
        if invitation.status == InvitationStatus.ACCEPTED:
            raise ValueError("Invitation has already been accepted")

        # Check if expired (status)
        if invitation.status == InvitationStatus.EXPIRED:
            raise ValueError("Invitation has expired")

        # Check expiration date
        now = datetime.now(timezone.utc)
        if invitation.expires_at < now:
            raise ValueError("Invitation has expired")

        return invitation

    async def accept_invitation_signup(
        self,
        token: str,
        password: str,
        first_name: str,
        last_name: str,
    ):
        """
        Accept an invitation by token by creating a new user account.

        This is intended for invited users who do not yet have an account.

        Args:
            token: Invitation token
            email: User email (must match invitation email)
            password: Plaintext password
            first_name: First name
            last_name: Last name

        Returns:
            (accepted_invitation, user)

        Raises:
            ValueError: If token invalid/expired/accepted
        """
        # Validate invitation token first (no acceptance yet)
        invitation = await self.validate_token(token)

        # Existing or new user path
        existing_user = await self.user_repo.get_by_email(invitation.email)
        if existing_user:
            # Update company and basic profile fields only if missing
            if not existing_user.company_id or existing_user.company_id != invitation.company_id:
                existing_user.company_id = invitation.company_id
            if not existing_user.first_name:
                existing_user.first_name = first_name
            if not existing_user.last_name:
                existing_user.last_name = last_name
            # Do not override existing role; set only if missing
            if not existing_user.role and invitation.role:
                existing_user.role = invitation.role.value
            await self.session.flush()
            user = self.user_repo._to_domain(existing_user)
        else:
            # Create the user, setting company_id from the invitation
            user_service = UserService(self.session)
            user_data = UserCreate(
                email=invitation.email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=invitation.role or UserRole.SALES_REP,
                company_id=invitation.company_id,
            )
            user = await user_service.create(user_data)

        # Mark invitation accepted
        now = datetime.now(timezone.utc)
        accepted_invitation = await self.invitation_repo.update_status(
            invitation.id,
            InvitationStatus.ACCEPTED,
            accepted_at=now,
        )
        if not accepted_invitation:
            raise ValueError("Failed to accept invitation")

        return accepted_invitation, user

    async def get_by_id(self, invitation_id: UUID) -> Optional[Invitation]:
        """
        Get invitation by ID.

        Args:
            invitation_id: Invitation ID

        Returns:
            Invitation or None
        """
        try:
            return await self.invitation_repo.get_by_id(invitation_id)
        except Exception as e:
            logger.error(f"Error getting invitation by ID: {e}")
            raise e

    async def expire_old_invitations(self) -> int:
        """
        Mark expired invitations as expired.

        Returns:
            Number of invitations expired
        """
        try:
            return await self.invitation_repo.expire_old_invitations()
        except Exception as e:
            logger.error(f"Error expiring old invitations: {e}")
            raise e
