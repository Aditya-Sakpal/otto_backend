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

        Args:
            raw_body: Raw request body bytes
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

            # Ensure key has proper PEM format
            if not public_key_pem.strip().startswith("-----BEGIN PUBLIC KEY-----"):
                # If it's just the key content, wrap it
                if isinstance(public_key_pem, str):
                    public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{public_key_pem}\n-----END PUBLIC KEY-----"

            # Load public key
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
            )

            # Verify signature
            sig_bytes = base64.b64decode(signature_b64)
            public_key.verify(
                sig_bytes,
                raw_body,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.error(f"Error verifying GHL signature: {e}")
            return False

    async def get_contact_info(self, contact_id: str) -> ContactInfo:
        """
        Fetch contact information from GHL.

        Calls GHL Get Contact:
          GET https://services.leadconnectorhq.com/contacts/:contactId

        Args:
            contact_id: GHL contact ID

        Returns:
            ContactInfo with contact details

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        if not self.bearer_token:
            raise ValueError("GHL bearer token not configured")

        url = f"{self.BASE_URL}/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }

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
            Dict with appointment details from the "event" key in the response

        Raises:
            ValueError: If bearer token is not configured
            httpx.HTTPStatusError: If API call fails
        """
        if not self.bearer_token:
            raise ValueError("GHL bearer token not configured")

        url = f"{self.BASE_URL}/calendars/events/appointments/{event_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data: Dict[str, Any] = resp.json()

        # GHL returns { "event": {...} } according to the API documentation
        event = data.get("event") if isinstance(data, dict) else None
        if not isinstance(event, dict):
            event = data if isinstance(data, dict) else {}

        return event

    async def get_opportunity_info(self, opportunity_id: str) -> Dict[str, Any]:
        """
        Fetch opportunity/lead information from GHL.

        Calls GHL Get Opportunity:
          GET https://services.leadconnectorhq.com/opportunities/:id

        Args:
            opportunity_id: GHL opportunity ID

        Returns:
            Dict with opportunity details from the "opportunity" key in the response

        Raises:
            ValueError: If bearer token is not configured
            httpx.HTTPStatusError: If API call fails
        """
        if not self.bearer_token:
            raise ValueError("GHL bearer token not configured")

        url = f"{self.BASE_URL}/opportunities/{opportunity_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data: Dict[str, Any] = resp.json()

        # GHL returns { "opportunity": {...} } according to the API documentation
        opportunity = data.get("opportunity") if isinstance(data, dict) else None
        if not isinstance(opportunity, dict):
            opportunity = data if isinstance(data, dict) else {}

        return opportunity

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch user/rep information from GHL.

        Calls GHL Get User:
          GET https://services.leadconnectorhq.com/users/:userId

        Args:
            user_id: GHL user ID

        Returns:
            Dict with user details (the API returns the user object directly)

        Raises:
            ValueError: If bearer token is not configured
            httpx.HTTPStatusError: If API call fails
        """
        if not self.bearer_token:
            raise ValueError("GHL bearer token not configured")

        url = f"{self.BASE_URL}/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data: Dict[str, Any] = resp.json()

        # GHL returns the user object directly according to the API documentation
        # (not wrapped in a "user" key)
        return data if isinstance(data, dict) else {}

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
            if not contact_info.phone:
                logger.warning(f"No phone number for contact {contact_id}")
                return

            contact_repo = ContactRepository(db_session)
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=contact_info.phone,
                email=None,  # Could fetch from contact_info if available
                first_name=contact_info.full_name.split()[0] if contact_info.full_name else None,
                last_name=" ".join(contact_info.full_name.split()[1:]) if contact_info.full_name and len(contact_info.full_name.split()) > 1 else None,
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
            if opp_data.get("assignedTo"):
                try:
                    user_info = await self.get_user_info(opp_data["assignedTo"])
                    if user_info:
                        # Map GHL user to our user by email
                        ghl_user_email = user_info.get("email")
                        if ghl_user_email:
                            user_repo = UserRepository(db_session)
                            user_orm = await user_repo.get_by_email(ghl_user_email)
                            if user_orm:
                                assigned_rep_id = user_orm.id
                                logger.info(f"Mapped GHL user {opp_data['assignedTo']} ({ghl_user_email}) to our user {assigned_rep_id}")
                            else:
                                logger.warning(f"GHL user {opp_data['assignedTo']} has email {ghl_user_email} but no matching user found in our database")
                        else:
                            logger.warning(f"GHL user {opp_data['assignedTo']} has no email field, cannot map to our user")
                except Exception as e:
                    logger.warning(f"Failed to fetch user {opp_data['assignedTo']}: {e}")

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

            # Get full contact details
            contact_info = await self.get_contact_info(contact_id)
            if not contact_info.phone:
                logger.warning(f"No phone number for contact {contact_id}")
                return

            # Get full contact details from GHL API
            url = f"{self.BASE_URL}/contacts/{contact_id}"
            headers = {
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
            }

            full_contact_data = {}
            if self.bearer_token:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    try:
                        resp = await client.get(url, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        full_contact_data = data.get("contact") or data
                    except httpx.HTTPError:
                        pass

            contact_repo = ContactRepository(db_session)

            # Parse name
            first_name = full_contact_data.get("firstName") or (contact_info.full_name.split()[0] if contact_info.full_name else None)
            last_name = full_contact_data.get("lastName") or (" ".join(contact_info.full_name.split()[1:]) if contact_info.full_name and len(contact_info.full_name.split()) > 1 else None)

            # Update or create contact
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=contact_info.phone,
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
            if not contact_info.phone:
                logger.warning(f"No phone number for contact {contact_id}")
                return

            contact_repo = ContactRepository(db_session)
            contact_card = await contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=contact_info.phone,
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
            if full_appt_data.get("assignedUserId"):
                try:
                    user_info = await self.get_user_info(full_appt_data["assignedUserId"])
                    if user_info:
                        # Map GHL user to our user by email
                        ghl_user_email = user_info.get("email")
                        if ghl_user_email:
                            user_repo = UserRepository(db_session)
                            user_orm = await user_repo.get_by_email(ghl_user_email)
                            if user_orm:
                                assigned_rep_id = user_orm.id
                                logger.info(f"Mapped GHL user {full_appt_data['assignedUserId']} ({ghl_user_email}) to our user {assigned_rep_id}")
                            else:
                                logger.warning(f"GHL user {full_appt_data['assignedUserId']} has email {ghl_user_email} but no matching user found in our database")
                        else:
                            logger.warning(f"GHL user {full_appt_data['assignedUserId']} has no email field, cannot map to our user")
                except Exception as e:
                    logger.warning(f"Failed to fetch user {full_appt_data['assignedUserId']}: {e}")

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
            if not contact_info.phone:
                logger.warning(f"No phone number for contact {contact_id}")
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

            # Filter for completed calls only
            if status and status.lower() != "completed":
                logger.info(f"Skipping call with status {status}, only processing completed calls")
                return {
                    "ok": True,
                    "isCall": True,
                    "skipped": True,
                    "reason": f"Status is {status}, not completed",
                }

            logger.info(
                "Processing CALL webhook: locationId=%s userId=%s messageId=%s contactId=%s",
                location_id, user_id, message_id, contact_id
            )

            # Get contact info from GHL
            contact_full_name = None
            contact_phone = None
            if contact_id:
                try:
                    contact_info = await self.get_contact_info(contact_id=contact_id)
                    contact_full_name = contact_info.full_name
                    contact_phone = contact_info.phone
                except Exception:
                    logger.exception(f"Failed to fetch contact info for contactId={contact_id}")

            if not contact_phone:
                logger.warning(f"No phone number found for contact {contact_id}, cannot process call")
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
