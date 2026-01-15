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
from app.domain.enums import InvitationStatus
from app.infrastructure.repositories.invitation import InvitationRepository
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.database.models.user import UserORM

logger = get_logger(__name__)


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

            # Check if there's already a pending invitation for this email and company
            existing = await self.invitation_repo.get_by_email_and_company(
                email=invitation_data.email,
                company_id=invitation_data.company_id,
                status=InvitationStatus.PENDING,
            )

            if existing:
                # Check if any are not expired
                now = datetime.now(timezone.utc)
                valid_invitations = [inv for inv in existing if inv.expires_at > now]
                if valid_invitations:
                    raise ValueError(
                        f"A pending invitation already exists for {invitation_data.email} "
                        f"to company {company.name}"
                    )

            # Generate secure token
            token = secrets.token_urlsafe(32)

            # Set expiration (7 days from now)
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            # Create invitation ORM model
            from app.infrastructure.database.models.invitation import InvitationORM
            invitation_orm = InvitationORM(
                email=invitation_data.email,
                company_id=invitation_data.company_id,
                inviter_id=inviter_id,
                token=token,
                status=InvitationStatus.PENDING.value,
                expires_at=expires_at,
            )

            self.session.add(invitation_orm)
            await self.session.flush()
            await self.session.refresh(invitation_orm)

            invitation = self.invitation_repo._to_domain(invitation_orm)

            # Send invitation email
            inviter_name = f"{inviter.first_name or ''} {inviter.last_name or ''}".strip() or inviter.email
            accept_url = f"{settings.API_URL}/api/v1/invites/accept/{token}"

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

    async def accept_invitation(self, token: str, accepting_user_email: str) -> Invitation:
        """
        Accept an invitation by token.

        Args:
            token: Invitation token
            accepting_user_email: Email of the authenticated user accepting the invite

        Returns:
            Accepted invitation

        Raises:
            ValueError: If invitation not found, expired, or already accepted
        """
        try:
            # Get invitation by token
            invitation = await self.invitation_repo.get_by_token(token)

            if not invitation:
                raise ValueError("Invitation not found")

            # # Ensure the authenticated user matches the invitation email
            # if invitation.email.lower() != accepting_user_email.lower():
            #     raise ValueError("Invitation email does not match the authenticated user")

            # Check if already accepted
            if invitation.status == InvitationStatus.ACCEPTED:
                raise ValueError("Invitation has already been accepted")

            # Check if expired
            if invitation.status == InvitationStatus.EXPIRED:
                raise ValueError("Invitation has expired")

            # Check expiration date
            now = datetime.now(timezone.utc)
            if invitation.expires_at < now:
                # Mark as expired
                await self.invitation_repo.update_status(
                    invitation.id,
                    InvitationStatus.EXPIRED,
                )
                raise ValueError("Invitation has expired")

            # Mark as accepted
            accepted_invitation = await self.invitation_repo.update_status(
                invitation.id,
                InvitationStatus.ACCEPTED,
                accepted_at=now,
            )

            if not accepted_invitation:
                raise ValueError("Failed to accept invitation")

            # Update user's company_id to match the invitation's company_id
            user_orm = await self.user_repo.get_by_email(invitation.email)
            if user_orm:
                user_orm.company_id = invitation.company_id
                await self.session.flush()
                logger.info(
                    f"Updated user {user_orm.email} company_id to {invitation.company_id} "
                    f"after accepting invitation"
                )
            else:
                logger.warning(
                    f"User with email {invitation.email} not found. "
                    f"Invitation accepted but user company_id not updated."
                )

            return accepted_invitation

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error accepting invitation: {e}")
            raise e

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
