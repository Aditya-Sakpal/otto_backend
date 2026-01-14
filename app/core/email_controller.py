"""
Email controller with factory pattern.

Central controller for handling email notifications with support for different email types.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Optional plain text content
            from_email: Optional sender email (defaults to configured sender)

        Returns:
            True if email was sent successfully, False otherwise
        """
        pass


class MailgunProvider(EmailProvider):
    """Mailgun email provider implementation."""

    def __init__(self):
        self.api_key = settings.MAILGUN_API_KEY
        self.domain = settings.MAILGUN_DOMAIN
        self.base_url = settings.MAILGUN_BASE_URL
        self.from_email = settings.MAILGUN_FROM_EMAIL

        if not self.api_key or not self.domain:
            logger.warning(
                "Mailgun credentials not configured. Email sending will fail. "
                "Set MAILGUN_API_KEY and MAILGUN_DOMAIN environment variables."
            )

    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send email via Mailgun API.

        Args:
            to: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Optional plain text content
            from_email: Optional sender email

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key or not self.domain:
            logger.error("Mailgun credentials not configured")
            return False

        try:
            url = f"{self.base_url}/{self.domain}/messages"

            data = {
                "from": from_email or self.from_email,
                "to": to,
                "subject": subject,
                "html": html_content,
            }

            if text_content:
                data["text"] = text_content

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    auth=("api", self.api_key),
                    data=data,
                    timeout=10.0,
                )

            if response.status_code == 200:
                logger.info(f"Email sent successfully to {to}")
                return True
            else:
                logger.error(
                    f"Failed to send email to {to}. Status: {response.status_code}, "
                    f"Response: {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending email via Mailgun: {e}")
            return False


class EmailFactory:
    """Factory for creating email provider instances."""

    _providers: Dict[str, type[EmailProvider]] = {
        "mailgun": MailgunProvider,
    }

    @classmethod
    def create_provider(cls, provider_type: str = "mailgun") -> EmailProvider:
        """
        Create an email provider instance.

        Args:
            provider_type: Type of email provider (default: "mailgun")

        Returns:
            EmailProvider instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_class = cls._providers.get(provider_type.lower())
        if not provider_class:
            raise ValueError(
                f"Unsupported email provider: {provider_type}. "
                f"Supported providers: {list(cls._providers.keys())}"
            )

        return provider_class()

    @classmethod
    def register_provider(cls, provider_type: str, provider_class: type[EmailProvider]):
        """
        Register a new email provider type.

        Args:
            provider_type: Name of the provider type
            provider_class: EmailProvider subclass
        """
        if not issubclass(provider_class, EmailProvider):
            raise ValueError("Provider class must inherit from EmailProvider")
        cls._providers[provider_type.lower()] = provider_class


class EmailController:
    """
    Central email controller.

    Handles sending different types of emails through the configured provider.
    """

    def __init__(self, provider_type: str = "mailgun"):
        """
        Initialize email controller.

        Args:
            provider_type: Type of email provider to use
        """
        self.provider = EmailFactory.create_provider(provider_type)

    async def send_invitation_email(
        self,
        to: str,
        inviter_name: str,
        company_name: str,
        accept_url: str,
    ) -> bool:
        """
        Send an invitation email.

        Args:
            to: Recipient email address
            inviter_name: Name of the person sending the invitation
            company_name: Name of the company
            accept_url: URL to accept the invitation

        Returns:
            True if email was sent successfully, False otherwise
        """
        subject = f"Invitation to join {company_name}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4F46E5; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>You're Invited!</h1>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p><strong>{inviter_name}</strong> has invited you to join <strong>{company_name}</strong> on Otto.</p>
                    <p>Click the button below to accept the invitation and get started:</p>
                    <div style="text-align: center;">
                        <a href="{accept_url}" class="button">Accept Invitation</a>
                    </div>
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #4F46E5;">{accept_url}</p>
                    <p>This invitation will expire in 7 days.</p>
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message from Otto. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
        Hello,

        {inviter_name} has invited you to join {company_name} on Otto.

        Click the following link to accept the invitation:
        {accept_url}

        This invitation will expire in 7 days.

        If you didn't expect this invitation, you can safely ignore this email.

        ---
        This is an automated message from Otto. Please do not reply to this email.
        """

        return await self.provider.send_email(
            to=to,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
