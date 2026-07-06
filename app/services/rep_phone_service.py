"""
Rep phone registration and OTP verification service.

Handles the one-time phone registration flow for sales reps:
1. Rep submits phone number
2. OTP sent via Twilio SMS
3. Rep verifies OTP
4. Phone marked as verified — ready for masked comms
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.rep_phone import RepPhone
from app.infrastructure.integrations.twilio_client import get_twilio_client
from app.infrastructure.repositories.rep_phone import RepPhoneRepository

logger = get_logger(__name__)

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10


class RepPhoneNotRegisteredError(Exception):
    """Rep has no verified phone number."""

    def __init__(self, user_id: UUID):
        self.user_id = user_id
        super().__init__(f"Rep {user_id} has no verified phone number")


class RepPhoneService:
    """Handles rep phone registration and OTP verification."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RepPhoneRepository(session)
        self.twilio = get_twilio_client()

    async def register_phone(self, user_id: UUID, phone_number: str) -> dict:
        """
        Start phone registration — sends OTP via Twilio SMS.

        Returns dict with status and masked phone for UI display.
        """
        phone_number = self._normalize_phone(phone_number)
        code = self._generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

        # Create or update the rep_phone record with new OTP
        await self.repo.upsert_phone(
            user_id=user_id,
            phone_number=phone_number,
            verification_code=code,
            expires_at=expires_at,
        )

        # Send OTP via Twilio
        if self.twilio.is_available():
            sent = self.twilio.send_verification_sms(phone_number, code)
            if not sent:
                logger.error("Failed to send OTP SMS", user_id=str(user_id))
                return {"status": "error", "message": "Failed to send verification code"}
        else:
            logger.warning(
                "Twilio not available — OTP not sent (dev mode?)",
                user_id=str(user_id),
                code=code,
            )

        masked = self._mask_phone(phone_number)
        logger.info("OTP sent for phone registration", user_id=str(user_id), phone=masked)
        return {"status": "otp_sent", "phone_masked": masked}

    async def verify_phone(self, user_id: UUID, phone_number: str, code: str) -> RepPhone:
        """
        Verify OTP and mark phone as verified.

        Raises ValueError if code is invalid or expired.
        """
        phone_number = self._normalize_phone(phone_number)
        rep_phone = await self.repo.get_by_user(user_id)

        if not rep_phone:
            raise ValueError("No phone registration found. Please register first.")

        if rep_phone.phone_number != phone_number:
            raise ValueError("Phone number does not match the registered number.")

        if not rep_phone.verification_code:
            raise ValueError("No pending verification. Please register again.")

        if rep_phone.verification_expires_at and rep_phone.verification_expires_at < datetime.now(
            timezone.utc
        ):
            raise ValueError("Verification code has expired. Please register again.")

        if rep_phone.verification_code != code:
            raise ValueError("Invalid verification code.")

        # Mark as verified
        verified = await self.repo.mark_verified(
            user_id=user_id,
            phone_number=phone_number,
            verified_at=datetime.now(timezone.utc),
        )
        logger.info("Phone verified", user_id=str(user_id))
        return verified

    async def get_verified_phone(self, user_id: UUID) -> Optional[RepPhone]:
        """Get rep's verified primary phone."""
        return await self.repo.get_verified_primary(user_id)

    async def get_phone_status(self, user_id: UUID) -> dict:
        """Get phone registration status for mobile app."""
        rep_phone = await self.repo.get_by_user(user_id)
        if not rep_phone:
            return {"has_phone": False, "is_verified": False, "phone_number": None}
        return {
            "has_phone": True,
            "is_verified": rep_phone.is_verified,
            "phone_number": self._mask_phone(rep_phone.phone_number),
        }

    async def update_push_token(self, user_id: UUID, expo_push_token: str) -> int:
        """Upsert the Expo push token for a rep. Returns rows written (1 = ok)."""
        affected = await self.repo.update_push_token(user_id, expo_push_token)
        logger.info("Updated push token", user_id=str(user_id), rows=affected)
        return affected

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number to E.164 format.

        International numbers must include their country code (e.g. +918887646909
        or 00918887646909); bare 10-digit numbers are assumed to be US.
        """
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if not phone.startswith("+"):
            if phone.startswith("1") and len(phone) == 11:
                phone = "+" + phone
            elif len(phone) == 10:
                phone = "+1" + phone
            else:
                phone = "+" + phone
        return phone

    @staticmethod
    def _generate_otp() -> str:
        """Generate a random 6-digit OTP."""
        return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """Mask a phone number for display: +1***-***-4567"""
        if len(phone) >= 4:
            return phone[:2] + "*" * (len(phone) - 6) + phone[-4:]
        return phone
