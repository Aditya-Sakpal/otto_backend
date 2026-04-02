"""
Twilio client.

Abstraction for Twilio telephony services used by masked communications:
- Voice call bridging (connect rep to homeowner via proxy number)
- SMS messaging (via proxy number)
- Phone number provisioning and management
- OTP verification for rep phone registration
- Webhook signature validation

Follows the same singleton pattern as ShoonyaClient.
"""
from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class TwilioClient:
    """
    Client for Twilio API.

    Platform-level credentials — one gomotto Twilio account,
    not per-company sub-accounts.
    """

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.system_number = settings.TWILIO_SYSTEM_NUMBER
        self.webhook_base_url = settings.API_URL.rstrip("/") if settings.API_URL else ""

        if not self.account_sid or not self.auth_token:
            logger.warning(
                "Twilio not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN missing) "
                "— masked comms features will be disabled"
            )
            self._enabled = False
        else:
            self._enabled = True
            self._client = Client(self.account_sid, self.auth_token)
            self._validator = RequestValidator(self.auth_token)
            logger.info("Twilio client initialized")

    def is_available(self) -> bool:
        """Check if Twilio is configured and available."""
        return self._enabled

    # ── Voice ─────────────────────────────────────────────────────────────

    def create_outbound_call(
        self,
        from_number: str,
        to_number: str,
        twiml_url: str,
        status_callback_url: str,
        record: bool = True,
    ) -> Dict[str, Any]:
        """
        Initiate an outbound bridged call.

        First leg: call the rep's phone from the proxy number.
        When rep answers, Twilio fetches twiml_url which returns
        <Dial> TwiML to bridge to the homeowner.
        """
        recording_kwargs = {}
        if record:
            recording_kwargs = {
                "record": True,
                "recording_status_callback": (
                    f"{self.webhook_base_url}/api/v1/webhooks/twilio/recording-status"
                ),
                "recording_status_callback_event": ["completed"],
            }

        call = self._client.calls.create(
            to=to_number,
            from_=from_number,
            url=twiml_url,
            status_callback=status_callback_url,
            status_callback_event=["completed"],
            **recording_kwargs,
        )
        logger.info(
            "Created outbound call",
            call_sid=call.sid,
            from_number=from_number,
            to_number=to_number,
        )
        return {"call_sid": call.sid, "status": call.status}

    # ── SMS ───────────────────────────────────────────────────────────────

    def send_sms(
        self,
        from_number: str,
        to_number: str,
        body: str,
        status_callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send SMS via a proxy number."""
        kwargs = {
            "to": to_number,
            "from_": from_number,
            "body": body,
        }
        if status_callback_url:
            kwargs["status_callback"] = status_callback_url

        msg = self._client.messages.create(**kwargs)
        logger.info(
            "Sent SMS",
            message_sid=msg.sid,
            from_number=from_number,
            to_number=to_number,
        )
        return {"message_sid": msg.sid, "status": msg.status}

    # ── OTP Verification ──────────────────────────────────────────────────

    def send_verification_sms(self, to_number: str, code: str) -> bool:
        """Send OTP verification SMS to a rep's personal phone."""
        if not self.system_number:
            logger.error("TWILIO_SYSTEM_NUMBER not configured — cannot send OTP")
            return False

        msg = self._client.messages.create(
            to=to_number,
            from_=self.system_number,
            body=f"Your gomotto verification code is: {code}. It expires in 10 minutes.",
        )
        return msg.status in ("queued", "sent")

    # ── Phone Number Management ───────────────────────────────────────────

    def provision_number(
        self, area_code: Optional[str] = None, country: str = "US"
    ) -> Dict[str, Any]:
        """
        Purchase a phone number from Twilio and configure webhook URLs.

        Returns dict with phone_number, sid, friendly_name.
        """
        search_params: Dict[str, Any] = {
            "voice_enabled": True,
            "sms_enabled": True,
        }
        if area_code:
            search_params["area_code"] = area_code

        available = (
            self._client.available_phone_numbers(country)
            .local.list(**search_params, limit=1)
        )
        if not available:
            raise RuntimeError(
                f"No available Twilio numbers for area_code={area_code}, country={country}"
            )

        number = self._client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            voice_url=f"{self.webhook_base_url}/api/v1/webhooks/twilio/inbound-call",
            voice_method="POST",
            sms_url=f"{self.webhook_base_url}/api/v1/webhooks/twilio/inbound-sms",
            sms_method="POST",
        )
        logger.info(
            "Provisioned Twilio number",
            phone_number=number.phone_number,
            sid=number.sid,
        )
        return {
            "phone_number": number.phone_number,
            "sid": number.sid,
            "friendly_name": number.friendly_name,
        }

    def release_number(self, twilio_sid: str) -> bool:
        """Release a phone number back to Twilio."""
        self._client.incoming_phone_numbers(twilio_sid).delete()
        logger.info("Released Twilio number", twilio_sid=twilio_sid)
        return True

    # ── Webhook Validation ────────────────────────────────────────────────

    def validate_request(self, url: str, params: dict, signature: str) -> bool:
        """Validate a Twilio webhook signature (X-Twilio-Signature header)."""
        return self._validator.validate(url, params, signature)


# Singleton
_twilio_client: Optional[TwilioClient] = None


def get_twilio_client() -> TwilioClient:
    """Get or create the global TwilioClient instance."""
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioClient()
    return _twilio_client
