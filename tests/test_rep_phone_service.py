"""
Tests for RepPhoneService — OTP registration and verification flow.

Uses pytest-asyncio with mocked database session and Twilio client.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.rep_phone_service import (
    RepPhoneService,
    RepPhoneNotRegisteredError,
    OTP_LENGTH,
    OTP_EXPIRY_MINUTES,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_twilio():
    """Mock TwilioClient."""
    twilio = MagicMock()
    twilio.is_available.return_value = True
    twilio.send_verification_sms.return_value = True
    return twilio


@pytest.fixture
def service(mock_db, mock_twilio):
    """Create RepPhoneService with mocked deps."""
    with patch("app.services.rep_phone_service.get_twilio_client", return_value=mock_twilio):
        svc = RepPhoneService(mock_db)
        svc.repo = AsyncMock()
        return svc


# ── Phone Normalization ──────────────────────────────────────────────────────


class TestNormalizePhone:
    def test_ten_digit(self):
        assert RepPhoneService._normalize_phone("5551234567") == "+15551234567"

    def test_eleven_digit_with_country_code(self):
        assert RepPhoneService._normalize_phone("15551234567") == "+15551234567"

    def test_already_e164(self):
        assert RepPhoneService._normalize_phone("+15551234567") == "+15551234567"

    def test_strips_formatting(self):
        assert RepPhoneService._normalize_phone("(555) 123-4567") == "+15551234567"

    def test_strips_spaces(self):
        assert RepPhoneService._normalize_phone("555 123 4567") == "+15551234567"


# ── OTP Generation ───────────────────────────────────────────────────────────


class TestGenerateOTP:
    def test_length(self):
        otp = RepPhoneService._generate_otp()
        assert len(otp) == OTP_LENGTH

    def test_all_digits(self):
        otp = RepPhoneService._generate_otp()
        assert otp.isdigit()

    def test_randomness(self):
        """Multiple calls should produce different codes (probabilistic)."""
        codes = {RepPhoneService._generate_otp() for _ in range(50)}
        assert len(codes) > 1


# ── Phone Masking ────────────────────────────────────────────────────────────


class TestMaskPhone:
    def test_standard_e164(self):
        masked = RepPhoneService._mask_phone("+15551234567")
        assert masked.endswith("4567")
        assert "*" in masked
        assert "555123" not in masked

    def test_short_number(self):
        masked = RepPhoneService._mask_phone("+1")
        assert masked == "+1"


# ── register_phone ───────────────────────────────────────────────────────────


class TestRegisterPhone:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_twilio):
        user_id = uuid4()
        service.repo.upsert_phone = AsyncMock()

        result = await service.register_phone(user_id, "5551234567")

        assert result["status"] == "otp_sent"
        assert "phone_masked" in result
        service.repo.upsert_phone.assert_awaited_once()
        mock_twilio.send_verification_sms.assert_called_once()

    @pytest.mark.asyncio
    async def test_normalizes_phone(self, service):
        user_id = uuid4()
        service.repo.upsert_phone = AsyncMock()

        await service.register_phone(user_id, "(555) 123-4567")

        call_args = service.repo.upsert_phone.call_args
        assert call_args.kwargs["phone_number"] == "+15551234567"

    @pytest.mark.asyncio
    async def test_twilio_unavailable_logs_warning(self, service, mock_twilio):
        """When Twilio is not available, still creates record but doesn't send SMS."""
        mock_twilio.is_available.return_value = False
        user_id = uuid4()
        service.repo.upsert_phone = AsyncMock()

        result = await service.register_phone(user_id, "5551234567")

        assert result["status"] == "otp_sent"
        mock_twilio.send_verification_sms.assert_not_called()

    @pytest.mark.asyncio
    async def test_twilio_send_failure(self, service, mock_twilio):
        mock_twilio.send_verification_sms.return_value = False
        user_id = uuid4()
        service.repo.upsert_phone = AsyncMock()

        result = await service.register_phone(user_id, "5551234567")

        assert result["status"] == "error"


# ── verify_phone ─────────────────────────────────────────────────────────────


class TestVerifyPhone:
    @pytest.mark.asyncio
    async def test_success(self, service):
        user_id = uuid4()
        mock_phone = MagicMock()
        mock_phone.phone_number = "+15551234567"
        mock_phone.verification_code = "123456"
        mock_phone.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)
        service.repo.mark_verified = AsyncMock(return_value=mock_phone)

        result = await service.verify_phone(user_id, "5551234567", "123456")

        assert result == mock_phone
        service.repo.mark_verified.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_registration_found(self, service):
        user_id = uuid4()
        service.repo.get_by_user = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="No phone registration found"):
            await service.verify_phone(user_id, "5551234567", "123456")

    @pytest.mark.asyncio
    async def test_phone_mismatch(self, service):
        user_id = uuid4()
        mock_phone = MagicMock()
        mock_phone.phone_number = "+19998887777"
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        with pytest.raises(ValueError, match="does not match"):
            await service.verify_phone(user_id, "5551234567", "123456")

    @pytest.mark.asyncio
    async def test_expired_code(self, service):
        user_id = uuid4()
        mock_phone = MagicMock()
        mock_phone.phone_number = "+15551234567"
        mock_phone.verification_code = "123456"
        mock_phone.verification_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        with pytest.raises(ValueError, match="expired"):
            await service.verify_phone(user_id, "5551234567", "123456")

    @pytest.mark.asyncio
    async def test_wrong_code(self, service):
        user_id = uuid4()
        mock_phone = MagicMock()
        mock_phone.phone_number = "+15551234567"
        mock_phone.verification_code = "123456"
        mock_phone.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        with pytest.raises(ValueError, match="Invalid verification code"):
            await service.verify_phone(user_id, "5551234567", "999999")

    @pytest.mark.asyncio
    async def test_no_pending_verification(self, service):
        user_id = uuid4()
        mock_phone = MagicMock()
        mock_phone.phone_number = "+15551234567"
        mock_phone.verification_code = None
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        with pytest.raises(ValueError, match="No pending verification"):
            await service.verify_phone(user_id, "5551234567", "123456")


# ── get_phone_status ─────────────────────────────────────────────────────────


class TestGetPhoneStatus:
    @pytest.mark.asyncio
    async def test_no_phone(self, service):
        service.repo.get_by_user = AsyncMock(return_value=None)
        result = await service.get_phone_status(uuid4())
        assert result == {"has_phone": False, "is_verified": False, "phone_number": None}

    @pytest.mark.asyncio
    async def test_verified_phone(self, service):
        mock_phone = MagicMock()
        mock_phone.is_verified = True
        mock_phone.phone_number = "+15551234567"
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        result = await service.get_phone_status(uuid4())

        assert result["has_phone"] is True
        assert result["is_verified"] is True
        assert "4567" in result["phone_number"]  # Masked but last 4 visible

    @pytest.mark.asyncio
    async def test_unverified_phone(self, service):
        mock_phone = MagicMock()
        mock_phone.is_verified = False
        mock_phone.phone_number = "+15551234567"
        service.repo.get_by_user = AsyncMock(return_value=mock_phone)

        result = await service.get_phone_status(uuid4())

        assert result["has_phone"] is True
        assert result["is_verified"] is False


# ── update_push_token ────────────────────────────────────────────────────────


class TestUpdatePushToken:
    @pytest.mark.asyncio
    async def test_updates_token(self, service):
        user_id = uuid4()
        service.repo.update_push_token = AsyncMock()

        await service.update_push_token(user_id, "ExponentPushToken[abc123]")

        service.repo.update_push_token.assert_awaited_once_with(
            user_id, "ExponentPushToken[abc123]"
        )
