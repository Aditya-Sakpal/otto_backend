"""
Twilio SMS executor.

Sends follow-up SMS messages to homeowners.
"""
from __future__ import annotations

import asyncio

from twilio.rest import Client as TwilioClient

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)


class TwilioSMSSender:
    """Send SMS via Twilio."""

    def __init__(self, account_sid: str, auth_token: str):
        self._client = TwilioClient(account_sid, auth_token)

    async def send(
        self,
        to: str,
        from_: str,
        body: str,
        source_metadata: dict | None = None,
    ) -> str | None:
        """
        Send an SMS message.

        Args:
            to: Recipient phone (E.164)
            from_: Sender phone (E.164)
            body: SMS text
            source_metadata: Optional metadata for masked comms integration.
                When the comms bridge is built, this dict is attached to the
                masked_communications INSERT. Structure:
                {source, follow_up_log_id, attempt_number, queue_type}

        Returns:
            Twilio message SID on success, None on failure.
        """
        if source_metadata:
            logger.debug(
                "SMS source_metadata attached",
                metadata_keys=list(source_metadata.keys()),
            )

        try:
            message = await asyncio.to_thread(
                self._client.messages.create,
                body=body,
                from_=from_,
                to=to,
            )
            logger.info("SMS sent", sid=message.sid, to=to)
            return message.sid
        except Exception as e:
            logger.error("SMS send failed", error=str(e), to=to)
            return None
