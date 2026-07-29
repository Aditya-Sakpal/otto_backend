"""Orchestrates Retell voice-agent tool calls into Otto CRM services."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email_controller import EmailController
from app.core.logging import get_logger
from app.domain.enums import CallType, LeadStatus, PipelineStage
from app.domain.models.call import Call
from app.domain.models.lead import Lead
from app.domain.schemas.voice_agent import (
    AvailableSlotsResponse,
    CreateAppointmentResponse,
    CreateLeadResponse,
    CurrentDateResponse,
    CustomerHistoryResponse,
    GenericStatusResponse,
    SaveCallSummaryResponse,
    SearchLeadResponse,
    SurfaceNextActionsResponse,
)
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.user import UserORM
from app.domain.models.appointment import Appointment
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.services.call_service import CallService
from app.services.lead_phone_resolver import LeadPhoneResolver, digits_only
from app.services.lead_service import LeadService
from app.services.pending_action_service import PendingActionService
from app.services.property_text_extractor import extract_property_from_text
from app.services.slot_availability_service import SlotAvailabilityService
from app.services.voice_follow_up_service import VoiceFollowUpService

logger = get_logger(__name__)

_VOICE_LEAD_STATUS_MAP: dict[str, tuple[LeadStatus, PipelineStage]] = {
    "qualified": (LeadStatus.QUALIFIED_UNBOOKED, PipelineStage.QUALIFIED),
    "unqualified": (LeadStatus.ABANDONED, PipelineStage.UNQUALIFIED),
    "service_not_offered": (
        LeadStatus.QUALIFIED_SERVICE_NOT_OFFERED,
        PipelineStage.SERVICE_NOT_OFFERED,
    ),
}

_PRIORITY_MAP = {"high": 10, "medium": 5, "low": 1}


def parse_retell_payload(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (args, call_dict) from Retell wrapped or flat body."""
    if "args" in body or "call" in body:
        args = body.get("args") or {}
        call = body.get("call") or {}
        return args, call if isinstance(call, dict) else {}
    return body, {}


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    d = digits_only(phone)
    if len(d) == 10:
        return d
    if len(d) == 11 and d.startswith("1"):
        return d[1:]
    return phone.strip()


def parse_customer_name(name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not name or not name.strip():
        return None, None
    parts = name.strip().split(None, 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else None
    return first, last


_INVALID_COMPANY_VALUES = frozenset(
    {"", "1", "{{company_id}}", "REPLACE_WITH_COMPANY_UUID"}
)


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def parse_company_id(raw: Optional[str], *, field: str = "company_id") -> UUID:
    """Parse tenant UUID from Retell args/query, falling back to env default.

    Retell often sends unresolved templates (``{{company_id}}``) or placeholders;
    those are ignored in favour of ``VOICE_AGENT_DEFAULT_COMPANY_ID``.
    """
    if raw is not None:
        candidate = str(raw).strip()
        if candidate and candidate not in _INVALID_COMPANY_VALUES and not (
            candidate.startswith("{{") and candidate.endswith("}}")
        ):
            if _looks_like_uuid(candidate):
                return UUID(candidate)
            logger.warning("Ignoring invalid voice-agent company_id", raw=candidate)
    default = (settings.VOICE_AGENT_DEFAULT_COMPANY_ID or "").strip()
    if default and _looks_like_uuid(default):
        return UUID(default)
    raise ValueError(f"{field} is required")


def resolve_company_id(args: dict[str, Any]) -> UUID:
    return parse_company_id(args.get("company_id"))


def phone_from_context(args: dict[str, Any], call: dict[str, Any]) -> Optional[str]:
    return normalize_phone(args.get("phone_number") or call.get("from_number"))


class VoiceAgentService:
    """Business logic for /api/v1/voice-agent/*."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.lead_repo = LeadRepository(session)
        self.lead_service = LeadService(session)
        self.phone_resolver = LeadPhoneResolver(session)
        self.slot_service = SlotAvailabilityService(session)
        self.follow_up_service = VoiceFollowUpService(session)

    async def _contact_display_name(self, contact_id: UUID) -> str:
        contact = await self.contact_repo.get_by_id(contact_id)
        if not contact:
            return ""
        parts = [contact.first_name or "", contact.last_name or ""]
        return " ".join(p for p in parts if p).strip()

    async def _lead_by_retell_call(self, company_id: UUID, call_id: str) -> Optional[Lead]:
        if not call_id:
            return None
        result = await self.session.execute(
            select(LeadORM)
            .where(
                LeadORM.company_id == company_id,
                LeadORM.extra_metadata.op("->>")("retell_call_id") == call_id,
            )
            .order_by(LeadORM.created_at.desc())
            .limit(1)
        )
        lead_orm = result.scalar_one_or_none()
        if not lead_orm:
            return None
        return self.lead_repo._to_domain(lead_orm)

    async def _system_user_id(self, company_id: UUID) -> UUID:
        result = await self.session.execute(
            select(UserORM)
            .where(UserORM.company_id == company_id, UserORM.is_active.is_(True))
            .order_by(UserORM.created_at.asc())
            .limit(1)
        )
        user = result.scalar_one_or_none()
        if user:
            return user.id
        return uuid4()

    def _build_history_text(self, card: Any, max_len: int = 300) -> tuple[bool, str]:
        if not card:
            return False, ""
        bits: list[str] = []
        if getattr(card, "pipeline_stage", None):
            bits.append(f"Pipeline stage: {card.pipeline_stage}")
        calls = getattr(card, "calls", None) or []
        if calls:
            latest = calls[0]
            summary = getattr(latest, "summary", None) or getattr(latest, "transcript", None)
            if summary:
                bits.append(str(summary)[:120])
        text = ". ".join(bits)
        if not text:
            return False, ""
        return True, text[:max_len]

    async def search_lead(
        self, args: dict[str, Any], call: dict[str, Any]
    ) -> SearchLeadResponse:
        company_id = resolve_company_id(args)
        phone = phone_from_context(args, call)
        if not phone:
            return SearchLeadResponse(found=False)

        resolved = await self.phone_resolver.resolve_by_phone(phone, company_id)
        if not resolved:
            return SearchLeadResponse(found=False)

        lead = await self.lead_repo.get_by_id(resolved.lead_id)
        name = await self._contact_display_name(resolved.contact_card_id)
        history_text = None

        status_val = None
        if lead and lead.status:
            status_val = lead.status.value if hasattr(lead.status, "value") else str(lead.status)

        # --- BUG 5 FIX: Convert raw backend objections into clean user-friendly labels ---
        _OBJECTION_LABEL_MAP = {
            "workmanship_quality_complaints": "Workmanship Quality Complaints",
            "competitor_related_concerns": "Competitor Related Concerns",
            "immediate_service_unavailability": "Immediate Service Unavailability",
            "in_person_estimates_only": "In-Person Estimates Only",
            "none_detected": "None Detected"
        }
        
        # Safe extraction and string conversion formatting logic
        meta = dict(lead.extra_metadata or {}) if lead else {}
        raw_objection = args.get("objection") or meta.get("objection") or "none_detected"
        objection_clean = _OBJECTION_LABEL_MAP.get(str(raw_objection).lower(), str(raw_objection).title())
        
        if lead and hasattr(lead, "extra_metadata"):
            meta["objection_label"] = objection_clean
            lead.extra_metadata = meta
            await self.lead_repo.update(lead.id, lead)
        # ---------------------------------------------------------------------------------

        return SearchLeadResponse(
            found=True,
            lead_id=str(resolved.lead_id),
            contact_id=str(resolved.contact_card_id),
            name=name or None,
            status=status_val,
            history_text=history_text,
        )

    async def get_customer_history(
        self, args: dict[str, Any], _call: dict[str, Any]
    ) -> CustomerHistoryResponse:
        lead_id = UUID(str(args["lead_id"]))
        card = await self.lead_service.get_customer_card(lead_id)
        has_history, history_text = self._build_history_text(card)
        return CustomerHistoryResponse(has_history=has_history, history_text=history_text)

    async def create_lead(
        self, args: dict[str, Any], call: dict[str, Any], *, call_id: Optional[str] = None
    ) -> CreateLeadResponse:
        company_id = resolve_company_id(args)
        retell_id = call_id or call.get("call_id")
        if retell_id:
            existing = await self._lead_by_retell_call(company_id, retell_id)
            if existing and existing.id:
                return CreateLeadResponse(
                    lead_id=str(existing.id),
                    contact_id=str(existing.contact_card_id),
                    created=False,
                )

        phone = phone_from_context(args, call)
        if not phone:
            raise ValueError("Caller phone number could not be resolved from call metadata")

        customer_name = (args.get("customer_name") or "Unknown").strip()
        first, last = parse_customer_name(customer_name if customer_name != "Unknown" else None)

        contact = await self.contact_repo.find_or_create_by_phone(
            company_id=company_id,
            phone=phone,
            first_name=first,
            last_name=last,
        )

        existing_leads = await self.lead_repo.get_all(
            filters={"contact_card_id": contact.id, "company_id": company_id},
            limit=1,
        )
        created = False
        if existing_leads:
            lead = existing_leads[0]
        else:
            lead_status, pipeline = _VOICE_LEAD_STATUS_MAP.get(
                str(args.get("lead_status") or "qualified").lower(),
                (LeadStatus.QUALIFIED_UNBOOKED, PipelineStage.QUALIFIED),
            )
            lead = Lead(  # type: ignore
                company_id=company_id,
                contact_card_id=contact.id,
                status=lead_status,
                pipeline_stage=pipeline,
                lead_source=args.get("lead_source") or "voice_agent",
            )

            lead = await self.lead_repo.create(lead)
            created = True

        # Enrich contact + lead from captured fields
        await self._apply_property_fields(contact.id, args)
        meta = dict(lead.extra_metadata or {})
        if retell_id:
            meta["retell_call_id"] = retell_id
        meta["voice_agent"] = True
        if args.get("problem_description"):
            meta["problem_description"] = args["problem_description"]
        if args.get("urgency"):
            meta["urgency"] = args["urgency"]
        if args.get("insurance_status"):
            meta["insurance_status"] = args["insurance_status"]
        lead.extra_metadata = meta
        lead.lead_source = args.get("lead_source") or lead.lead_source or "voice_agent"
        voice_status = args.get("lead_status")
        if voice_status and str(voice_status).lower() in _VOICE_LEAD_STATUS_MAP:
            st, ps = _VOICE_LEAD_STATUS_MAP[str(voice_status).lower()]
            lead.status = st
            lead.pipeline_stage = ps
        await self.lead_repo.update(lead.id, lead)

        await self.session.commit()
        return CreateLeadResponse(
            lead_id=str(lead.id),
            contact_id=str(contact.id),
            created=created,
        )

    async def _apply_property_fields(self, contact_id: UUID, args: dict[str, Any]) -> None:
        contact = await self.contact_repo.get_by_id(contact_id)
        if not contact:
            return
        if args.get("property_address"):
            contact.address = args["property_address"]
        parts = [
            args.get("property_address"),
            args.get("house_type"),
            args.get("square_footage"),
            args.get("roof_type"),
            args.get("roof_age"),
            args.get("problem_description"),
        ]
        extracted = extract_property_from_text(*(p for p in parts if p))
        snapshot = dict(contact.property_snapshot or {})
        for key, val in extracted.items():
            if val is not None:
                snapshot[key] = val
        for key in (
            "house_type",
            "square_footage",
            "roof_type",
            "roof_age",
            "problem_description",
        ):
            if args.get(key):
                snapshot[key] = args[key]
        contact.property_snapshot = snapshot or contact.property_snapshot
        await self.contact_repo.update(contact_id, contact)

    async def save_property_details(
        self, args: dict[str, Any], call: dict[str, Any]
    ) -> GenericStatusResponse:
        company_id = resolve_company_id(args)
        contact_id: UUID | None = None
        contact_id_raw = args.get("contact_id")
        if contact_id_raw and _looks_like_uuid(str(contact_id_raw).strip()):
            contact_id = UUID(str(contact_id_raw).strip())
        if contact_id is None:
            phone = phone_from_context(args, call)
            if not phone:
                raise ValueError("contact_id or caller phone required")
            resolved = await self.phone_resolver.resolve_by_phone(phone, company_id)
            if not resolved:
                contact = await self.contact_repo.find_or_create_by_phone(
                    company_id=company_id, phone=phone
                )
                contact_id = contact.id
            else:
                contact_id = resolved.contact_card_id
        await self._apply_property_fields(contact_id, args)
        await self.session.commit()
        return GenericStatusResponse(status="saved")

    async def update_lead(self, args: dict[str, Any], _call: dict[str, Any]) -> GenericStatusResponse:
        lead_id = UUID(str(args["lead_id"]))
        raw_status = str(args["status"]).lower()
        if raw_status in _VOICE_LEAD_STATUS_MAP:
            lead_status, pipeline = _VOICE_LEAD_STATUS_MAP[raw_status]
            lead = await self.lead_repo.get_by_id(lead_id)
            if lead:
                lead.status = lead_status
                lead.pipeline_stage = pipeline
                await self.lead_repo.update(lead_id, lead)
        else:
            await self.lead_service.update_status(
                lead_id,
                raw_status,
                reason=args.get("reason"),
            )
        await self.session.commit()
        return GenericStatusResponse(status="updated")

    async def get_current_date(self, company_id: UUID) -> CurrentDateResponse:
        tz_name = await self.slot_service.company_timezone(company_id)
        now = datetime.now(ZoneInfo(tz_name))
        return CurrentDateResponse(datetime=now.isoformat())

    async def get_available_slots(
        self, company_id: UUID, target_date: date, assigned_rep_id: Optional[UUID] = None
    ) -> AvailableSlotsResponse:
        slots = await self.slot_service.get_slots(
            company_id, target_date, assigned_rep_id=assigned_rep_id
        )
        return AvailableSlotsResponse(slots=slots)

    async def create_appointment(
        self, args: dict[str, Any], call: dict[str, Any], *, call_id: Optional[str] = None
    ) -> CreateAppointmentResponse:
        company_id = resolve_company_id(args)
        lead_id_raw = args.get("lead_id") or args.get("crm_lead_id")
        if lead_id_raw and _looks_like_uuid(str(lead_id_raw).strip()):
            lead_id = UUID(str(lead_id_raw).strip())
            lead = await self.lead_repo.get_by_id(lead_id)
            if not lead:
                raise ValueError("lead_id not found")
            contact_id = lead.contact_card_id
        else:
            lead_resp = await self.create_lead(args, call, call_id=call_id)
            lead_id = UUID(lead_resp.lead_id)
            contact_id = UUID(lead_resp.contact_id)

        start_raw = args.get("selected_start")
        if not start_raw:
            raise ValueError("selected_start is required")
        start_dt = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        appt_repo = AppointmentRepository(self.session)
        appt = await appt_repo.create(
            Appointment(  # type: ignore
                company_id=company_id,
                lead_id=lead_id,
                contact_card_id=contact_id,
                scheduled_start=start_dt,
                scheduled_end=start_dt + timedelta(hours=1),
                location_address=args.get("location_address") or args.get("property_address"),
            )
        )


        lead = await self.lead_repo.get_by_id(lead_id)
        if lead:
            lead.pipeline_stage = PipelineStage.BOOKED
            lead.status = LeadStatus.QUALIFIED_BOOKED
            await self.lead_repo.update(lead_id, lead)
        await self.session.commit()
        return CreateAppointmentResponse(appointment_id=str(appt.id))

    async def create_pending_action(
        self, args: dict[str, Any], call: dict[str, Any], *, call_id: Optional[str] = None
    ) -> GenericStatusResponse:
        company_id = resolve_company_id(args)
        assigned_by = await self._system_user_id(company_id)
        priority_raw = str(args.get("priority") or "medium").lower()
        priority = _PRIORITY_MAP.get(priority_raw, 5)
        lead_id = UUID(str(args["lead_id"])) if args.get("lead_id") else None
        svc = PendingActionService(self.session)
        await svc.create_task_manual(
            company_id=company_id,
            assigned_by_id=assigned_by,
            action_type=args.get("action_type") or "callback",
            raw_text=args.get("raw_text") or args.get("next_action") or "Voice agent follow-up",
            priority=priority,
            lead_id=lead_id,
            call_id=UUID(call_id) if call_id else None,
        )
        await self.session.commit()
        return GenericStatusResponse(status="created")

    async def generate_followup(self, args: dict[str, Any]) -> UUID | None:
        company_id = resolve_company_id(args)
        lead_id = UUID(str(args["lead_id"]))
        required = str(args.get("follow_up_required", "true")).lower() != "false"
        fid = await self.follow_up_service.propose_for_voice_lead(
            company_id,
            lead_id,
            context=args.get("context"),
            follow_up_required=required,
        )
        await self.session.commit()
        return fid

    async def surface_next_actions(
        self, args: dict[str, Any]
    ) -> SurfaceNextActionsResponse:
        company_id = resolve_company_id(args)
        lead_id = UUID(str(args["lead_id"])) if args.get("lead_id") else None
        q = select(PendingActionORM).where(
            PendingActionORM.company_id == company_id,
            PendingActionORM.status.in_(("pending", "in_progress")),
        )
        if lead_id:
            q = q.where(PendingActionORM.lead_id == lead_id)
        q = q.order_by(PendingActionORM.priority.desc().nullslast()).limit(5)
        result = await self.session.execute(q)
        actions = []
        for row in result.scalars().all():
            label = row.raw_text or row.action_type or "Follow up"
            actions.append(
                {
                    "label": label[:120],
                    "priority": str(row.priority or 5),
                }
            )
        return SurfaceNextActionsResponse(actions=actions)

    async def send_sms(self, args: dict[str, Any]) -> GenericStatusResponse:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_SYSTEM_NUMBER:
            return GenericStatusResponse(status="skipped", detail="Twilio not configured")
        company_id = resolve_company_id(args)
        lead_id = UUID(str(args["lead_id"]))
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return GenericStatusResponse(status="failed", detail="Lead not found")
        contact = await self.contact_repo.get_by_id(lead.contact_card_id)
        if not contact or not contact.primary_phone:
            return GenericStatusResponse(status="failed", detail="No phone on file")
        try:
            from twilio.rest import Client # type: ignore

            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=args["body"],
                from_=settings.TWILIO_SYSTEM_NUMBER,
                to=contact.primary_phone,
            )
            return GenericStatusResponse(status="sent")
        except Exception as exc:
            logger.error("Voice agent SMS failed", error=str(exc))
            return GenericStatusResponse(status="failed", detail=str(exc))

    async def send_email(self, args: dict[str, Any]) -> GenericStatusResponse:
        lead_id = UUID(str(args["lead_id"]))
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return GenericStatusResponse(status="failed", detail="Lead not found")
        contact = await self.contact_repo.get_by_id(lead.contact_card_id)
        if not contact or not contact.email:
            return GenericStatusResponse(status="failed", detail="No email on file")
        controller = EmailController()
        ok = await controller.provider.send_email(
            to=contact.email,
            subject=args["subject"],
            html_content=f"<p>{args['body']}</p>",
            text_content=str(args["body"]),
        )
        return GenericStatusResponse(status="sent" if ok else "failed")

    async def save_call_summary(
        self, args: dict[str, Any], call: dict[str, Any]
    ) -> SaveCallSummaryResponse:
        company_id = resolve_company_id(args)
        phone = phone_from_context(args, call) or "unknown"
        call_svc = CallService(self.session)
        ingested = await call_svc.ingest_call(
            company_id=company_id,
            phone_number=phone,
            call_type=CallType.CSR_CALL.value,
            missed_call=False,
        )
        
        # --- FIXED MYPY INCOMPATIBLE TYPE ASSIGNMENT (Line 588) ---
        if not ingested:
            raise ValueError("Failed to ingest call record or initialize record context")
            
        if args.get("transcript") or call.get("transcript"):
            ingested.transcript = args.get("transcript") or call.get("transcript")
        meta = dict(ingested.extra_metadata or {})
        if args.get("summary"):
            meta["summary"] = args["summary"]
        meta["source"] = "retell_voice_agent"
        if call.get("call_id"):
            meta["retell_call_id"] = call["call_id"]
        ingested.extra_metadata = meta
        if args.get("lead_id"):
            ingested.lead_id = UUID(str(args["lead_id"]))
        from app.infrastructure.repositories.call import CallRepository

        repo = CallRepository(self.session)
        ingested = await repo.update(ingested.id, ingested)  # type: ignore
        await self.session.commit()
        return SaveCallSummaryResponse(call_id=str(ingested.id))

    async def save_recording_analysis(self, args: dict[str, Any]) -> GenericStatusResponse:
        appointment_id = UUID(str(args["appointment_id"]))
        result = await self.session.execute(
            select(AppointmentORM).where(AppointmentORM.id == appointment_id)
        )
        appt = result.scalar_one_or_none()
        if not appt:
            return GenericStatusResponse(status="failed", detail="Appointment not found")
        if args.get("recording_url"):
            appt.audio_url = args["recording_url"]
            appt.recording_status = "uploaded"
        meta = dict(appt.extra_metadata or {})
        if args.get("transcript"):
            meta["voice_agent_transcript"] = args["transcript"]
        appt.extra_metadata = meta
        await self.session.flush()
        await self.session.commit()
        return GenericStatusResponse(status="saved")

    async def ingest_retell_call(self, payload: dict[str, Any]) -> SaveCallSummaryResponse:
        """Post-call webhook: persist transcript + summary."""
        call_obj = payload.get("call") or payload
        args = {
            "company_id": self._company_from_retell(payload),
            "lead_id": payload.get("metadata", {}).get("lead_id"),
            "transcript": call_obj.get("transcript"),
            "summary": call_obj.get("call_analysis", {}).get("call_summary")
            if isinstance(call_obj.get("call_analysis"), dict)
            else call_obj.get("summary"),
        }
        call_ctx = {
            "call_id": call_obj.get("call_id"),
            "from_number": call_obj.get("from_number"),
            "transcript": call_obj.get("transcript"),
        }
        return await self.save_call_summary(args, call_ctx)

    def _company_from_retell(self, payload: dict[str, Any]) -> str:
        call_obj = payload.get("call") or payload
        agent_id = call_obj.get("agent_id")
        if agent_id:
            try:
                mapping = dict(json.loads(settings.RETELL_AGENT_COMPANY_MAP or "{}"))
                if agent_id in mapping and mapping[agent_id]:
                    return str(mapping[agent_id])
            except json.JSONDecodeError:
                pass
        if settings.VOICE_AGENT_DEFAULT_COMPANY_ID:
            return str(settings.VOICE_AGENT_DEFAULT_COMPANY_ID)
        raise ValueError("Could not resolve company_id for Retell webhook")
