"""
GoHighLevel (GHL) integration service.

Handles API calls to GHL for contacts, recordings, and other resources.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import base64
import re

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@dataclass(frozen=True)
class ContactInfo:
    """GHL contact information."""
    contact_id: str
    full_name: Optional[str]
    phone: Optional[str]


@dataclass(frozen=True)
class RecordingResult:
    """GHL recording result."""
    content_type: Optional[str]
    filename: Optional[str]
    audio_bytes: bytes


class GHLService:
    """Service for GoHighLevel API interactions."""

    BASE_URL = "https://services.leadconnectorhq.com"

    def __init__(self, bearer_token: Optional[str] = None):
        """
        Initialize GHL service.

        Args:
            bearer_token: GHL bearer token. If None, uses GHL_BEARER_TOKEN from settings.
        """
        self.bearer_token = bearer_token or getattr(settings, 'GHL_BEARER_TOKEN', None)
        if not self.bearer_token:
            logger.warning("GHL bearer token not configured. GHL API calls will fail.")

    @staticmethod
    def extract_event_payload(body: Dict[str, Any]) -> Dict[str, Any]:
        """
        GHL webhooks often come as an envelope:
        { "type": "...", "timestamp": "...", "webhookId": "...", "data": { ... } }
        but the InboundMessage page shows the message schema itself. We support both.
        """
        if isinstance(body.get("data"), dict):
            return body["data"]
        return body

    @staticmethod
    def verify_ghl_signature(raw_body: bytes, signature_b64: str) -> bool:
        """
        Verify GHL webhook signature using public key from environment.

        According to GHL documentation:
        - The signature is in the x-wh-signature header as base64
        - The payload should be the raw JSON string
        - Verification uses SHA256 with RSA PKCS1v15 padding

        Args:
            raw_body: Raw request body bytes (JSON string)
            signature_b64: Base64-encoded signature from x-wh-signature header

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Get public key from environment
            public_key_pem = settings.GHL_PUBLIC_KEY
            if not public_key_pem:
                logger.warning("GHL_PUBLIC_KEY not configured, skipping signature verification")
                return False

            # Clean and format the public key
            # Handle cases where the key might be:
            # 1. Already in PEM format with BEGIN/END markers
            # 2. Just the base64 content (needs wrapping)
            # 3. Has escaped newlines (\n) that need to be converted
            public_key_pem = public_key_pem.strip()

            # Replace escaped newlines with actual newlines
            public_key_pem = public_key_pem.replace("\\n", "\n")

            # If it doesn't start with BEGIN marker, it's just the key content
            if not public_key_pem.startswith("-----BEGIN PUBLIC KEY-----"):
                # Remove any existing whitespace/newlines and wrap properly
                # The key content should be 64 chars per line for proper PEM format
                key_content = public_key_pem.replace("\n", "").replace(" ", "").replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "")
                # Format with proper line breaks (64 chars per line)
                formatted_key = "\n".join([key_content[i:i+64] for i in range(0, len(key_content), 64)])
                public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{formatted_key}\n-----END PUBLIC KEY-----"
            else:
                # Already has BEGIN/END markers, but ensure proper formatting
                # Extract the key content and reformat if needed
                lines = public_key_pem.split("\n")
                key_lines = [line for line in lines if line and not line.startswith("-----")]
                if key_lines:
                    # Check if lines are properly formatted (64 chars)
                    key_content = "".join(key_lines).replace(" ", "")
                    if len(key_lines[0]) != 64:
                        # Reformat with proper line breaks
                        formatted_key = "\n".join([key_content[i:i+64] for i in range(0, len(key_content), 64)])
                        public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{formatted_key}\n-----END PUBLIC KEY-----"

            # Load public key
            try:
                public_key = serialization.load_pem_public_key(
                    public_key_pem.encode('utf-8')
                )
            except Exception as key_error:
                logger.error(f"Error loading GHL public key: {key_error}")
                logger.debug(f"Public key PEM (first 100 chars): {public_key_pem[:100]}")
                return False

            # Clean and decode the signature
            # Remove any whitespace from the base64 string
            signature_b64_clean = signature_b64.strip().replace(" ", "").replace("\n", "").replace("\r", "")

            try:
                sig_bytes = base64.b64decode(signature_b64_clean, validate=True)
            except Exception as decode_error:
                logger.error(f"Error decoding GHL signature (base64): {decode_error}")
                logger.debug(f"Signature (first 50 chars): {signature_b64_clean[:50]}")
                return False

            # Verify signature
            # According to GHL docs: SHA256 hash of the payload, signed with RSA
            public_key.verify(
                sig_bytes,
                raw_body,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.error(f"Error verifying GHL signature: {e}", exc_info=True)
            return False

    async def get_contact_info(self, contact_id: str) -> Optional[ContactInfo]:
        """
        Fetch contact information from GHL.

        Calls GHL Get Contact:
          GET https://services.leadconnectorhq.com/contacts/:contactId

        Args:
            contact_id: GHL contact ID

        Returns:
            ContactInfo with contact details, or None if bearer token is not configured or API call fails
        """
        if not self.bearer_token:
            logger.warning(f"GHL bearer token not configured, cannot fetch contact info for {contact_id}")
            return None

        url = f"{self.BASE_URL}/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Version": "2021-07-28",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()

            # Some GHL endpoints return { "contact": {...} }, others return the object directly.
            contact = data.get("contact") if isinstance(data, dict) else None
            if not isinstance(contact, dict):
                contact = data if isinstance(data, dict) else {}

            # Name fields present in GHL contact records: firstName, lastName, name
            first = (contact.get("firstName") or "").strip()
            last = (contact.get("lastName") or "").strip()
            name = (contact.get("name") or "").strip()

            if first and last:
                full_name = f"{first} {last}".strip()
            elif name:
                full_name = name
            else:
                full_name = None

            phone = (contact.get("phone") or "").strip() or None

            return ContactInfo(contact_id=contact_id, full_name=full_name, phone=phone)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(f"GHL API returned 401 Unauthorized for contact {contact_id}. Bearer token may be invalid or expired.")
            else:
                logger.error(f"GHL API error fetching contact {contact_id}: {e.response.status_code} {e.response.reason_phrase}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching contact info for {contact_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching contact info for {contact_id}: {e}", exc_info=True)
            return None

    def _parse_filename(self, content_disposition: Optional[str]) -> Optional[str]:
        """Parse filename from Content-Disposition header."""
        if not content_disposition:
            return None
        # Example: Attachment; filename=audio.wav
        m = re.search(r'filename="?([^"]+)"?', content_disposition, flags=re.IGNORECASE)
        return m.group(1) if m else None

    async def get_message_recording(
        self,
        location_id: str,
        message_id: str,
    ) -> RecordingResult:
        """
        Fetch recording for a message from GHL.

        GHL Get Recording by Message ID:
          GET https://services.leadconnectorhq.com/conversations/messages/:messageId/locations/:locationId/recording

        Returns audio bytes (WAV) with Content-Type audio/x-wav and Content-Disposition filename header.

        Args:
            location_id: GHL location ID
            message_id: GHL message ID

        Returns:
            RecordingResult with audio bytes and metadata

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        if not self.bearer_token:
            raise ValueError("GHL bearer token not configured")

        url = (
            f"{self.BASE_URL}"
            f"/conversations/messages/{message_id}/locations/{location_id}/recording"
        )
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "*/*",
            "Version": "2021-07-28",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type")
            filename = self._parse_filename(resp.headers.get("content-disposition"))
            audio_bytes = resp.content  # recording bytes

        return RecordingResult(
            content_type=content_type,
            filename=filename,
            audio_bytes=audio_bytes
        )

    @staticmethod
    async def verify_api_key(api_key: str, location_id: str):
        url = f"https://services.leadconnectorhq.com/locations/{location_id}"
        # Ensure there are no extra spaces in the API Key
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Version": "2021-07-28",
            "Accept": "application/json"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)

                # This will raise an exception for 4xx and 5xx responses
                response.raise_for_status()

                data = response.json()
                # GHL API returns { "location": {...} } or the location object directly
                location = data.get("location") if isinstance(data, dict) else None
                if not isinstance(location, dict):
                    location = data if isinstance(data, dict) else None

                if location:
                    return {
                        "location_id": location.get("id"),
                        "company_id": location.get("companyId"),
                        "company_name": location.get("name")
                    }
                else:
                    return None

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
                return None
            except (httpx.HTTPError, KeyError) as e:
                logger.error(f"Request failed: {str(e)}")
                return None

    async def get_appointment_info(self, event_id: str) -> Dict[str, Any]:
        """
        Fetch appointment information from GHL.

        Calls GHL Get Appointment:
          GET https://services.leadconnectorhq.com/calendars/events/appointments/:eventId

        Args:
            event_id: GHL event/appointment ID

        Returns:
            Dict with appointment details from the "event" key in the response, or empty dict if bearer token is not configured or API call fails
        """
        if not self.bearer_token:
            logger.warning(f"GHL bearer token not configured, cannot fetch appointment info for {event_id}")
            return {}

        url = f"{self.BASE_URL}/calendars/events/appointments/{event_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Version": "2021-07-28",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()

            # GHL returns { "event": {...} } according to the API documentation
            event = data.get("event") if isinstance(data, dict) else None
            if not isinstance(event, dict):
                event = data if isinstance(data, dict) else {}

            return event
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(f"GHL API returned 401 Unauthorized for appointment {event_id}. Bearer token may be invalid or expired.")
            else:
                logger.error(f"GHL API error fetching appointment {event_id}: {e.response.status_code} {e.response.reason_phrase}")
            return {}
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching appointment info for {event_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching appointment info for {event_id}: {e}", exc_info=True)
            return {}

    async def get_opportunity_info(self, opportunity_id: str) -> Dict[str, Any]:
        """
        Fetch opportunity/lead information from GHL.

        Calls GHL Get Opportunity:
          GET https://services.leadconnectorhq.com/opportunities/:id

        Args:
            opportunity_id: GHL opportunity ID

        Returns:
            Dict with opportunity details from the "opportunity" key in the response, or empty dict if bearer token is not configured or API call fails
        """
        if not self.bearer_token:
            logger.warning(f"GHL bearer token not configured, cannot fetch opportunity info for {opportunity_id}")
            return {}

        url = f"{self.BASE_URL}/opportunities/{opportunity_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Version": "2021-07-28",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()

            # GHL returns { "opportunity": {...} } according to the API documentation
            opportunity = data.get("opportunity") if isinstance(data, dict) else None
            if not isinstance(opportunity, dict):
                opportunity = data if isinstance(data, dict) else {}

            return opportunity
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(f"GHL API returned 401 Unauthorized for opportunity {opportunity_id}. Bearer token may be invalid or expired.")
            else:
                logger.error(f"GHL API error fetching opportunity {opportunity_id}: {e.response.status_code} {e.response.reason_phrase}")
            return {}
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching opportunity info for {opportunity_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching opportunity info for {opportunity_id}: {e}", exc_info=True)
            return {}

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch user/rep information from GHL.

        Calls GHL Get User:
          GET https://services.leadconnectorhq.com/users/:userId

        Args:
            user_id: GHL user ID

        Returns:
            Dict with user details (the API returns the user object directly), or empty dict if bearer token is not configured or API call fails
        """
        if not self.bearer_token:
            logger.warning(f"GHL bearer token not configured, cannot fetch user info for {user_id}")
            return {}

        url = f"{self.BASE_URL}/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Version": "2021-07-28",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()

            # GHL returns the user object directly according to the API documentation
            # (not wrapped in a "user" key)
            return data if isinstance(data, dict) else {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(f"GHL API returned 401 Unauthorized for user {user_id}. Bearer token may be invalid or expired.")
            else:
                logger.error(f"GHL API error fetching user {user_id}: {e.response.status_code} {e.response.reason_phrase}")
            return {}
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching user info for {user_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching user info for {user_id}: {e}", exc_info=True)
            return {}

    async def update_lead_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Update lead/opportunity event.

        Args:
            event: GHL event (OpportunityUpdate, OpportunityStatusUpdate, etc.)
            db_session: Database session
            company_id: Company UUID
        """
        from uuid import UUID
        from datetime import datetime
        from app.infrastructure.repositories.lead import LeadRepository
        from app.infrastructure.repositories.contact import ContactRepository
        from app.domain.users.repository import UserRepository
        from app.domain.models.lead import Lead
        from app.domain.enums import LeadStatus, DealStatus

        try:
            location_id = event.get("locationId")
            opportunity_id = event.get("id")
            contact_id = event.get("contactId")

            if not opportunity_id or not contact_id:
                logger.warning("Missing opportunity_id or contact_id in event", event=event)
                return

            # Get full opportunity details
            opp_data = await self.get_opportunity_info(opportunity_id)

            # Get contact info to find/create contact card
            contact_info = await self.get_contact_info(contact_id)
            phone = contact_info.phone if contact_info else None
            if not phone:
                # Try to get phone from opportunity data or event
                phone = opp_data.get("contact", {}).get("phone") if isinstance(opp_data, dict) else None
                if not phone:
                    phone = event.get("contactId")  # Sometimes contactId might be phone-like, but unlikely
                if not phone:
                    logger.warning(f"No phone number available for contact {contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
                    return

            contact_repo = ContactRepository(db_session)
            full_name = contact_info.full_name if contact_info else None
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=phone,
                email=None,  # Could fetch from contact_info if available
                first_name=full_name.split()[0] if full_name else None,
                last_name=" ".join(full_name.split()[1:]) if full_name and len(full_name.split()) > 1 else None,
            )

            # Find existing lead by GHL opportunity ID in extra_metadata
            lead_repo = LeadRepository(db_session)
            from sqlalchemy import select
            from app.infrastructure.database.models.lead import LeadORM

            # Search for existing lead by GHL opportunity ID in metadata
            existing_lead = None
            all_leads = await lead_repo.get_all(
                filters={"company_id": company_id, "contact_card_id": contact_card.id}
            )
            for lead in all_leads:
                if lead.extra_metadata and lead.extra_metadata.get("ghl_opportunity_id") == opportunity_id:
                    existing_lead = lead
                    break

            # Map GHL status to our LeadStatus
            ghl_status = opp_data.get("status", "open")
            if ghl_status == "won":
                status = LeadStatus.CLOSED_WON
                deal_status = DealStatus.WON
            elif ghl_status == "lost":
                status = LeadStatus.CLOSED_LOST
                deal_status = DealStatus.LOST
            else:
                status = LeadStatus.NEW
                deal_status = None

            # Get assigned user if available
            assigned_rep_id = None
            assigned_to = opp_data.get("assignedTo")
            if assigned_to:
                try:
                    user_info = await self.get_user_info(assigned_to)
                    if user_info:
                        # Map GHL user to our user by email
                        ghl_user_email = user_info.get("email")
                        if ghl_user_email:
                            user_repo = UserRepository(db_session)
                            user_orm = await user_repo.get_by_email(ghl_user_email)
                            if user_orm:
                                assigned_rep_id = user_orm.id
                                logger.info(f"Mapped GHL user {assigned_to} ({ghl_user_email}) to our user {assigned_rep_id}")
                            else:
                                logger.warning(f"GHL user {assigned_to} has email {ghl_user_email} but no matching user found in our database")
                        else:
                            logger.warning(f"GHL user {assigned_to} has no email field, cannot map to our user")
                except Exception as e:
                    logger.warning(f"Failed to fetch user {assigned_to}: {e}")

            # Prepare lead data
            lead_data = {
                "company_id": company_id,
                "contact_card_id": contact_card.id,
                "status": status.value,
                "deal_status": deal_status.value if deal_status else None,
                "assigned_rep_id": assigned_rep_id,
                "deal_size": opp_data.get("monetaryValue"),
                "extra_metadata": {
                    "ghl_opportunity_id": opportunity_id,
                    "ghl_contact_id": contact_id,
                    "ghl_pipeline_id": opp_data.get("pipelineId"),
                    "ghl_pipeline_stage_id": opp_data.get("pipelineStageId"),
                    "ghl_source": opp_data.get("source"),
                    "ghl_assigned_to": opp_data.get("assignedTo"),
                },
            }

            # Update existing lead or create new one
            if existing_lead:
                # Update existing lead
                for key, value in lead_data.items():
                    if key != "company_id" and key != "contact_card_id":  # Don't update these
                        setattr(existing_lead, key, value)
                await lead_repo.update(existing_lead.id, existing_lead)
            else:
                # Create new lead
                lead = Lead(**lead_data)
                await lead_repo.create(lead)

            logger.info(f"Updated lead from GHL opportunity {opportunity_id}")

        except Exception as e:
            logger.error(f"Error updating lead event: {e}", exc_info=True)
            raise

    async def update_contact_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Update contact event.

        Args:
            event: GHL event (ContactUpdate, ContactTagUpdate)
            db_session: Database session
            company_id: Company UUID
        """
        from app.infrastructure.repositories.contact import ContactRepository
        from app.domain.models.contact import ContactCard

        try:
            contact_id = event.get("id")
            if not contact_id:
                logger.warning("Missing contact_id in event", event=event)
                return

            # Get full contact details from GHL API (if bearer token is configured)
            full_contact_data = {}
            contact_info = None
            if self.bearer_token:
                try:
                    contact_info = await self.get_contact_info(contact_id)

                    # Get full contact details from GHL API
                    url = f"{self.BASE_URL}/contacts/{contact_id}"
                    headers = {
                        "Authorization": f"Bearer {self.bearer_token}",
                        "Accept": "application/json",
                        "Version": "2021-07-28",
                    }
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        try:
                            resp = await client.get(url, headers=headers)
                            resp.raise_for_status()
                            data = resp.json()
                            full_contact_data = data.get("contact") or data
                        except httpx.HTTPStatusError as e:
                            if e.response.status_code == 401:
                                logger.warning(f"GHL API returned 401 Unauthorized for contact {contact_id}. Bearer token may be invalid or expired.")
                            else:
                                logger.warning(f"GHL API error fetching full contact data for {contact_id}: {e.response.status_code}")
                        except httpx.HTTPError:
                            pass
                except Exception as e:
                    logger.warning(f"Error fetching contact info from GHL API for {contact_id}: {e}. Continuing with webhook payload data.")

            # Extract phone number - prefer from API, fallback to event payload
            phone = None
            if contact_info and contact_info.phone:
                phone = contact_info.phone
            elif full_contact_data.get("phone"):
                phone = full_contact_data.get("phone")
            elif event.get("phone"):
                phone = event.get("phone")

            if not phone:
                logger.warning(f"No phone number available for contact {contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
                return

            contact_repo = ContactRepository(db_session)

            # Parse name - prefer from API, fallback to event payload
            first_name = full_contact_data.get("firstName") or event.get("firstName")
            if not first_name and contact_info and contact_info.full_name:
                name_parts = contact_info.full_name.split()
                first_name = name_parts[0] if name_parts else None

            last_name = full_contact_data.get("lastName") or event.get("lastName")
            if not last_name and contact_info and contact_info.full_name:
                name_parts = contact_info.full_name.split()
                last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None

            # Update or create contact
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=phone,
                email=full_contact_data.get("email") or event.get("email"),
                first_name=first_name,
                last_name=last_name,
            )

            # Update additional fields if available
            update_needed = False
            if full_contact_data.get("address1") and not contact_card.address:
                contact_card.address = full_contact_data.get("address1")
                update_needed = True
            if full_contact_data.get("city") and not contact_card.city:
                contact_card.city = full_contact_data.get("city")
                update_needed = True
            if full_contact_data.get("state") and not contact_card.state:
                contact_card.state = full_contact_data.get("state")
                update_needed = True
            if full_contact_data.get("postalCode") and not contact_card.postal_code:
                contact_card.postal_code = full_contact_data.get("postalCode")
                update_needed = True

            # Update extra_metadata with GHL contact ID
            if not contact_card.extra_metadata:
                contact_card.extra_metadata = {}
            contact_card.extra_metadata["ghl_contact_id"] = contact_id
            if full_contact_data.get("tags"):
                contact_card.extra_metadata["ghl_tags"] = full_contact_data.get("tags")

            if update_needed or "ghl_contact_id" not in contact_card.extra_metadata:
                await contact_repo.update(contact_card.id, contact_card)

            logger.info(f"Updated contact from GHL contact {contact_id}")

        except Exception as e:
            logger.error(f"Error updating contact event: {e}", exc_info=True)
            raise

    async def update_appointment_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Update appointment event.

        Args:
            event: GHL event (AppointmentUpdate)
            db_session: Database session
            company_id: Company UUID
        """
        from uuid import UUID
        from datetime import datetime
        from app.infrastructure.repositories.appointment import AppointmentRepository
        from app.infrastructure.repositories.contact import ContactRepository
        from app.infrastructure.repositories.lead import LeadRepository
        from app.domain.users.repository import UserRepository
        from app.domain.models.appointment import Appointment

        try:
            location_id = event.get("locationId")
            appointment_data = event.get("appointment") or event
            appointment_id = appointment_data.get("id")
            contact_id = appointment_data.get("contactId")

            if not appointment_id or not contact_id:
                logger.warning("Missing appointment_id or contact_id in event", event=event)
                return

            # Get full appointment details
            full_appt_data = await self.get_appointment_info(appointment_id)

            # Get contact info
            contact_info = await self.get_contact_info(contact_id)
            phone = contact_info.phone if contact_info else None
            if not phone:
                # Try to get phone from appointment data or event
                phone = full_appt_data.get("contact", {}).get("phone") if isinstance(full_appt_data, dict) else None
                if not phone:
                    phone = appointment_data.get("contact", {}).get("phone") if isinstance(appointment_data, dict) else None
                if not phone:
                    logger.warning(f"No phone number available for contact {contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
                    return

            contact_repo = ContactRepository(db_session)
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=phone,
            )

            # Find or create lead for this contact
            lead_repo = LeadRepository(db_session)
            # For simplicity, find first lead for this contact or create new one
            leads = await lead_repo.get_all(filters={"contact_card_id": contact_card.id, "company_id": company_id})
            lead = leads[0] if leads else None

            if not lead:
                from app.domain.models.lead import Lead
                from app.domain.enums import LeadStatus
                lead = Lead(
                    company_id=company_id,
                    contact_card_id=contact_card.id,
                    status=LeadStatus.NEW,
                )
                lead = await lead_repo.create(lead)

            # Parse dates
            start_time = None
            end_time = None
            if full_appt_data.get("startTime"):
                try:
                    start_time = datetime.fromisoformat(full_appt_data["startTime"].replace("Z", "+00:00"))
                except:
                    pass
            if full_appt_data.get("endTime"):
                try:
                    end_time = datetime.fromisoformat(full_appt_data["endTime"].replace("Z", "+00:00"))
                except:
                    pass

            # Map appointment status to outcome
            from app.domain.enums import AppointmentOutcome
            appt_status = full_appt_data.get("appointmentStatus", "").lower()
            if appt_status == "confirmed":
                outcome = AppointmentOutcome.PENDING
            elif appt_status == "completed":
                outcome = AppointmentOutcome.WON  # or could be LOST, depends on business logic
            elif appt_status == "cancelled":
                outcome = AppointmentOutcome.LOST
            else:
                outcome = None

            # Get assigned user
            assigned_rep_id = None
            assigned_user_id = full_appt_data.get("assignedUserId")
            if assigned_user_id:
                try:
                    user_info = await self.get_user_info(assigned_user_id)
                    if user_info:
                        # Map GHL user to our user by email
                        ghl_user_email = user_info.get("email")
                        if ghl_user_email:
                            user_repo = UserRepository(db_session)
                            user_orm = await user_repo.get_by_email(ghl_user_email)
                            if user_orm:
                                assigned_rep_id = user_orm.id
                                logger.info(f"Mapped GHL user {assigned_user_id} ({ghl_user_email}) to our user {assigned_rep_id}")
                            else:
                                logger.warning(f"GHL user {assigned_user_id} has email {ghl_user_email} but no matching user found in our database")
                        else:
                            logger.warning(f"GHL user {assigned_user_id} has no email field, cannot map to our user")
                except Exception as e:
                    logger.warning(f"Failed to fetch user {assigned_user_id}: {e}")

            # Find existing appointment by GHL appointment ID
            appt_repo = AppointmentRepository(db_session)
            existing_appt = None
            all_appts = await appt_repo.get_all(
                filters={"company_id": company_id, "lead_id": lead.id}
            )
            for appt in all_appts:
                if appt.extra_metadata and appt.extra_metadata.get("ghl_appointment_id") == appointment_id:
                    existing_appt = appt
                    break

            # Create or update appointment
            appointment_data = {
                "company_id": company_id,
                "lead_id": lead.id,
                "contact_card_id": contact_card.id,
                "scheduled_start": start_time or datetime.now(),
                "scheduled_end": end_time,
                "location_address": full_appt_data.get("address"),
                "outcome": outcome,
                "assigned_rep_id": assigned_rep_id,
                "extra_metadata": {
                    "ghl_appointment_id": appointment_id,
                    "ghl_contact_id": contact_id,
                    "ghl_calendar_id": full_appt_data.get("calendarId"),
                    "ghl_status": full_appt_data.get("appointmentStatus"),
                    "ghl_notes": full_appt_data.get("notes"),
                },
            }

            if existing_appt:
                # Update existing appointment
                appointment = Appointment(**{**appointment_data, "id": existing_appt.id})
                await appt_repo.update(existing_appt.id, appointment)
            else:
                # Create new appointment
                appointment = Appointment(**appointment_data)
                await appt_repo.create(appointment)

            logger.info(f"Updated appointment from GHL appointment {appointment_id}")

        except Exception as e:
            logger.error(f"Error updating appointment event: {e}", exc_info=True)
            raise

    async def insert_contact_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Insert contact event (same as update for contacts).

        Args:
            event: GHL event (ContactCreate)
            db_session: Database session
            company_id: Company UUID
        """
        await self.update_contact_event(event, db_session, company_id)

    async def insert_appointment_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Insert appointment event (same as update for appointments).

        Args:
            event: GHL event (AppointmentCreate)
            db_session: Database session
            company_id: Company UUID
        """
        await self.update_appointment_event(event, db_session, company_id)

    async def insert_lead_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Insert lead/opportunity event (same as update for leads).

        Args:
            event: GHL event (OpportunityCreate)
            db_session: Database session
            company_id: Company UUID
        """
        await self.update_lead_event(event, db_session, company_id)

    async def delete_contact_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Delete contact event (soft delete - mark as inactive or remove from active use).

        Args:
            event: GHL event (ContactDelete)
            db_session: Database session
            company_id: Company UUID
        """
        from app.infrastructure.repositories.contact import ContactRepository
        from app.infrastructure.database.models.contact import ContactCardORM
        from sqlalchemy import select

        try:
            contact_id = event.get("id")
            if not contact_id:
                logger.warning("Missing contact_id in delete event", event=event)
                return

            # Get contact info to find the contact card
            contact_info = await self.get_contact_info(contact_id)
            phone = contact_info.phone if contact_info else None
            if not phone:
                # Try to get phone from event payload
                phone = event.get("phone")
                if not phone:
                    logger.warning(f"No phone number available for contact {contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
                    return

            contact_repo = ContactRepository(db_session)
            # Find contact by phone
            result = await db_session.execute(
                select(ContactCardORM).where(
                    ContactCardORM.company_id == company_id,
                    ContactCardORM.primary_phone == contact_info.phone
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Mark as deleted in metadata or actually delete
                # For now, we'll just log it - actual deletion depends on business logic
                logger.info(f"Contact {contact_id} deleted in GHL, marking in metadata")
                contact_card = contact_repo._to_domain(existing)
                if not contact_card.extra_metadata:
                    contact_card.extra_metadata = {}
                contact_card.extra_metadata["ghl_deleted"] = True
                await contact_repo.update(existing.id, contact_card)

        except Exception as e:
            logger.error(f"Error deleting contact event: {e}", exc_info=True)

    async def delete_appointment_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Delete appointment event.

        Args:
            event: GHL event (AppointmentDelete)
            db_session: Database session
            company_id: Company UUID
        """
        from app.infrastructure.repositories.appointment import AppointmentRepository
        from sqlalchemy import select

        try:
            appointment_data = event.get("appointment") or event
            appointment_id = appointment_data.get("id")

            if not appointment_id:
                logger.warning("Missing appointment_id in delete event", event=event)
                return

            appt_repo = AppointmentRepository(db_session)
            # Find appointment by GHL ID in metadata
            # For now, we'll just log it
            logger.info(f"Appointment {appointment_id} deleted in GHL")
            # TODO: Implement actual deletion or soft delete

        except Exception as e:
            logger.error(f"Error deleting appointment event: {e}", exc_info=True)

    async def delete_lead_event(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ):
        """
        Delete lead/opportunity event.

        Args:
            event: GHL event (OpportunityDelete)
            db_session: Database session
            company_id: Company UUID
        """
        from app.infrastructure.repositories.lead import LeadRepository
        from app.domain.enums import LeadStatus

        try:
            opportunity_id = event.get("id")

            if not opportunity_id:
                logger.warning("Missing opportunity_id in delete event", event=event)
                return

            lead_repo = LeadRepository(db_session)
            # Find lead by GHL opportunity ID in metadata
            # For now, mark as abandoned
            logger.info(f"Opportunity {opportunity_id} deleted in GHL, marking lead as abandoned")
            # TODO: Implement actual deletion or status update

        except Exception as e:
            logger.error(f"Error deleting lead event: {e}", exc_info=True)

    async def process_call_webhook(
        self,
        event: Dict[str, Any],
        db_session: Any,
        company_id: Any,
    ) -> Dict[str, Any]:
        """
        Process GHL call webhook event.

        Handles CALL message types to:
        - Store recordings in S3
        - Link calls to Leads (contacts) and Users (internal staff via email)
        - Create call records in database
        - Update Lead with last call metadata

        Args:
            event: GHL webhook event payload (InboundMessage/OutboundMessage with messageType="CALL")
            db_session: Database session
            company_id: Company UUID

        Returns:
            Dict with processing results including call_id, recording_s3_url, etc.
        """

        from datetime import datetime
        from app.infrastructure.repositories.call import CallRepository
        from app.infrastructure.repositories.contact import ContactRepository
        from app.infrastructure.repositories.lead import LeadRepository
        from app.domain.users.repository import UserRepository
        from app.domain.models.call import Call
        from app.domain.models.lead import Lead
        from app.domain.enums import CallType, LeadStatus
        from app.core.s3 import get_s3_service

        try:
            # Extract call event data
            location_id: Optional[str] = event.get("locationId")
            contact_id: Optional[str] = event.get("contactId")
            date_added: Optional[str] = event.get("dateAdded")
            direction: Optional[str] = event.get("direction")
            user_id: Optional[str] = event.get("userId")
            message_id: Optional[str] = event.get("messageId")
            status: Optional[str] = event.get("status")
            call_from: Optional[str] = event.get("from")  # For outbound webhooks
            call_to: Optional[str] = event.get("to")  # For outbound webhooks
            call_duration: Optional[int] = event.get("callDuration") or event.get("duration")

            # Filter for completed calls only
            # Accept both "completed" and "answered" statuses
            if status and status.lower() not in ("completed", "answered"):
                logger.info(f"Skipping call with status {status}, only processing completed/answered calls")
                return {
                    "ok": True,
                    "isCall": True,
                    "skipped": True,
                    "reason": f"Status is {status}, not completed or answered",
                }

            logger.info(
                "Processing CALL webhook: locationId=%s userId=%s messageId=%s contactId=%s direction=%s",
                location_id, user_id, message_id, contact_id, direction
            )

            # Get contact info from GHL or extract from webhook payload
            contact_full_name = None
            contact_phone = None

            # For inbound calls: contact is the caller (from field)
            # For outbound calls: contact is the recipient (to field)
            if direction and direction.lower() in ("inbound", "incoming"):
                # Inbound: contact is the caller
                if call_from:
                    contact_phone = call_from
                elif contact_id:
                    contact_info = await self.get_contact_info(contact_id=contact_id)
                    if contact_info:
                        contact_full_name = contact_info.full_name
                        contact_phone = contact_info.phone
                    else:
                        logger.warning(f"Could not fetch contact info for contactId={contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
            elif direction and direction.lower() in ("outbound", "outgoing"):
                # Outbound: contact is the recipient
                if call_to:
                    contact_phone = call_to
                elif contact_id:
                    contact_info = await self.get_contact_info(contact_id=contact_id)
                    if contact_info:
                        contact_full_name = contact_info.full_name
                        contact_phone = contact_info.phone
                    else:
                        logger.warning(f"Could not fetch contact info for contactId={contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")
            else:
                # Fallback: try to get from contact_id or use from/to fields
                if contact_id:
                    contact_info = await self.get_contact_info(contact_id=contact_id)
                    if contact_info:
                        contact_full_name = contact_info.full_name
                        contact_phone = contact_info.phone
                    else:
                        logger.warning(f"Could not fetch contact info for contactId={contact_id} (bearer token: {'configured' if self.bearer_token else 'not configured'})")

                # If still no phone, try from/to fields
                if not contact_phone:
                    contact_phone = call_from or call_to

            if not contact_phone:
                logger.warning(f"No phone number found for contact (contactId={contact_id}, from={call_from}, to={call_to}), cannot process call")
                return {
                    "ok": False,
                    "isCall": True,
                    "error": "No phone number found for contact",
                }

            # Fetch recording and upload to S3
            recording_s3_url = None
            recording_filename = None
            recording_content_type = None
            recording_num_bytes = None

            if location_id and message_id:
                try:
                    rec = await self.get_message_recording(
                        location_id=location_id,
                        message_id=message_id,
                    )
                    recording_filename = rec.filename
                    recording_content_type = rec.content_type
                    recording_num_bytes = len(rec.audio_bytes)

                    # Upload to S3
                    s3_service = get_s3_service()
                    if s3_service:
                        try:
                            # Generate S3 key with company_id prefix
                            prefix = f"ghl-recordings/{company_id or 'unknown'}"
                            extension = "wav"
                            if recording_filename:
                                # Extract extension from filename
                                if "." in recording_filename:
                                    extension = recording_filename.split(".")[-1]

                            s3_key = s3_service.generate_s3_key(
                                prefix=prefix,
                                filename=f"{message_id}",
                                extension=extension
                            )

                            # Upload to S3 (audio bucket)
                            recording_s3_url = await s3_service.upload_file(
                                file_bytes=rec.audio_bytes,
                                s3_key=s3_key,
                                content_type=recording_content_type,
                                bucket_type="audio",
                                metadata={
                                    "location_id": location_id,
                                    "message_id": message_id,
                                    "contact_id": contact_id or "",
                                    "direction": direction or "",
                                    "date_added": date_added or "",
                                }
                            )

                            logger.info(
                                f"Uploaded recording to S3: {s3_key}",
                                location_id=location_id,
                                message_id=message_id,
                                s3_url=recording_s3_url
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to upload recording to S3: {e}",
                                exc_info=True,
                                location_id=location_id,
                                message_id=message_id
                            )
                    else:
                        logger.warning("S3 service not available, skipping upload")

                except Exception:
                    logger.exception(
                        f"Failed to fetch recording for locationId={location_id} messageId={message_id}"
                    )

            # Find or create contact card
            contact_repo = ContactRepository(db_session)
            contact_card = None
            try:
                # Parse name if available
                first_name = None
                last_name = None
                if contact_full_name:
                    name_parts = contact_full_name.split(maxsplit=1)
                    first_name = name_parts[0] if name_parts else None
                    last_name = name_parts[1] if len(name_parts) > 1 else None

                contact_card = await contact_repo.find_or_create_by_phone(
                    company_id=company_id,
                    phone=contact_phone,
                    first_name=first_name,
                    last_name=last_name,
                )
            except Exception as e:
                logger.exception(f"Failed to find or create contact for phone {contact_phone}: {e}")
                return {
                    "ok": False,
                    "isCall": True,
                    "error": f"Failed to find or create contact: {e}",
                }

            # Find or create lead by contact_card_id
            lead_repo = LeadRepository(db_session)
            lead = None
            try:
                # Find existing lead for this contact
                all_leads = await lead_repo.get_all(
                    filters={"company_id": company_id, "contact_card_id": contact_card.id}
                )
                # Get the most recent lead or first one
                lead = all_leads[0] if all_leads else None

                if not lead:
                    # Create new lead if none exists
                    lead = Lead(
                        company_id=company_id,
                        contact_card_id=contact_card.id,
                        status=LeadStatus.NEW,
                    )
                    lead = await lead_repo.create(lead)
                    logger.info(f"Created new lead {lead.id} for contact {contact_card.id}")
            except Exception as e:
                logger.exception(f"Failed to find or create lead for contact {contact_card.id}: {e}")

            # Match user by email (from GHL userId)
            handled_by_user_id = None
            if user_id:
                try:
                    user_info = await self.get_user_info(user_id)
                    if user_info:
                        ghl_user_email = user_info.get("email")
                        if ghl_user_email:
                            user_repo = UserRepository(db_session)
                            user_orm = await user_repo.get_by_email(ghl_user_email)
                            if user_orm:
                                handled_by_user_id = user_orm.id
                                logger.info(
                                    f"Mapped GHL user {user_id} ({ghl_user_email}) to our user {handled_by_user_id}"
                                )
                            else:
                                logger.warning(
                                    f"GHL user {user_id} has email {ghl_user_email} but no matching user found in our database"
                                )
                        else:
                            logger.warning(f"GHL user {user_id} has no email field, cannot map to our user")
                except Exception as e:
                    logger.warning(f"Failed to fetch user {user_id}: {e}")

            # Determine call_type from direction
            call_type = None
            if direction:
                direction_lower = direction.lower()
                if direction_lower in ("inbound", "incoming"):
                    call_type = CallType.CSR_CALL
                elif direction_lower in ("outbound", "outgoing"):
                    call_type = CallType.SALES_CALL

            # Prepare extra_metadata with GHL-specific data
            extra_metadata = {
                "ghl_location_id": location_id,
                "ghl_message_id": message_id,
                "ghl_contact_id": contact_id,
                "ghl_direction": direction,
                "ghl_date_added": date_added,
                "ghl_user_id": user_id,
                "ghl_contact_full_name": contact_full_name,
                "ghl_call_from": call_from,  # For outbound webhooks
                "ghl_call_to": call_to,  # For outbound webhooks
                "ghl_call_duration": call_duration,  # Duration in seconds
                "recording_filename": recording_filename,
                "recording_content_type": recording_content_type,
                "recording_num_bytes": recording_num_bytes,
            }

            # Create call record
            call_repo = CallRepository(db_session)
            call = Call(
                company_id=company_id,
                contact_card_id=contact_card.id,
                lead_id=lead.id if lead else None,
                phone_number=contact_phone,
                call_type=call_type,
                audio_url=recording_s3_url,
                duration_seconds=call_duration,  # From callDuration field in webhook
                missed_call=False,  # GHL calls are typically not missed
                handled_by_user_id=handled_by_user_id,
                interaction_type="call",
                extra_metadata=extra_metadata,
            )

            call = await call_repo.create(call)
            call_id = call.id

            logger.info(
                f"Created call record in database",
                call_id=str(call_id),
                company_id=str(company_id),
                location_id=location_id,
                message_id=message_id,
                lead_id=str(lead.id) if lead else None,
            )

            # Update lead with last call metadata
            if lead:
                try:
                    # Update lead's extra_metadata with last call info
                    if not lead.extra_metadata:
                        lead.extra_metadata = {}

                    lead.extra_metadata["last_call_id"] = str(call_id)
                    lead.extra_metadata["last_call_date"] = date_added or datetime.utcnow().isoformat()
                    lead.extra_metadata["last_call_direction"] = direction
                    lead.extra_metadata["last_call_recording_url"] = recording_s3_url
                    if handled_by_user_id:
                        lead.extra_metadata["last_call_handled_by"] = str(handled_by_user_id)

                    # Update lead status if it's new (mark as warm after first call)
                    if lead.status == LeadStatus.NEW:
                        lead.status = LeadStatus.WARM

                    await lead_repo.update(lead.id, lead)
                    logger.info(f"Updated lead {lead.id} with last call metadata")
                except Exception as e:
                    logger.exception(f"Failed to update lead metadata: {e}")

            # Trigger Shunya analysis if audio URL is available
            if recording_s3_url and not call.missed_call:
                try:
                    from app.services.call_service import CallService
                    call_service = CallService(db_session)
                    await call_service.trigger_analysis(call.id)
                    logger.info(f"Triggered Shunya analysis for GHL call {call.id}")
                except Exception as e:
                    logger.error(f"Failed to trigger Shunya analysis for call {call.id}: {e}", exc_info=True)
                    # Don't raise - analysis is non-critical

            return {
                "ok": True,
                "isCall": True,
                "locationId": location_id,
                "contactId": contact_id,
                "companyId": str(company_id) if company_id else None,
                "callId": str(call_id) if call_id else None,
                "leadId": str(lead.id) if lead else None,
                "dateAdded": date_added,
                "direction": direction,
                "userId": user_id,
                "handledByUserId": str(handled_by_user_id) if handled_by_user_id else None,
                "messageId": message_id,
                "contactFullName": contact_full_name,
                "contactPhone": contact_phone,
                "recordingContentType": recording_content_type,
                "recordingFilename": recording_filename,
                "recordingNumBytes": recording_num_bytes,
                "recordingS3Url": recording_s3_url,
            }

        except Exception as e:
            logger.error(f"Error processing call webhook: {e}", exc_info=True)
            raise
