"""
Call Tracking Metrics (CTM) integration service.

Handles CTM webhook processing:
- Call ingestion from CTM webhooks
- Contact card updates
- Audio file storage in S3
- Call analysis triggering
"""
import base64
import hmac
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.encryption import decrypt_api_key
from app.domain.models.call import Call
from app.domain.models.lead import Lead
from app.domain.enums import LeadStatus
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.domain.users.repository import UserRepository
from app.core.s3 import get_s3_service
from app.services.call_service import CallService
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.domain.models.pending_action import PendingAction
from app.domain.enums import PendingActionStatus, CallType

logger = get_logger(__name__)


class CTMService:
    """Service for CTM integration operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize CTM service.

        Args:
            session: Database session
        """
        self.session = session
        self.call_repo = CallRepository(session)
        self.contact_repo = ContactRepository(session)
        self.user_repo = UserRepository(session)
        self.appointment_repo = AppointmentRepository(session)

    @staticmethod
    def verify_ctm_signature(
        raw_body: bytes,
        signature_header: str,
        time_header: str,
        auth_token: str,
    ) -> bool:
        """
        Verify CTM webhook signature using HMAC-SHA1.

        CTM generates signatures as:
        signature = Base64.encode64(OpenSSL::HMAC.digest('sha1', auth_token, request_time + post_data))

        Args:
            raw_body: Raw request body bytes (post_data)
            signature_header: X-CTM-Signature header value
            time_header: X-CTM-Time header value (request_time)
            auth_token: CTM Secret Key (decrypted from company_integration.voip_api_encrypted_key)

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            if not signature_header or not time_header or not auth_token:
                logger.warning("Missing required headers or auth_token for CTM signature verification")
                return False

            # Concatenate request_time + post_data as strings
            # request_time is the exact string value of X-CTM-Time header
            # post_data is the exact string body of the webhook request
            message = time_header + raw_body.decode('utf-8')

            # Compute HMAC-SHA1
            digest = hmac.new(
                auth_token.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha1
            ).digest()

            # Base64 encode the HMAC digest
            expected_signature = base64.b64encode(digest).decode('utf-8')

            # Compare signatures (use constant-time comparison to prevent timing attacks)
            return hmac.compare_digest(expected_signature, signature_header)

        except Exception as e:
            logger.error(f"Error verifying CTM signature: {e}", exc_info=True)
            return False

    @staticmethod
    async def verify_api_key(access_key: str, secret_key: str) -> Optional[Dict[str, Any]]:
        """
        Verify CTM API credentials by calling the accounts endpoint.

        Args:
            access_key: CTM access key (used as Basic Auth username)
            secret_key: CTM secret key (used as Basic Auth password)

        Returns:
            Dictionary with secret_key, company_name, and company_id if valid, None otherwise
        """
        url = "https://api.calltrackingmetrics.com/api/v1/accounts.json"

        async with httpx.AsyncClient() as client:
            try:
                # CTM uses Basic Auth: access_key as username, secret_key as password
                response = await client.get(
                    url,
                    auth=(access_key.strip(), secret_key.strip()),
                    headers={"Accept": "application/json"},
                    timeout=10.0
                )

                # This will raise an exception for 4xx and 5xx responses
                response.raise_for_status()

                data = response.json()
                accounts = data.get("accounts", [])

                # Return the first account if available
                if accounts and len(accounts) > 0:
                    account = accounts[0]
                    return {
                        "secret_key": secret_key,  # Return secret_key for confirmation
                        "company_name": account.get("name"),
                        "company_id": account.get("id")
                    }
                else:
                    logger.warning("CTM accounts endpoint returned empty accounts list")
                    return None

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
                return None
            except (httpx.HTTPError, KeyError) as e:
                logger.error(f"Request failed: {str(e)}")
                return None

    async def process_webhook(
        self,
        payload: Dict[str, Any],
        company_id: UUID,
    ) -> Call:
        """
        Process Call Tracking Metrics (CTM) webhook payload.

        Handles both inbound and outbound calls:
        - For inbound: updates contactCard and call tables, stores audio in S3
        - For outbound: updates call tables, stores audio in S3

        Args:
            payload: CTM webhook payload
            company_id: Company/tenant ID

        Returns:
            Created or updated Call
        """
        try:
            # Extract call data from payload
            call_id_ctm = payload.get("id")  # CTM call ID
            direction = payload.get("direction", "").lower()
            status = payload.get("status", "").lower()
            call_status = (payload.get("call_status") or "").lower()

            # Determine missed vs answered / completed calls
            # CTM can send a variety of terminal statuses – we treat the
            # common "no answer", "missed", "busy" as missed calls but
            # still persist them, and only ignore truly non-final states.
            is_missed = status in ["no answer", "missed", "busy"]
            if not is_missed and status not in ["completed", "answered"]:
                logger.info(
                    f"Ignoring CTM webhook - call not completed",
                    ctm_call_id=call_id_ctm,
                    status=status,
                )
                raise ValueError(f"Call status '{status}' is not completed or answered")

            # Extract phone numbers
            if direction == "inbound":
                caller_phone = payload.get("caller_number_bare") or payload.get("caller_number")
                if caller_phone == "+":
                    caller_phone = "anonymous"
                # Handle "anonymous" or empty/plus-only numbers
                if not caller_phone or caller_phone == "+":
                    contact_phone = "anonymous"
                else:
                    contact_phone = caller_phone

            elif direction == "outbound":
                caller_phone = payload.get("tracking_number")  # Company's tracking number
                contact_phone = (
                    payload.get("contact_number")
                    or payload.get("dialed_number")
                    or payload.get("destination_number")
                    or payload.get("caller_number_bare")
                    or payload.get("caller_number")
                )

            else:
                raise ValueError(f"Unknown call direction: {direction}")

            if not contact_phone:
                raise ValueError("Contact phone number is required")

            # Extract contact information
            contact_name = payload.get("name") or payload.get("cnam")
            first_name = None
            last_name = None
            if contact_name:
                name_parts = contact_name.split(maxsplit=1)
                first_name = name_parts[0] if name_parts else None
                last_name = name_parts[1] if len(name_parts) > 1 else None

            # Extract user information (for outbound calls)
            handled_by_user_id = None
            agent_data = payload.get("agent")
            agent_email = agent_data.get("email") if isinstance(agent_data, dict) else payload.get("agent_email") if payload.get("agent_email") else None
            if agent_email:
                user_orm = await self.user_repo.get_by_email(agent_email)
                if user_orm:
                    handled_by_user_id = user_orm.id

            # Extract call metadata
            # Prefer talk_time when it's non-zero (actual conversation time),
            # otherwise fall back to CTM's duration which often includes ring time.
            duration_raw = payload.get("duration")
            talk_time = payload.get("talk_time")
            ring_time = payload.get("ring_time")
            hold_time = payload.get("hold_time")
            wait_time = payload.get("wait_time")
            duration = (
                talk_time
                if isinstance(talk_time, (int, float)) and talk_time > 0
                else duration_raw
            )
            transcript = payload.get("transcription_text")
            audio_url_ctm = payload.get("audio")
            called_at = payload.get("called_at")
            unix_time = payload.get("unix_time")

            # Parse called_at timestamp
            call_timestamp = None
            if unix_time:
                call_timestamp = datetime.fromtimestamp(unix_time)
            elif called_at:
                try:
                    # Try parsing CTM timestamp format: "2026-01-19 12:00 PM -05:00"
                    call_timestamp = datetime.strptime(called_at, "%Y-%m-%d %I:%M %p %z")
                except ValueError:
                    try:
                        call_timestamp = datetime.fromisoformat(called_at.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Could not parse called_at: {called_at}")

            # Find or create contact card (for both inbound and outbound calls)
            contact_card = None
            contact_card = await self.contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=contact_phone,
                first_name=first_name,
                last_name=last_name,
            )

            # Update contact card with additional info if available
            if contact_card:
                update_needed = False
                contact_updates = {}

                # Update address/location fields if provided
                street = payload.get("street")
                city = payload.get("city")
                state = payload.get("state")
                postal_code = payload.get("postal_code")
                country = payload.get("country")

                if street and not contact_card.address:
                    contact_updates["address"] = street
                    update_needed = True
                if city and not contact_card.city:
                    contact_updates["city"] = city
                    update_needed = True
                if state and not contact_card.state:
                    contact_updates["state"] = state
                    update_needed = True
                if postal_code and not contact_card.postal_code:
                    contact_updates["postal_code"] = postal_code
                    update_needed = True
                if country:
                    # Store country in extra_metadata since we don't have a direct column
                    if contact_card.extra_metadata is None:
                        contact_card.extra_metadata = {}
                    if "country" not in contact_card.extra_metadata:
                        contact_card.extra_metadata["country"] = country
                        update_needed = True

                if update_needed:
                    for key, value in contact_updates.items():
                        setattr(contact_card, key, value)
                    await self.contact_repo.update(contact_card.id, contact_card)

            # Stream audio to S3 if available
            s3_audio_url = None
            if audio_url_ctm:
                try:
                    s3_service = get_s3_service()
                    if s3_service:
                        # Generate S3 key: recordings/{contactId}/{messageId}.mp3
                        contact_id_str = str(contact_card.id) if contact_card else "unknown"
                        message_id = str(call_id_ctm)
                        s3_key = f"recordings/{contact_id_str}/{message_id}.mp3"

                        # Stream from CTM URL to S3
                        s3_audio_url = await s3_service.upload_from_url(
                            url=audio_url_ctm,
                            s3_key=s3_key,
                            content_type="audio/mpeg",
                            metadata={
                                "ctm_call_id": str(call_id_ctm),
                                "direction": direction,
                                "company_id": str(company_id),
                            },
                            bucket_type="audio",
                        )
                        logger.info(
                            "Audio streamed to S3",
                            ctm_call_id=call_id_ctm,
                            s3_url=s3_audio_url,
                        )
                    else:
                        logger.warning("S3 service not available, using CTM URL directly")
                        s3_audio_url = audio_url_ctm
                except Exception as e:
                    logger.error(f"Error streaming audio to S3: {e}", exc_info=True)
                    # Fallback to CTM URL if S3 upload fails
                    s3_audio_url = audio_url_ctm

            # Prepare call extra_metadata
            extra_metadata = {
                "ctm_call_id": call_id_ctm,
                "ctm_sid": payload.get("sid"),
                "direction": direction,
                "status": status,
                "call_status": call_status or payload.get("call_status"),
                "tracking_number": payload.get("tracking_number"),
                "tracking_label": payload.get("tracking_label"),
                "source": payload.get("source"),
                "medium": payload.get("medium"),
                "campaign": payload.get("campaign"),
                "keyword": payload.get("keyword"),
                "tags": payload.get("tag_list", []),
                "outcome_label": payload.get("outcome_label"),
                "total_cost": payload.get("total_cost"),
                # Duration / timing breakdown
                "duration": duration_raw,
                "talk_time": talk_time,
                "ring_time": ring_time,
                "hold_time": hold_time,
                "wait_time": wait_time,
                # Routing / queueing information
                "call_path": payload.get("call_path", []),
                "legs": payload.get("legs", []),
                # Caller / analytics context
                "is_new_caller": payload.get("is_new_caller"),
                "day": payload.get("day"),
                "month": payload.get("month"),
                "hour": payload.get("hour"),
                "location": payload.get("location"),
                "country": payload.get("country"),
                "agent": agent_data,
                # Preserve the full raw payload for debugging / future use
                "ctm_raw_payload": payload,
            }

            # Create or update call record
            # Check if call already exists by CTM call ID
            existing_calls = await self.call_repo.get_all(
                filters={"company_id": company_id},
            )
            existing_call = None
            for call in existing_calls:
                if call.extra_metadata and call.extra_metadata.get("ctm_call_id") == call_id_ctm:
                    existing_call = call
                    break

            is_new_call = False

            if existing_call:
                # Update existing call
                existing_call.audio_url = s3_audio_url or existing_call.audio_url
                existing_call.duration_seconds = duration or existing_call.duration_seconds
                existing_call.transcript = transcript or existing_call.transcript
                existing_call.handled_by_user_id = handled_by_user_id or existing_call.handled_by_user_id
                existing_call.missed_call = is_missed
                if is_missed:
                    existing_call.call_type = CallType.MISSED_CALL.value
                if contact_card:
                    existing_call.contact_card_id = contact_card.id
                if not existing_call.lead_source and payload.get("source"):
                    existing_call.lead_source = payload["source"]
                existing_call.extra_metadata = {**(existing_call.extra_metadata or {}), **extra_metadata}

                call = await self.call_repo.update(existing_call.id, existing_call)
                logger.info("Call updated", call_id=str(call.id), ctm_call_id=call_id_ctm)

                # Also update appointment's audio_url if this call is linked to an appointment
                if s3_audio_url and call.audio_url:
                    appointment = await self.appointment_repo.get_by_interaction_id(call.id)
                    if appointment:
                        appointment.audio_url = call.audio_url
                        appointment.mark_updated()
                        await self.appointment_repo.update(appointment.id, appointment)
                        logger.info(
                            f"Updated appointment {appointment.id} with audio_url from CTM call {call.id}"
                        )
            else:
                # Create new call
                call = Call(
                    company_id=company_id,
                    contact_card_id=contact_card.id if contact_card else None,
                    phone_number=contact_phone,
                    audio_url=s3_audio_url,
                    duration_seconds=duration,
                    transcript=transcript,
                    handled_by_user_id=handled_by_user_id,
                    call_type=CallType.MISSED_CALL if is_missed else None,
                    missed_call=is_missed,
                    interaction_type="call",
                    lead_source=payload.get("source") or None,
                    extra_metadata=extra_metadata,
                )
                call = await self.call_repo.create(call)
                is_new_call = True
                logger.info("Call created", call_id=str(call.id), ctm_call_id=call_id_ctm)

            # Find or create lead for this contact card
            if contact_card:
                try:
                    lead_repo = LeadRepository(self.session)
                    existing_leads = await lead_repo.get_all(
                        filters={"contact_card_id": contact_card.id, "company_id": company_id}
                    )
                    lead = existing_leads[0] if existing_leads else None

                    if not lead:
                        lead = Lead(
                            company_id=company_id,
                            contact_card_id=contact_card.id,
                            status=LeadStatus.NEW,
                            lead_source=payload.get("source") or None,
                        )
                        lead = await lead_repo.create(lead)
                        logger.info("Lead created", lead_id=str(lead.id), contact_card_id=str(contact_card.id))

                    if lead and not call.lead_id:
                        call.lead_id = lead.id
                        call = await self.call_repo.update(call.id, call)
                except Exception as e:
                    logger.error(f"Failed to find or create lead for contact {contact_card.id}: {e}")

            # Update contact card with last call metadata (for inbound calls)
            if direction == "inbound" and contact_card:
                try:
                    if not contact_card.extra_metadata:
                        contact_card.extra_metadata = {}

                    contact_card.extra_metadata["last_call_id"] = str(call.id)
                    contact_card.extra_metadata["last_call_date"] = (
                        call_timestamp.isoformat() if call_timestamp else datetime.utcnow().isoformat()
                    )
                    contact_card.extra_metadata["last_call_direction"] = direction
                    contact_card.extra_metadata["last_call_recording_url"] = s3_audio_url
                    if handled_by_user_id:
                        contact_card.extra_metadata["last_call_handled_by"] = str(handled_by_user_id)

                    await self.contact_repo.update(contact_card.id, contact_card)
                    logger.info(f"Updated contact card {contact_card.id} with last call metadata")
                except Exception as e:
                    logger.exception(f"Failed to update contact card metadata: {e}")

            # Trigger analysis only for NEW calls (skip re-fired webhooks to avoid 409 from Shunya)
            if is_new_call and s3_audio_url and not call.missed_call:
                try:
                    call_service = CallService(self.session)
                    await call_service.trigger_analysis(call.id)
                except Exception as e:
                    logger.error(f"Failed to trigger analysis for call {call.id}: {e}")
                    # Don't raise - analysis is non-critical

            return call

        except Exception as e:
            logger.error(f"Error processing CTM webhook: {e}", exc_info=True)
            raise e
