"""
ServiceTitan integration service.

Handles processing of ST webhook payloads (calls and CRM data) received from
the ST poller worker. The poller uses the Export API endpoints which return
flat response structures with continueFrom token pagination.

Export API response shapes (from ST OpenAPI docs):
  - Calls:    { id, from, to, duration (ISO 8601), direction, status, type, recordingUrl, customer: {id, name}, agent, campaign, lead }
  - Customers:  { id, name, type, address: {street, city, state, zip, country, lat, lng}, ... }
  - Customer Contacts: { id, type (Phone/Email/Fax/MobilePhone), value, customerId, active }
  - Leads:    { id, status (Open/Dismissed/Converted), customerId, leadPhone, leadEmail, leadCustomerName, leadStreet/City/State/Zip, bookingId, callId }
  - Bookings: { id, name, start, status (New/Converted/Dismissed/Accepted), address: {street, city, state, zip, country}, jobId }
"""
import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from app.domain.enums import AppointmentOutcome, CallType, LeadStatus, PendingActionStatus, PipelineStage
from app.domain.models.appointment import Appointment
from app.domain.models.lead import Lead
from app.domain.models.pending_action import PendingAction
from app.domain.users.repository import UserRepository
from app.infrastructure.integrations.servicetitan import ServiceTitanClient, parse_iso_duration
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.services.call_service import CallService

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
#  Status → enum mapping tables                                                #
# --------------------------------------------------------------------------- #

# ST Export Lead status has only 3 values: Open, Dismissed, Converted
ST_LEAD_STATUS_MAP: dict[str, LeadStatus] = {
    "open": LeadStatus.NEW,
    "dismissed": LeadStatus.ABANDONED,
    "converted": LeadStatus.CLOSED_WON,
}

# ST Booking status has 4 values: New, Accepted, Converted, Dismissed
ST_BOOKING_STATUS_MAP: dict[str, AppointmentOutcome] = {
    "new": AppointmentOutcome.PENDING,
    "accepted": AppointmentOutcome.PENDING,
    "converted": AppointmentOutcome.WON,
    "dismissed": AppointmentOutcome.LOST,
}

# LeadStatus → PipelineStage mapping (mirrors call_service._map_to_pipeline_stage)
ST_PIPELINE_STAGE_MAP: dict[LeadStatus, PipelineStage] = {
    LeadStatus.NEW: PipelineStage.REVIEW,
    LeadStatus.QUALIFIED_UNBOOKED: PipelineStage.QUALIFIED,
    LeadStatus.QUALIFIED_BOOKED: PipelineStage.BOOKED,
    LeadStatus.QUALIFIED_SERVICE_NOT_OFFERED: PipelineStage.SERVICE_NOT_OFFERED,
    LeadStatus.ABANDONED: PipelineStage.UNQUALIFIED,
    LeadStatus.CLOSED_WON: PipelineStage.WON,
    LeadStatus.CLOSED_LOST: PipelineStage.LOST,
}

# ST Export Call type values that indicate a missed call
ST_MISSED_CALL_TYPES = {"abandoned"}


class ServiceTitanService:
    """Service for processing ServiceTitan webhook data."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
        self.contact_repo = ContactRepository(session)
        self.lead_repo = LeadRepository(session)
        self.appointment_repo = AppointmentRepository(session)
        self.pending_action_repo = PendingActionRepository(session)
        self.integration_repo = CompanyIntegrationRepository(session)
        self.user_repo = UserRepository(session)
        self._st_client_cache: dict[UUID, ServiceTitanClient] = {}
        self._agent_user_cache: dict[str, UUID | None] = {}

    async def _get_st_client(self, company_id: UUID) -> ServiceTitanClient | None:
        """Get an authenticated ST client for the company, with caching."""
        if company_id in self._st_client_cache:
            return self._st_client_cache[company_id]
        creds = await self.integration_repo.get_decrypted_st_credentials(company_id)
        if not creds or not creds.get("client_id") or not creds.get("client_secret"):
            return None
        st_client = ServiceTitanClient(
            tenant_id=creds["tenant_id"],
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
        )
        self._st_client_cache[company_id] = st_client
        return st_client

    # ----------------------------------------------------------------------- #
    #  Agent → User resolution                                                 #
    # ----------------------------------------------------------------------- #

    @staticmethod
    def _normalize_agent_name(name: str) -> tuple[str, str]:
        """Normalize an ST agent name to (first, last) for fuzzy matching.

        'Jerome (Jerry) Cruz' → ('jerome', 'cruz')
        'Johnny L Jacobo'     → ('johnny', 'l jacobo')
        """
        # Strip parenthetical nicknames
        name = re.sub(r"\s*\([^)]*\)\s*", " ", name)
        # Strip double quotes and extra whitespace (preserve apostrophes in names)
        name = name.replace('"', "").strip()
        parts = name.split(maxsplit=1)
        first = parts[0].lower().strip() if parts else ""
        last = parts[1].lower().strip() if len(parts) > 1 else ""
        return first, last

    async def _resolve_agent_user(
        self,
        agent_data: Any,
        company_id: UUID,
    ) -> UUID | None:
        """Resolve an ST agent dict to an Otto user ID.

        Strategy:
        1. Try ST Employee API → get email → match by email
        2. Fallback: fuzzy name match within the company
        """
        if not isinstance(agent_data, dict):
            return None

        agent_name = (agent_data.get("name") or "").strip()
        if not agent_name:
            return None

        # Check cache first
        cache_key = f"{company_id}:{agent_name.lower()}"
        if cache_key in self._agent_user_cache:
            return self._agent_user_cache[cache_key]

        user_id: UUID | None = None

        # 1. Try ST Employee API for email
        agent_id = agent_data.get("id")
        if agent_id:
            try:
                st_client = await self._get_st_client(company_id)
                if st_client:
                    employee = await st_client.get_employee(agent_id)
                    if employee:
                        email = employee.get("email")
                        if email:
                            user_orm = await self.user_repo.get_by_email(
                                email
                            )
                            if user_orm:
                                user_id = user_orm.id
            except Exception as e:
                logger.debug(
                    f"ST employee API lookup failed for agent "
                    f"{agent_id}: {e}"
                )

        # 2. Fallback: fuzzy name match
        if not user_id:
            first, last = self._normalize_agent_name(agent_name)
            if first and last:
                user_orm = await self.user_repo.find_by_name(
                    company_id, first, last
                )
                if user_orm:
                    user_id = user_orm.id

        self._agent_user_cache[cache_key] = user_id
        if user_id:
            logger.info(
                f"Resolved ST agent '{agent_name}' → user {user_id}"
            )
        return user_id

    # ----------------------------------------------------------------------- #
    #  Public: calls webhook                                                   #
    # ----------------------------------------------------------------------- #

    async def process_calls_webhook(
        self,
        payload: dict[str, Any],
        company_id: UUID,
    ) -> dict[str, Any]:
        """
        Process a batch of ST calls from the worker.

        Args:
            payload: { "tenant_id": ..., "calls": [...] }
            company_id: Otto company UUID

        Returns:
            { "processed": N, "skipped": N, "errors": N }
        """
        processed = skipped = errors = 0
        for st_call in payload.get("calls", []):
            try:
                was_new = await self._process_single_call(st_call, company_id)
                if was_new:
                    processed += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(
                    f"Error processing ST call {st_call.get('id')}: {e}",
                    exc_info=True,
                )
                errors += 1
        return {"processed": processed, "skipped": skipped, "errors": errors}

    async def _process_single_call(
        self,
        st_call: dict[str, Any],
        company_id: UUID,
    ) -> bool:
        """
        Process one ST Export call record (flat structure).

        Export call fields:
          id, from, to, duration (ISO 8601 string e.g. "PT5M30S"),
          direction (Inbound/Outbound), status (Ringing/Answered/Completed/Initiated),
          type (Abandoned/Unbooked/Excused/Booked/NotLead/null),
          recordingUrl, customer: {id, name}, agent, campaign, lead

        Flow (per spec):
          New Call → upsert ContactCard → create Call → create Lead

        Returns True if a new call was created, False if duplicate.
        """
        st_call_id = str(st_call.get("id", ""))

        # 1. Resolve existing row by st_call_id (indexed JSON query — NOT get_all(limit=100)).
        #    Companies can have thousands of calls; the old scan missed prior rows so ST
        #    re-exports (e.g. type Unbooked → Booked) created duplicate calls + appointments.
        existing_st_call = (
            await self.call_repo.get_by_st_call_id(company_id, st_call_id) if st_call_id else None
        )

        # 2. Extract phone number — Export API has "from" at root level
        phone = st_call.get("from") or "anonymous"

        # 3. Upsert ContactCard
        customer = st_call.get("customer") or {}
        contact_name = customer.get("name") or ""
        name_parts = contact_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

        contact_card = await self.contact_repo.find_or_create_by_phone(
            company_id=company_id,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
        )

        # Store st_customer_id on contact if present
        st_customer_id = customer.get("id")
        if st_customer_id:
            meta = dict(contact_card.extra_metadata or {})
            st_cust_id = str(st_customer_id)
            if meta.get("st_customer_id") != st_cust_id:
                meta["st_customer_id"] = st_cust_id
                contact_card.extra_metadata = meta
                await self.contact_repo.update(contact_card.id, contact_card)

        # 3b. Enrich from ST CRM APIs — fetch full customer, contacts, leads
        if st_customer_id:
            await self._enrich_from_st_customer(st_customer_id, company_id)

        # 4. Detect missed call — Export API "type" is the call classification string
        call_type_raw = (st_call.get("type") or "").lower()
        is_missed = call_type_raw in ST_MISSED_CALL_TYPES

        # 5. Parse duration — Export API returns ISO 8601 duration string (e.g. "PT5M30S")
        duration_seconds = parse_iso_duration(st_call.get("duration"))

        # 6. Upload recording to S3 (skip for missed calls)
        recording_url = st_call.get("recordingUrl")
        s3_audio_url: Optional[str] = None
        if recording_url and not is_missed:
            try:
                # Resolve relative ST recording URLs to absolute
                if recording_url.startswith("/"):
                    api_base = ServiceTitanClient.PROD_API if settings.ST_ENV.lower() == "production" else ServiceTitanClient.INT_API
                    recording_url = f"{api_base}{recording_url}"

                # Build ST auth headers so we can download the recording
                st_headers: dict[str, str] | None = None
                try:
                    st_client = await self._get_st_client(company_id)
                    if st_client:
                        async with httpx.AsyncClient() as http_client:
                            token = await st_client._ensure_token(http_client)
                        st_headers = st_client._auth_headers(token)
                except Exception as e:
                    logger.warning(f"Could not get ST auth headers for recording download: {e}")

                s3_service = get_s3_service()
                if s3_service:
                    contact_id_str = str(contact_card.id) if contact_card else "unknown"
                    s3_key = f"recordings/{contact_id_str}/st_{st_call_id}.mp3"
                    s3_audio_url = await s3_service.upload_from_url(
                        url=recording_url,
                        s3_key=s3_key,
                        content_type="audio/mpeg",
                        metadata={
                            "st_call_id": st_call_id,
                            "company_id": str(company_id),
                        },
                        bucket_type="audio",
                        headers=st_headers,
                    )
                else:
                    s3_audio_url = recording_url
            except Exception as e:
                logger.error(f"Failed to upload ST recording to S3: {e}")
                s3_audio_url = recording_url

        # 6b. Resolve ST agent to Otto user
        handled_by_user_id = await self._resolve_agent_user(
            st_call.get("agent"), company_id
        )

        # 7a. Same ServiceTitan call id seen again — merge export onto one row (no second Call).
        if existing_st_call:
            old_meta = dict(existing_st_call.extra_metadata or {})
            old_type = (old_meta.get("st_type") or "").lower()
            new_type = call_type_raw
            existing_st_call.extra_metadata = {
                **old_meta,
                "st_call_id": st_call_id,
                "st_direction": st_call.get("direction"),
                "st_type": call_type_raw,
                "st_status": st_call.get("status"),
                "st_agent": st_call.get("agent"),
                "st_campaign": st_call.get("campaign"),
            }
            if contact_card:
                existing_st_call.contact_card_id = contact_card.id
            if duration_seconds is not None:
                existing_st_call.duration_seconds = duration_seconds
            if s3_audio_url:
                existing_st_call.audio_url = s3_audio_url
            if handled_by_user_id:
                existing_st_call.handled_by_user_id = handled_by_user_id
            existing_st_call.missed_call = is_missed
            existing_st_call.call_type = CallType.MISSED_CALL if is_missed else CallType.CSR_CALL
            if not existing_st_call.lead_source:
                ls = (
                    st_call.get("campaign", {}).get("name")
                    if isinstance(st_call.get("campaign"), dict)
                    else st_call.get("campaign")
                )
                if ls:
                    existing_st_call.lead_source = ls
            call = await self.call_repo.update(existing_st_call.id, existing_st_call)

            if contact_card and not is_missed:
                try:
                    lead = await self._find_lead_by_contact(contact_card.id, company_id)
                    if not lead:
                        new_lead = Lead(
                            company_id=company_id,
                            contact_card_id=contact_card.id,
                            status=LeadStatus.NEW,
                            pipeline_stage=ST_PIPELINE_STAGE_MAP.get(LeadStatus.NEW),
                            lead_source=st_call.get("campaign", {}).get("name")
                            if isinstance(st_call.get("campaign"), dict)
                            else st_call.get("campaign")
                            or None,
                            extra_metadata={"source": "st_call", "st_call_id": st_call_id},
                        )
                        lead = await self.lead_repo.create(new_lead)
                        logger.info(f"Created lead from ST call {st_call_id}")
                    if lead and lead.id and not call.lead_id:
                        call.lead_id = lead.id
                        call = await self.call_repo.update(call.id, call)
                except Exception as e:
                    logger.error(f"Failed to find/create/link lead for ST call {st_call_id}: {e}")

            if s3_audio_url and not is_missed and new_type == "booked" and old_type != "booked":
                try:
                    call_service = CallService(self.session)
                    await call_service.trigger_analysis(call.id)
                except Exception as e:
                    logger.error(f"Failed to trigger analysis after ST type→booked for {call.id}: {e}")

            logger.info(
                "Merged ServiceTitan export into existing call (dedupe by st_call_id)",
                call_id=str(call.id),
                st_call_id=st_call_id,
                old_st_type=old_type,
                new_st_type=new_type,
            )
            return False

        # 7b. Create Call record
        from app.domain.models.call import Call

        call = Call(
            company_id=company_id,
            contact_card_id=contact_card.id if contact_card else None,
            phone_number=phone,
            audio_url=s3_audio_url,
            duration_seconds=duration_seconds,
            call_type=CallType.MISSED_CALL if is_missed else CallType.CSR_CALL,
            missed_call=is_missed,
            interaction_type="call",
            handled_by_user_id=handled_by_user_id,
            lead_source=st_call.get("campaign", {}).get("name") if isinstance(st_call.get("campaign"), dict) else st_call.get("campaign") or None,
            extra_metadata={
                "st_call_id": st_call_id,
                "st_direction": st_call.get("direction"),
                "st_type": call_type_raw,
                "st_status": st_call.get("status"),
                "st_agent": st_call.get("agent"),
                "st_campaign": st_call.get("campaign"),
            },
        )
        call = await self.call_repo.create(call)
        logger.info(f"Created ST call {call.id} (st_call_id={st_call_id})")

        # 8. Create PendingAction for missed calls
        if is_missed:
            try:
                pending_action = PendingAction(
                    company_id=company_id,
                    call_id=call.id,
                    action_type="call_back",
                    raw_text=f"Give {phone} a call back",
                    status=PendingActionStatus.PENDING,
                    source="manual",
                )
                await self.pending_action_repo.create(pending_action)
            except Exception as e:
                logger.error(f"Failed to create pending action for ST missed call {call.id}: {e}")

        # 9. Trigger analysis if we have a recording
        if s3_audio_url and not is_missed:
            try:
                call_service = CallService(self.session)
                await call_service.trigger_analysis(call.id)
            except Exception as e:
                logger.error(f"Failed to trigger analysis for ST call {call.id}: {e}")

        # 10. Create Lead if contact doesn't have one yet (non-missed calls only)
        #     Per spec: New Call → upsert ContactCard → create Call → create Lead
        #     Also link the call to the lead so pipeline-detail can find conversations.
        if contact_card and not is_missed:
            try:
                lead = await self._find_lead_by_contact(contact_card.id, company_id)
                if not lead:
                    new_lead = Lead(
                        company_id=company_id,
                        contact_card_id=contact_card.id,
                        status=LeadStatus.NEW,
                        pipeline_stage=ST_PIPELINE_STAGE_MAP.get(LeadStatus.NEW),
                        lead_source=st_call.get("campaign", {}).get("name") if isinstance(st_call.get("campaign"), dict) else st_call.get("campaign") or None,
                        extra_metadata={"source": "st_call", "st_call_id": st_call_id},
                    )
                    lead = await self.lead_repo.create(new_lead)
                    logger.info(f"Created lead from ST call {st_call_id}")

                # Link call to lead
                if lead and lead.id:
                    call.lead_id = lead.id
                    await self.call_repo.update(call.id, call)
            except Exception as e:
                logger.error(f"Failed to create/link lead for ST call {st_call_id}: {e}")

        return True

    # ----------------------------------------------------------------------- #
    #  Private: enrich contact from ST CRM APIs                                #
    # ----------------------------------------------------------------------- #

    async def _enrich_from_st_customer(
        self,
        st_customer_id: int | str,
        company_id: UUID,
    ) -> None:
        """
        Fetch the full customer, their contacts, and leads from the ST API
        and process them through the existing CRM handlers.
        """
        try:
            st_client = await self._get_st_client(company_id)
            if not st_client:
                logger.debug("No ST client available for CRM enrichment")
                return

            cid = str(st_customer_id)
            logger.info(f"Enriching from ST customer {cid}")

            # Fetch full customer record
            try:
                full_customer = await st_client.get_customer(cid)
                await self._upsert_contact_from_customer(full_customer, company_id)
                logger.info(f"Enriched contact from ST customer {cid}")
            except Exception as e:
                logger.warning(f"Failed to fetch/process ST customer {cid}: {e}")

            # Fetch customer contacts (phone/email) via paginated endpoint
            try:
                contacts_path = f"/crm/v2/tenant/{st_client.tenant_id}/customers/{cid}/contacts"
                contacts_data = await st_client._get_paginated(contacts_path)
                for st_contact in contacts_data:
                    try:
                        await self._process_customer_contact(st_contact, company_id)
                    except Exception as e:
                        logger.warning(f"Failed to process ST contact {st_contact.get('id')}: {e}")
                if contacts_data:
                    logger.info(f"Processed {len(contacts_data)} contacts for ST customer {cid}")
            except Exception as e:
                logger.warning(f"Failed to fetch ST contacts for customer {cid}: {e}")

            # Fetch leads for this customer via paginated endpoint
            try:
                leads_path = f"/crm/v2/tenant/{st_client.tenant_id}/leads"
                leads_data = await st_client._get_paginated(
                    leads_path, {"customerId": cid}
                )
                for st_lead in leads_data:
                    try:
                        await self._upsert_lead(st_lead, company_id)
                    except Exception as e:
                        logger.warning(f"Failed to process ST lead {st_lead.get('id')}: {e}")
                if leads_data:
                    logger.info(f"Processed {len(leads_data)} leads for ST customer {cid}")
            except Exception as e:
                logger.warning(f"Failed to fetch ST leads for customer {cid}: {e}")

        except Exception as e:
            logger.error(f"Error enriching from ST customer {st_customer_id}: {e}", exc_info=True)

    # ----------------------------------------------------------------------- #
    #  Public: CRM webhook                                                     #
    # ----------------------------------------------------------------------- #

    async def process_crm_webhook(
        self,
        payload: dict[str, Any],
        company_id: UUID,
    ) -> dict[str, Any]:
        """
        Process a batch of ST CRM records (customers, customer_contacts, leads, bookings).

        Args:
            payload: {
                "tenant_id": ...,
                "customers": [...],
                "customer_contacts": [...],
                "leads": [...],
                "bookings": [...]
            }
            company_id: Otto company UUID

        Returns:
            { "contacts_upserted": N, "customer_contacts_updated": N,
              "leads_upserted": N, "appointments_upserted": N, "errors": N }
        """
        contacts_upserted = customer_contacts_updated = 0
        leads_upserted = appointments_upserted = errors = 0

        # 1. Process customers (name + address only, no phone/email)
        for st_customer in payload.get("customers", []):
            try:
                await self._upsert_contact_from_customer(st_customer, company_id)
                contacts_upserted += 1
            except Exception as e:
                logger.error(
                    f"Error upserting ST customer {st_customer.get('id')}: {e}",
                    exc_info=True,
                )
                errors += 1

        # 2. Process customer contacts (separate feed with phone/email linked by customerId)
        for st_contact in payload.get("customer_contacts", []):
            try:
                if await self._process_customer_contact(st_contact, company_id):
                    customer_contacts_updated += 1
            except Exception as e:
                logger.error(
                    f"Error processing ST customer contact {st_contact.get('id')}: {e}",
                    exc_info=True,
                )
                errors += 1

        # 3. Process leads (have their own contact fields: leadPhone, leadEmail, etc.)
        for st_lead in payload.get("leads", []):
            try:
                if await self._upsert_lead(st_lead, company_id):
                    leads_upserted += 1
            except Exception as e:
                logger.error(
                    f"Error upserting ST lead {st_lead.get('id')}: {e}",
                    exc_info=True,
                )
                errors += 1

        # 4. Process bookings (ST's equivalent of appointments)
        for st_booking in payload.get("bookings", []):
            try:
                if await self._upsert_appointment(st_booking, company_id):
                    appointments_upserted += 1
            except Exception as e:
                logger.error(
                    f"Error upserting ST booking {st_booking.get('id')}: {e}",
                    exc_info=True,
                )
                errors += 1

        return {
            "contacts_upserted": contacts_upserted,
            "customer_contacts_updated": customer_contacts_updated,
            "leads_upserted": leads_upserted,
            "appointments_upserted": appointments_upserted,
            "errors": errors,
        }

    # ----------------------------------------------------------------------- #
    #  Private: CRM helpers                                                    #
    # ----------------------------------------------------------------------- #

    async def _upsert_contact_from_customer(
        self,
        st_customer: dict[str, Any],
        company_id: UUID,
    ) -> None:
        """
        Map a full ST customer export record to a ContactCard.

        ST CustomerResponse has NO contacts/phone/email — only:
          { id, name, type (Residential/Commercial), address: {street, city, state, zip, country, lat, lng} }

        Phone/email come from the separate customer-contacts export feed.
        We create/update the ContactCard with name + address, using a placeholder phone
        that gets updated when customer-contacts are processed.
        """
        st_customer_id = str(st_customer.get("id", ""))

        # Check if we already have a ContactCard with this st_customer_id
        contact_card = await self._find_contact_by_st_customer_id(st_customer_id, company_id)

        name = st_customer.get("name") or ""
        name_parts = name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

        address_obj = st_customer.get("address") or {}

        if contact_card:
            # Update existing contact with fresh data
            update_needed = False
            if first_name and not contact_card.first_name:
                contact_card.first_name = first_name
                update_needed = True
            if last_name and not contact_card.last_name:
                contact_card.last_name = last_name
                update_needed = True
            if address_obj.get("street") and not contact_card.address:
                contact_card.address = address_obj["street"]
                update_needed = True
            if address_obj.get("city") and not contact_card.city:
                contact_card.city = address_obj["city"]
                update_needed = True
            if address_obj.get("state") and not contact_card.state:
                contact_card.state = address_obj["state"]
                update_needed = True
            if address_obj.get("zip") and not contact_card.postal_code:
                contact_card.postal_code = address_obj["zip"]
                update_needed = True
            if address_obj.get("lat") and not contact_card.latitude:
                contact_card.latitude = address_obj["lat"]
                update_needed = True
            if address_obj.get("lng") and not contact_card.longitude:
                contact_card.longitude = address_obj["lng"]
                update_needed = True

            if update_needed:
                await self.contact_repo.update(contact_card.id, contact_card)
                logger.debug(f"Updated contact {contact_card.id} from ST customer {st_customer_id}")
        else:
            # Create new contact with placeholder phone (will be updated by customer-contacts feed)
            placeholder_phone = f"st-customer-{st_customer_id}"
            contact_card = await self.contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=placeholder_phone,
                first_name=first_name,
                last_name=last_name,
            )

            # Set address and metadata
            update_needed = False
            if address_obj.get("street"):
                contact_card.address = address_obj["street"]
                update_needed = True
            if address_obj.get("city"):
                contact_card.city = address_obj["city"]
                update_needed = True
            if address_obj.get("state"):
                contact_card.state = address_obj["state"]
                update_needed = True
            if address_obj.get("zip"):
                contact_card.postal_code = address_obj["zip"]
                update_needed = True
            if address_obj.get("lat"):
                contact_card.latitude = address_obj["lat"]
                update_needed = True
            if address_obj.get("lng"):
                contact_card.longitude = address_obj["lng"]
                update_needed = True

            meta = dict(contact_card.extra_metadata or {})
            meta["st_customer_id"] = st_customer_id
            meta["st_customer_type"] = st_customer.get("type")
            contact_card.extra_metadata = meta
            update_needed = True

            if update_needed:
                await self.contact_repo.update(contact_card.id, contact_card)

            logger.info(f"Created contact from ST customer {st_customer_id}")

    async def _process_customer_contact(
        self,
        st_contact: dict[str, Any],
        company_id: UUID,
    ) -> bool:
        """
        Process one ST customer contact export record.

        ExportCustomerContactResponse: { id, type (Phone/Email/Fax/MobilePhone), value, customerId, active }

        Links phone/email to existing ContactCards by st_customer_id in extra_metadata.
        Updates placeholder phones (st-customer-{id}) with real phone numbers.
        """
        customer_id = str(st_contact.get("customerId") or "")
        contact_type = (st_contact.get("type") or "").lower()
        value = (st_contact.get("value") or "").strip()
        active = st_contact.get("active", True)

        if not customer_id or not value or not active:
            return False

        # Find existing ContactCard with this st_customer_id
        contact_card = await self._find_contact_by_st_customer_id(customer_id, company_id)
        if not contact_card:
            logger.debug(f"No contact found for ST customer {customer_id}, skipping contact method")
            return False

        update_needed = False

        if contact_type in ("phone", "mobilephone"):
            # Replace placeholder phone or set as secondary
            if contact_card.primary_phone and contact_card.primary_phone.startswith("st-customer-"):
                contact_card.primary_phone = value
                update_needed = True
            elif not contact_card.primary_phone or contact_card.primary_phone == "anonymous":
                contact_card.primary_phone = value
                update_needed = True
            elif contact_card.primary_phone != value and not contact_card.secondary_phone:
                contact_card.secondary_phone = value
                update_needed = True
        elif contact_type == "email":
            if not contact_card.email:
                contact_card.email = value
                update_needed = True

        if update_needed:
            await self.contact_repo.update(contact_card.id, contact_card)
            logger.debug(
                f"Updated contact {contact_card.id} with {contact_type}={value} "
                f"from ST customer {customer_id}"
            )

        return update_needed

    async def _upsert_lead(
        self,
        st_lead: dict[str, Any],
        company_id: UUID,
    ) -> bool:
        """
        Map an ST lead export record to a Lead.

        ST ExportLeadsResponse fields:
          { id, status (Open/Dismissed/Converted), customerId,
            leadPhone, leadEmail, leadCustomerName,
            leadStreet, leadCity, leadState, leadZip,
            bookingId, callId, campaignId, priority, summary }

        Flow (per spec): New/Update Lead → upsert ContactCard → create/update Lead
        """
        st_lead_id = str(st_lead.get("id", ""))

        # 1. Extract contact info from the lead's own fields
        phone = st_lead.get("leadPhone") or ""
        email = st_lead.get("leadEmail") or ""
        lead_name = st_lead.get("leadCustomerName") or ""
        name_parts = lead_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

        # 2. Upsert ContactCard — prefer phone from lead, fall back to st_customer_id lookup
        contact_card = None
        st_customer_id = str(st_lead.get("customerId") or "")

        if phone:
            contact_card = await self.contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=phone,
                email=email or None,
                first_name=first_name,
                last_name=last_name,
            )
        elif st_customer_id:
            contact_card = await self._find_contact_by_st_customer_id(st_customer_id, company_id)

        if not contact_card:
            logger.warning(
                f"ST lead {st_lead_id}: no phone or customer link, skipping"
            )
            return False

        # Update contact with address from lead if available
        update_contact = False
        if st_lead.get("leadStreet") and not contact_card.address:
            contact_card.address = st_lead["leadStreet"]
            update_contact = True
        if st_lead.get("leadCity") and not contact_card.city:
            contact_card.city = st_lead["leadCity"]
            update_contact = True
        if st_lead.get("leadState") and not contact_card.state:
            contact_card.state = st_lead["leadState"]
            update_contact = True
        if st_lead.get("leadZip") and not contact_card.postal_code:
            contact_card.postal_code = st_lead["leadZip"]
            update_contact = True

        # Link st_customer_id if present
        if st_customer_id:
            meta = dict(contact_card.extra_metadata or {})
            if meta.get("st_customer_id") != st_customer_id:
                meta["st_customer_id"] = st_customer_id
                contact_card.extra_metadata = meta
                update_contact = True

        if update_contact:
            await self.contact_repo.update(contact_card.id, contact_card)

        # 3. Map status — only 3 values: Open, Dismissed, Converted
        st_status = (st_lead.get("status") or "").lower()
        otto_status = ST_LEAD_STATUS_MAP.get(st_status, LeadStatus.NEW)

        # 4. Look for existing lead by st_lead_id in extra_metadata
        existing_lead = await self._find_lead_by_st_lead_id(st_lead_id, company_id)

        if existing_lead:
            existing_lead.status = otto_status
            new_stage = ST_PIPELINE_STAGE_MAP.get(otto_status)
            if new_stage:
                existing_lead.pipeline_stage = new_stage
            if st_lead.get("campaignId") and not existing_lead.lead_source:
                existing_lead.lead_source = str(st_lead["campaignId"])
            meta = dict(existing_lead.extra_metadata or {})
            meta["st_lead_id"] = st_lead_id
            if st_lead.get("bookingId"):
                meta["st_booking_id"] = str(st_lead["bookingId"])
            if st_lead.get("callId"):
                meta["st_call_id"] = str(st_lead["callId"])
            existing_lead.extra_metadata = meta
            await self.lead_repo.update(existing_lead.id, existing_lead)
            logger.debug(f"Updated lead {existing_lead.id} from ST lead {st_lead_id}")
        else:
            lead_meta: dict[str, Any] = {"st_lead_id": st_lead_id}
            if st_lead.get("bookingId"):
                lead_meta["st_booking_id"] = str(st_lead["bookingId"])
            if st_lead.get("callId"):
                lead_meta["st_call_id"] = str(st_lead["callId"])
            if st_lead.get("campaignId"):
                lead_meta["st_campaign_id"] = str(st_lead["campaignId"])

            new_lead = Lead(
                company_id=company_id,
                contact_card_id=contact_card.id,
                status=otto_status,
                pipeline_stage=ST_PIPELINE_STAGE_MAP.get(otto_status, PipelineStage.REVIEW),
                lead_source=str(st_lead["campaignId"]) if st_lead.get("campaignId") else None,
                extra_metadata=lead_meta,
            )
            await self.lead_repo.create(new_lead)
            logger.info(f"Created lead from ST lead {st_lead_id}")
        return True

    async def _upsert_appointment(
        self,
        st_booking: dict[str, Any],
        company_id: UUID,
    ) -> bool:
        """
        Map an ST booking export record to an Appointment.

        ST BookingResponse fields:
          { id, name, source, start, status (New/Converted/Dismissed/Accepted),
            address: {street, unit, city, state, zip, country},
            jobId, campaignId, businessUnitId, jobTypeId, priority, summary }

        Flow (per spec): New Appointment → upsert ContactCard → optionally create Lead → create Appointment
        Lead is auto-created if none exists so the DB FK constraint is satisfied.
        """
        st_booking_id = str(st_booking.get("id", ""))

        # 1. Upsert ContactCard from booking name + address
        booking_name = st_booking.get("name") or ""
        name_parts = booking_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

        address_obj = st_booking.get("address") or {}

        # Try to find an existing lead linked to this booking (via st_booking_id in lead metadata)
        lead = await self._find_lead_by_booking_id(st_booking_id, company_id)
        contact_card = None

        if lead:
            # Lead already exists — use its contact card
            contact_card = await self.contact_repo.get_by_id(lead.contact_card_id)
        else:
            # No lead linked to this booking — try to find contact by booking name
            # Bookings don't have phone/customer info directly, use a placeholder
            placeholder_phone = f"st-booking-{st_booking_id}"
            contact_card = await self.contact_repo.find_or_create_by_phone(
                company_id=company_id,
                phone=placeholder_phone,
                first_name=first_name,
                last_name=last_name,
            )

            # Update address on contact
            update_needed = False
            if address_obj.get("street") and not contact_card.address:
                contact_card.address = address_obj["street"]
                update_needed = True
            if address_obj.get("city") and not contact_card.city:
                contact_card.city = address_obj["city"]
                update_needed = True
            if address_obj.get("state") and not contact_card.state:
                contact_card.state = address_obj["state"]
                update_needed = True
            if address_obj.get("zip") and not contact_card.postal_code:
                contact_card.postal_code = address_obj["zip"]
                update_needed = True

            meta = dict(contact_card.extra_metadata or {})
            meta["st_booking_id"] = st_booking_id
            contact_card.extra_metadata = meta
            update_needed = True

            if update_needed:
                await self.contact_repo.update(contact_card.id, contact_card)

        if not contact_card:
            logger.warning(f"ST booking {st_booking_id}: no contact data, skipping")
            return False

        # 2. Find or auto-create Lead (DB FK requires one)
        if not lead:
            lead = await self._find_lead_by_contact(contact_card.id, company_id)
        if not lead:
            new_lead = Lead(
                company_id=company_id,
                contact_card_id=contact_card.id,
                status=LeadStatus.NEW,
                pipeline_stage=PipelineStage.BOOKED,
                lead_source=st_booking.get("source") or (str(st_booking["campaignId"]) if st_booking.get("campaignId") else None),
                extra_metadata={"source": "st_booking", "st_booking_id": st_booking_id},
            )
            lead = await self.lead_repo.create(new_lead)
            logger.info(f"Auto-created lead for contact {contact_card.id} from ST booking {st_booking_id}")

        # 3. Parse scheduled_start from "start" field
        start_raw = st_booking.get("start")
        if not start_raw:
            logger.warning(f"ST booking {st_booking_id}: no start date, skipping")
            return False
        try:
            scheduled_start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            logger.warning(f"ST booking {st_booking_id}: could not parse start date '{start_raw}', skipping")
            return False

        # 4. Map booking status — 4 values: New, Accepted, Converted, Dismissed
        st_status = (st_booking.get("status") or "").lower()
        outcome = ST_BOOKING_STATUS_MAP.get(st_status, AppointmentOutcome.PENDING)

        # 5. Build location address
        if isinstance(address_obj, dict):
            parts = [
                address_obj.get("street", ""),
                address_obj.get("unit", ""),
                address_obj.get("city", ""),
                address_obj.get("state", ""),
                address_obj.get("zip", ""),
            ]
            location_address = ", ".join(p for p in parts if p) or None
        else:
            location_address = None

        # Fallback to contact card address if booking has no address
        if not location_address and contact_card:
            parts = [contact_card.address, contact_card.city, contact_card.state, contact_card.postal_code]
            location_address = ", ".join(p for p in parts if p) or None

        # 6. Look for existing appointment by st_booking_id
        existing_appt = await self._find_appointment_by_st_booking_id(st_booking_id, company_id)

        if existing_appt:
            existing_appt.scheduled_start = scheduled_start
            existing_appt.outcome = outcome
            if location_address:
                existing_appt.location_address = location_address
            meta = dict(existing_appt.extra_metadata or {})
            meta["st_booking_id"] = st_booking_id
            if st_booking.get("jobId"):
                meta["st_job_id"] = str(st_booking["jobId"])
            existing_appt.extra_metadata = meta
            await self.appointment_repo.update(existing_appt.id, existing_appt)
            logger.debug(f"Updated appointment {existing_appt.id} from ST booking {st_booking_id}")
        else:
            appt_meta: dict[str, Any] = {"st_booking_id": st_booking_id}
            if st_booking.get("jobId"):
                appt_meta["st_job_id"] = str(st_booking["jobId"])
            if st_booking.get("campaignId"):
                appt_meta["st_campaign_id"] = str(st_booking["campaignId"])

            new_appt = Appointment(
                company_id=company_id,
                lead_id=lead.id,
                contact_card_id=contact_card.id,
                scheduled_start=scheduled_start,
                location_address=location_address,
                outcome=outcome,
                extra_metadata=appt_meta,
            )
            await self.appointment_repo.create(new_appt)
            logger.info(f"Created appointment from ST booking {st_booking_id}")

        # Lead conversion: spec says completed/converted booking → Lead.status=converted
        if outcome == AppointmentOutcome.WON:
            await self._handle_conversion(lead, contact_card)

        return True

    async def _handle_conversion(self, lead, contact_card) -> None:
        """
        Handle lead conversion when a booking is converted.

        Per spec: Appointment.status == completed → Lead.status = converted,
        ContactCard.type = customer
        """
        if lead and lead.status not in (LeadStatus.CLOSED_WON, LeadStatus.CLOSED_LOST):
            lead.status = LeadStatus.CLOSED_WON
            await self.lead_repo.update(lead.id, lead)
            logger.info(f"Converted lead {lead.id} to CLOSED_WON")

        # ContactCard has no dedicated type field; track via extra_metadata
        meta = dict(contact_card.extra_metadata or {})
        if not meta.get("is_customer"):
            meta["is_customer"] = True
            contact_card.extra_metadata = meta
            await self.contact_repo.update(contact_card.id, contact_card)
            logger.info(f"Marked contact {contact_card.id} as customer")

    # ----------------------------------------------------------------------- #
    #  Lookup helpers                                                           #
    # ----------------------------------------------------------------------- #

    async def _find_contact_by_st_customer_id(
        self,
        st_customer_id: str,
        company_id: UUID,
    ):
        """Find a ContactCard by st_customer_id stored in extra_metadata."""
        if not st_customer_id:
            return None
        all_contacts = await self.contact_repo.get_all(
            filters={"company_id": company_id}
        )
        for c in all_contacts:
            if c.extra_metadata and c.extra_metadata.get("st_customer_id") == st_customer_id:
                return c
        return None

    async def _find_lead_by_st_lead_id(
        self,
        st_lead_id: str,
        company_id: UUID,
    ):
        """Find a Lead by st_lead_id stored in extra_metadata."""
        if not st_lead_id:
            return None
        all_leads = await self.lead_repo.get_all(
            filters={"company_id": company_id}
        )
        for lead in all_leads:
            if lead.extra_metadata and lead.extra_metadata.get("st_lead_id") == st_lead_id:
                return lead
        return None

    async def _find_lead_by_contact(
        self,
        contact_card_id: UUID,
        company_id: UUID,
    ):
        """Return the first Lead for a given contact card."""
        all_leads = await self.lead_repo.get_all(
            filters={"company_id": company_id, "contact_card_id": contact_card_id}
        )
        return all_leads[0] if all_leads else None

    async def _find_lead_by_booking_id(
        self,
        st_booking_id: str,
        company_id: UUID,
    ):
        """Find a Lead that has st_booking_id stored in extra_metadata."""
        if not st_booking_id:
            return None
        all_leads = await self.lead_repo.get_all(
            filters={"company_id": company_id}
        )
        for lead in all_leads:
            if lead.extra_metadata and lead.extra_metadata.get("st_booking_id") == st_booking_id:
                return lead
        return None

    async def _find_appointment_by_st_booking_id(
        self,
        st_booking_id: str,
        company_id: UUID,
    ):
        """Find an Appointment by st_booking_id stored in extra_metadata."""
        if not st_booking_id:
            return None
        all_appts = await self.appointment_repo.get_by_company(company_id=company_id)
        for appt in all_appts:
            if appt.extra_metadata and appt.extra_metadata.get("st_booking_id") == st_booking_id:
                return appt
        return None
