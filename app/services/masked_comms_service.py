"""
Masked communications service.

Handles the core call bridging, SMS forwarding, and recording pipeline:
- Inbound call/SMS webhook handling (returns TwiML)
- Outbound call initiation (rep → homeowner via proxy)
- Outbound SMS (rep → homeowner via proxy)
- Call status and recording callbacks
- Recording → S3 → Shunya pipeline integration
- Recording consent disclosure (with 500ms timeout)
- Personalized push notifications via ReplyNotificationService
"""
import asyncio
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import PendingActionStatus
from app.domain.models.masked_communication import MaskedCommunication
from app.domain.models.pending_action import PendingAction
from app.infrastructure.integrations.twilio_client import get_twilio_client
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.repositories.masked_communication import MaskedCommunicationRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.repositories.proxy_session import ProxySessionRepository
from app.infrastructure.repositories.proxy_number import ProxyNumberRepository
from app.infrastructure.repositories.rep_phone import RepPhoneRepository
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.services.intent_to_action_service import (
    classify_inbound_reply,
    suggested_next_action,
)
from app.services.proxy_session_service import ProxySessionService
from app.services.reply_notification_service import ReplyNotificationService

logger = get_logger(__name__)


class MaskedCommsService:
    """Handles call bridging, SMS forwarding, recording pipeline."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.comms_repo = MaskedCommunicationRepository(session)
        self.session_repo = ProxySessionRepository(session)
        self.proxy_number_repo = ProxyNumberRepository(session)
        self.rep_phone_repo = RepPhoneRepository(session)
        self.session_service = ProxySessionService(session)
        self.twilio = get_twilio_client()
        self.reply_notification = ReplyNotificationService(session)
        self.ci_repo = CompanyIntegrationRepository(session)

    # ── Inbound Call (Twilio webhook) ─────────────────────────────────────

    async def handle_inbound_call(
        self,
        proxy_number: str,
        caller: str,
        twilio_call_sid: str,
    ) -> str:
        """
        Handle inbound voice call to a proxy number.

        Returns TwiML XML to bridge the call to the other party.
        """
        session, direction = await self.session_service.resolve_inbound(
            proxy_number, caller
        )

        # Determine bridge target
        if direction == "homeowner_to_rep":
            bridge_to = session.rep_phone
        else:
            bridge_to = session.homeowner_phone

        # Log the communication
        comm = MaskedCommunication(
            session_id=session.id,
            company_id=session.company_id,
            lead_id=session.lead_id,
            comm_type="call",
            direction=direction,
            from_number=caller,
            to_number=bridge_to,
            proxy_number=proxy_number,
            twilio_call_sid=twilio_call_sid,
            call_status="initiated",
            is_homeowner_reply=(direction == "homeowner_to_rep"),
        )
        await self.comms_repo.create(comm)

        # Send personalized push notification if homeowner is calling the rep
        if direction == "homeowner_to_rep":
            await self.reply_notification.notify_rep_of_inbound_call(
                session, twilio_call_sid
            )

        # Recording consent disclosure (500ms timeout — Twilio drops slow TwiML)
        recording_say = await self._get_recording_disclosure(session.company_id)

        # Generate TwiML to bridge
        webhook_base = self._webhook_base_url()
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"{recording_say}"
            f'<Dial callerId="{proxy_number}" '
            f'record="record-from-answer-dual" '
            f'recordingStatusCallback="{webhook_base}/api/v1/webhooks/twilio/recording-status" '
            f'recordingStatusCallbackEvent="completed" '
            f'action="{webhook_base}/api/v1/webhooks/twilio/call-status">'
            f"<Number>{bridge_to}</Number>"
            "</Dial>"
            "</Response>"
        )

        logger.info(
            "Bridging inbound call",
            call_sid=twilio_call_sid,
            direction=direction,
            session_id=str(session.id),
        )
        return twiml

    # ── Inbound SMS (Twilio webhook) ──────────────────────────────────────

    async def handle_inbound_sms(
        self,
        proxy_number: str,
        sender: str,
        body: str,
        twilio_message_sid: str,
    ) -> str:
        """
        Handle inbound SMS to a proxy number.

        Forwards the message to the other party and logs both.
        Returns empty TwiML (forwarding done via API, not TwiML).
        """
        session, direction = await self.session_service.resolve_inbound(
            proxy_number, sender
        )

        # Idempotency guard: Twilio may replay webhooks. If this MessageSid already
        # exists, do nothing (no second forward/push/task).
        existing = await self.comms_repo.get_by_twilio_message_sid(twilio_message_sid)
        if existing:
            logger.info(
                "Inbound SMS duplicate MessageSid — skipping",
                message_sid=twilio_message_sid,
                session_id=str(session.id),
            )
            return '<?xml version="1.0" encoding="UTF-8"?><Response/>'

        # Determine forward target
        if direction == "homeowner_to_rep":
            forward_to = session.rep_phone
        else:
            forward_to = session.homeowner_phone

        # Log the inbound message
        intent_label: Optional[str] = None
        confidence_score: Optional[float] = None
        extra_metadata = {}
        if direction == "homeowner_to_rep":
            intent_label, confidence_score, extra_metadata = await self._classify_sms_intent(
                message_body=body
            )

        comm = MaskedCommunication(
            session_id=session.id,
            company_id=session.company_id,
            lead_id=session.lead_id,
            comm_type="sms",
            direction=direction,
            from_number=sender,
            to_number=forward_to,
            proxy_number=proxy_number,
            twilio_message_sid=twilio_message_sid,
            message_body=body,
            is_homeowner_reply=(direction == "homeowner_to_rep"),
            intent_label=intent_label,
            confidence_score=confidence_score,
            extra_metadata=extra_metadata or None,
        )
        created_comm = await self.comms_repo.create(comm)

        # Forward the SMS via Twilio API
        if self.twilio.is_available():
            try:
                self.twilio.send_sms(
                    from_number=proxy_number,
                    to_number=forward_to,
                    body=body,
                )
            except Exception as e:
                logger.error(f"Failed to forward SMS: {e}", session_id=str(session.id))

        # Personalized push notification
        if direction == "homeowner_to_rep":
            await self.reply_notification.notify_rep_of_inbound_sms(
                session, body, created_comm.id
            )
            await self._maybe_create_callback_task(
                session_id=session.id,
                company_id=session.company_id,
                lead_id=session.lead_id,
                owner_id=session.rep_user_id,
                comm_id=created_comm.id,
                twilio_message_sid=twilio_message_sid,
                message_body=body,
                intent_label=intent_label,
                extra_metadata=extra_metadata,
            )

        logger.info(
            "Forwarded inbound SMS",
            message_sid=twilio_message_sid,
            direction=direction,
            session_id=str(session.id),
        )

        return '<?xml version="1.0" encoding="UTF-8"?><Response/>'

    async def _classify_sms_intent(self, message_body: str) -> tuple[Optional[str], Optional[float], dict]:
        """
        Classify inbound homeowner SMS and attach deterministic suggestion metadata.
        """
        text_body = (message_body or "").strip()
        if not text_body:
            return None, None, {}

        intent, conf = await classify_inbound_reply(text_body)
        suggestion = suggested_next_action(intent)
        return (
            intent,
            conf,
            {
                "intent_to_action": {
                    "suggested_action_type": suggestion.get("action_type"),
                    "suggested_action_summary": suggestion.get("summary"),
                    "reply_draft": suggestion.get("reply_draft"),
                },
                "source": "masked_comms_inbound_sms",
            },
        )

    async def _maybe_create_callback_task(
        self,
        *,
        session_id: UUID,
        company_id: UUID,
        lead_id: UUID,
        owner_id: UUID,
        comm_id: UUID,
        twilio_message_sid: str,
        message_body: str,
        intent_label: Optional[str],
        extra_metadata: Optional[dict],
    ) -> None:
        """
        Materialize call_me intent into a call_back pending action.
        """
        if intent_label != "call_me":
            return

        repo = PendingActionRepository(self.session)
        existing = await self.session.execute(
            select(PendingActionORM).where(
                PendingActionORM.company_id == company_id,
                PendingActionORM.lead_id == lead_id,
                PendingActionORM.action_type == "call_back",
                PendingActionORM.status.in_(
                    [
                        PendingActionStatus.PENDING.value,
                        PendingActionStatus.IN_PROGRESS.value,
                    ]
                ),
                # JSON idempotency check: avoid `.contains(...)` which can generate
                # incompatible SQL for JSON vs JSONB types.
                func.json_extract_path_text(
                    PendingActionORM.extra_metadata, "sms_intent_twilio_message_sid"
                )
                == twilio_message_sid,
            )
        )
        if existing.scalar_one_or_none():
            logger.info(
                "Skipped duplicate SMS callback task",
                message_sid=twilio_message_sid,
                session_id=str(session_id),
            )
            return

        suggestion = ((extra_metadata or {}).get("intent_to_action") or {}).get(
            "suggested_action_summary"
        ) or "Homeowner requested a callback via SMS."
        task = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            action_type="call_back",
            raw_text=f"Call back homeowner: {message_body[:120]}",
            status=PendingActionStatus.PENDING,
            owner_id=owner_id,
            source="system",
            extra_metadata={
                "materialized_from": "sms_intent",
                "sms_intent_label": intent_label,
                "sms_intent_twilio_message_sid": twilio_message_sid,
                "masked_comm_id": str(comm_id),
                "suggested_action_summary": suggestion,
            },
        )
        await repo.create(task)
        logger.info(
            "Created callback task from SMS intent",
            message_sid=twilio_message_sid,
            session_id=str(session_id),
            lead_id=str(lead_id),
        )

    # ── Outbound Call (from mobile app) ───────────────────────────────────

    async def initiate_outbound_call(self, session_id: UUID) -> dict:
        """
        Rep initiates a call to homeowner via the mobile app.

        Two-leg bridge:
        1. Call rep's phone from proxy number
        2. When rep answers, TwiML bridges to homeowner
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        proxy = await self.proxy_number_repo.get_by_id(session.proxy_number_id)
        if not proxy:
            raise ValueError(f"Proxy number {session.proxy_number_id} not found")

        webhook_base = self._webhook_base_url()
        bridge_url = f"{webhook_base}/api/v1/webhooks/twilio/bridge-call/{session_id}"
        status_url = f"{webhook_base}/api/v1/webhooks/twilio/call-status"

        if not self.twilio.is_available():
            raise RuntimeError("Twilio not configured")

        result = self.twilio.create_outbound_call(
            from_number=proxy.phone_number,
            to_number=session.rep_phone,
            twiml_url=bridge_url,
            status_callback_url=status_url,
            record=True,
        )

        # Log the communication
        comm = MaskedCommunication(
            session_id=session.id,
            company_id=session.company_id,
            lead_id=session.lead_id,
            comm_type="call",
            direction="rep_to_homeowner",
            from_number=session.rep_phone,
            to_number=session.homeowner_phone,
            proxy_number=proxy.phone_number,
            twilio_call_sid=result["call_sid"],
            call_status="initiated",
        )
        await self.comms_repo.create(comm)

        logger.info(
            "Initiated outbound call",
            call_sid=result["call_sid"],
            session_id=str(session_id),
        )
        return result

    # ── Outbound SMS (from mobile app) ────────────────────────────────────

    async def send_sms(self, session_id: UUID, body: str) -> dict:
        """Rep sends SMS to homeowner via mobile app."""
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        proxy = await self.proxy_number_repo.get_by_id(session.proxy_number_id)
        if not proxy:
            raise ValueError(f"Proxy number {session.proxy_number_id} not found")

        if not self.twilio.is_available():
            raise RuntimeError("Twilio not configured")

        result = self.twilio.send_sms(
            from_number=proxy.phone_number,
            to_number=session.homeowner_phone,
            body=body,
        )

        # Log the communication
        comm = MaskedCommunication(
            session_id=session.id,
            company_id=session.company_id,
            lead_id=session.lead_id,
            comm_type="sms",
            direction="rep_to_homeowner",
            from_number=session.rep_phone,
            to_number=session.homeowner_phone,
            proxy_number=proxy.phone_number,
            twilio_message_sid=result["message_sid"],
            message_body=body,
        )
        await self.comms_repo.create(comm)

        logger.info(
            "Sent outbound SMS",
            message_sid=result["message_sid"],
            session_id=str(session_id),
        )
        return result

    # ── Call Status Callback ──────────────────────────────────────────────

    async def handle_call_status(
        self, call_sid: str, call_status: str, duration: int
    ) -> None:
        """Handle Twilio call status callback — update communication record."""
        await self.comms_repo.update_call_status(call_sid, call_status, duration)
        logger.info(
            "Updated call status",
            call_sid=call_sid,
            status=call_status,
            duration=duration,
        )

    # ── Recording Callback ────────────────────────────────────────────────

    async def handle_recording_ready(
        self, call_sid: str, recording_url: str, recording_sid: str
    ) -> None:
        """
        Handle Twilio recording status callback.

        Pipeline:
        1. Update masked_communication with recording info
        2. Download recording from Twilio
        3. Upload to S3
        4. Create a Call record (for Shunya analysis)
        5. Submit to Shunya via process_call()
        6. Update masked_communication with call_id link

        Steps 2-6 are documented for integration — the actual S3/Shunya
        calls require importing existing services (CallService, S3Service,
        ShoonyaClient) which should be done during integration into the
        actual Otto-Backend codebase.
        """
        # Step 1: Update recording info on the masked_communication record
        # Twilio recording URLs need .mp3 appended for the actual file
        full_recording_url = f"{recording_url}.mp3"

        await self.comms_repo.update_recording(
            call_sid=call_sid,
            recording_url=full_recording_url,
            recording_sid=recording_sid,
        )

        logger.info(
            "Recording ready — linked to masked communication",
            call_sid=call_sid,
            recording_sid=recording_sid,
        )

        # ── Steps 2-6: feed the masked call into the SAME analysis pipeline as
        # CTM/normal calls (S3 → Call → Shunya → job-complete webhook →
        # process_analysis → PendingActions → Action Center/Guidance/Notifications).
        # Reuses S3Service.upload_from_url + CallService.ingest_call/trigger_analysis.
        # No new tables, analysis, or pending-action logic.
        comm = await self.comms_repo.get_by_twilio_call_sid(call_sid)
        if not comm:
            logger.warning("No masked communication found for recording", call_sid=call_sid)
            return

        # Idempotency: if this recording was already processed into a Call, stop.
        # Makes duplicate Twilio callbacks / replays no-ops (no double S3, no
        # double Shunya submission).
        if comm.call_id:
            logger.info(
                "Recording already processed into a call — skipping",
                call_sid=call_sid,
                call_id=str(comm.call_id),
            )
            return

        try:
            from app.core.s3 import get_s3_service
            from app.services.call_service import CallService

            # Step 2: stream the Twilio recording into our audio bucket (Twilio
            # URLs are private; this also unblocks presigned playback).
            s3_service = get_s3_service()
            if not s3_service:
                logger.warning("S3 unavailable; masked recording stored but not analyzed",
                               call_sid=call_sid)
                return
            s3_key = s3_service.generate_s3_key(
                prefix="recordings", filename=f"masked_{call_sid}", extension="mp3"
            )
            # Twilio recordings are private — Basic auth (account SID + auth token)
            # is required to download the media file.
            auth_headers = None
            sid = getattr(self.twilio, "account_sid", None)
            token = getattr(self.twilio, "auth_token", None)
            if sid and token:
                import base64
                creds = base64.b64encode(f"{sid}:{token}".encode()).decode()
                auth_headers = {"Authorization": f"Basic {creds}"}
            audio_s3_url = await s3_service.upload_from_url(
                url=full_recording_url,
                s3_key=s3_key,
                content_type="audio/mpeg",
                metadata={
                    "masked_call_sid": call_sid,
                    "company_id": str(comm.company_id),
                    "lead_id": str(comm.lead_id) if comm.lead_id else None,
                },
                bucket_type="audio",
                headers=auth_headers,
            )

            # Step 3: create the Call record via the existing ingest flow.
            # A masked call is a rep↔homeowner conversation → sales_call (routes
            # analysis through the sales-rep flow; "masked_call" is not a valid
            # CallType). The masked origin is recorded in extra_metadata below.
            call_service = CallService(self.session)
            call = await call_service.ingest_call(
                company_id=comm.company_id,
                phone_number=comm.from_number,
                audio_url=audio_s3_url,
                call_type="sales_call",
            )

            # Link to the masked comm's actual lead + owning rep so the
            # materialized tasks land on the right lead and the rep owns them
            # (process_analysis uses handled_by_user_id as the task owner).
            rep_user_id = None
            try:
                session = await self.session_repo.get_by_id(comm.session_id)
                rep_user_id = getattr(session, "rep_user_id", None) if session else None
            except Exception as e:
                logger.warning(f"Could not resolve rep for masked call: {e}", call_sid=call_sid)

            call_orm = call  # domain Call; update via repo
            if comm.lead_id:
                call_orm.lead_id = comm.lead_id
            if rep_user_id:
                call_orm.handled_by_user_id = rep_user_id
            meta = dict(getattr(call_orm, "extra_metadata", None) or {})
            meta["masked_call_sid"] = call_sid
            meta["interaction_type"] = "masked_call"
            call_orm.extra_metadata = meta
            call = await call_service.call_repo.update(call_orm.id, call_orm)

            # Step 4 (link back) BEFORE triggering analysis: persist call_id on the
            # masked comm so a retry sees it as processed (idempotency closes here).
            await self.comms_repo.update_recording(
                call_sid=call_sid,
                recording_url=full_recording_url,
                recording_sid=recording_sid,
                audio_url=audio_s3_url,
                call_id=call.id,
            )
            await self.session.commit()

            # Step 5: trigger Shunya analysis (submits with the job-complete webhook
            # → existing CALL branch → process_analysis → PendingActions). Non-fatal.
            try:
                await call_service.trigger_analysis(call.id)
            except Exception as e:
                logger.error(f"Failed to trigger analysis for masked call {call.id}: {e}")
                # Non-critical: call + recording persisted; analysis can be retried.

            logger.info(
                "Masked recording processed into analyzed call",
                call_sid=call_sid,
                call_id=str(call.id),
                lead_id=str(comm.lead_id) if comm.lead_id else None,
                owner_id=str(rep_user_id) if rep_user_id else None,
            )
        except Exception as e:
            # Any failure here leaves Step-1 linkage intact and unprocessed
            # (comm.call_id still null) → retryable on the next callback, no
            # orphan Call linked.
            logger.error(
                f"Failed to process masked recording into call: {e}",
                call_sid=call_sid,
                exc_info=True,
            )

    # ── Bridge Call TwiML (for outbound two-leg bridge) ───────────────────

    async def get_bridge_twiml(self, session_id: UUID) -> str:
        """
        Generate TwiML for the second leg of an outbound call bridge.

        Called by Twilio when the rep answers the first leg.
        Returns TwiML that dials the homeowner.
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Session not found.</Say></Response>'

        proxy = await self.proxy_number_repo.get_by_id(session.proxy_number_id)
        proxy_phone = proxy.phone_number if proxy else ""

        # Recording consent disclosure (500ms timeout — Twilio drops slow TwiML)
        recording_say = await self._get_recording_disclosure(session.company_id)

        webhook_base = self._webhook_base_url()
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"{recording_say}"
            f'<Dial callerId="{proxy_phone}" '
            f'record="record-from-answer-dual" '
            f'recordingStatusCallback="{webhook_base}/api/v1/webhooks/twilio/recording-status" '
            f'recordingStatusCallbackEvent="completed">'
            f"<Number>{session.homeowner_phone}</Number>"
            "</Dial>"
            "</Response>"
        )
        return twiml

    # ── Conversation Thread ───────────────────────────────────────────────

    async def get_conversation(
        self, session_id: UUID, skip: int = 0, limit: int = 50
    ) -> List[MaskedCommunication]:
        """Get conversation thread for mobile app display."""
        return await self.comms_repo.get_by_session(session_id, skip, limit)

    # ── Recording Disclosure ──────────────────────────────────────────────

    async def _get_recording_disclosure(self, company_id: UUID) -> str:
        """
        Look up recording consent disclosure setting for a company.

        Uses a 500ms timeout to prevent blocking the TwiML response.
        Falls back to no disclosure (empty string) on timeout or error.
        """
        try:
            integration = await asyncio.wait_for(
                self.ci_repo.get_by_company_id(company_id),
                timeout=0.5,
            )
            if integration and getattr(integration, "recording_disclosure_enabled", True):
                return '<Say voice="alice">This call may be recorded for quality purposes.</Say>'
        except asyncio.TimeoutError:
            logger.warning(
                "Recording disclosure lookup timed out",
                company_id=str(company_id),
            )
        except Exception:
            pass  # Default to no disclosure on lookup failure
        return ""

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _webhook_base_url() -> str:
        """Get the base URL for webhook callbacks."""
        return (settings.API_URL or "").rstrip("/")
