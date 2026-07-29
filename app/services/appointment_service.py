"""
Appointment service.

Provides business logic for managing appointments:
- CRUD operations
- Listing by company, lead, or assigned sales rep
- Enriched responses with contact and user details
"""
import asyncio
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.s3 import presign_audio_url_for_playback
from app.domain.models.appointment import Appointment
from app.domain.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AppointmentInsightSummary,
    AppointmentAnalysis,
    AppointmentContextResponse,
    AppointmentContextFollowUpDraft,
    AppointmentContextFollowUpSection,
    CallSummaryItem,
    ContactCardInfo,
    PropertyBrief,
    LeadContextInfo,
    AggregatedObjections,
    PendingActionItem,
    AIBriefing,
    PendingActionDetail,
    ObjectionDetail,
    ComplianceStageDetail,
)
from app.domain.enums import AppointmentOutcome, PendingActionStatus, LeadStatus, DealStatus, PipelineStage
from app.domain.schemas.appointment_details import (
    AppointmentDetailsResponse,
    AppointmentOverview,
)
from app.infrastructure.repositories.appointment import AppointmentRepository
from app.infrastructure.repositories.contact import ContactRepository
from app.domain.users.repository import UserRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.database.models.follow_up_otto import FollowUpOttoORM
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.services.property_text_extractor import extract_property_from_text
from app.core.datetime_utils import isoformat_utc

logger = get_logger(__name__)

OUTCOME_TO_STATUS = {
    "pending": "In Progress",
    None: "In Progress",
    "won": "Won",
    "lost": "Lost",
    "no_show": "No Show",
    "rescheduled": "Rescheduled",
}

# Values Shunya uses for "no data" in property_details — treated as absent.
_PROPERTY_UNKNOWN = {None, "", "unknown", "Unknown", "UNKNOWN"}


def _clean(value):
    """Normalize a property_details scalar: drop Shunya's 'unknown'/empty sentinels."""
    if isinstance(value, str) and value.strip() in _PROPERTY_UNKNOWN:
        return None
    return value if value not in _PROPERTY_UNKNOWN else None


def _str_list(value) -> list:
    """Coerce a value into a clean list of non-empty strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v and str(v).strip()]
    return []


def _format_service_address(structured) -> Optional[str]:
    """Build a human-readable address from a service_address_structured dict.

    Tolerant of Shunya 'unknown'/empty sentinels (via `_clean`) and missing parts;
    returns None when nothing usable is present. Shape: "line1, city, state postal".
    """
    if not isinstance(structured, dict):
        return None
    line1 = _clean(structured.get("line1"))
    city = _clean(structured.get("city"))
    state = _clean(structured.get("state"))
    postal = _clean(structured.get("postal_code"))

    # "state postal" reads as one token (e.g. "AZ 85338"); the rest are comma-joined.
    region = " ".join(p for p in (state, postal) if p) or None
    parts = [p for p in (line1, city, region) if p]
    return ", ".join(parts) if parts else None


def _select_brief_source(candidates: list[dict]) -> Optional[dict]:
    """Pick the call whose analysis should drive the property brief.

    Preference order (each restricted to calls that actually carry usable detail):
      1. latest CSR call (call_type == 'csr_call')
      2. latest call of any type
    Sorts defensively newest-first so callers needn't pre-sort.

    "Usable detail" is broader than structured property_details: Shunya frequently
    leaves property_details/customer_details null while still extracting
    service_requested, a rich summary, and a service address. Those alone make an
    actionable brief, so they count as a valid source.
    """
    def _has_detail(c: dict) -> bool:
        return bool(
            c.get("property_details")
            or c.get("customer_details")
            or _clean(c.get("service_requested"))
            or _clean(c.get("summary"))
            or c.get("service_address_structured")
        )

    def _key(c: dict):
        from datetime import timezone as _tz
        return c.get("call_date") or datetime.min.replace(tzinfo=_tz.utc)

    ordered = sorted(candidates, key=_key, reverse=True)
    csr = [c for c in ordered if c.get("call_type") == "csr_call" and _has_detail(c)]
    if csr:
        return csr[0]
    any_with = [c for c in ordered if _has_detail(c)]
    return any_with[0] if any_with else None


def build_property_brief(candidates: list[dict]) -> PropertyBrief:
    """Assemble a typed PropertyBrief from CSR call analyses (pure, no I/O).

    `candidates` is a newest-first list of dicts with keys: call_id, call_date,
    call_type, property_details (dict|None), customer_details (dict|None),
    service_requested, qualification_status, booking_status, summary.

    Returns an empty brief (has_data=False) when no call carries property/customer
    detail. Tolerant of partial blobs and Shunya 'unknown' sentinels.
    """
    source = _select_brief_source(candidates)
    if source is None:
        return PropertyBrief(has_data=False)

    pd = source.get("property_details") or {}
    cd = source.get("customer_details") or {}
    if not isinstance(pd, dict):
        pd = {}
    if not isinstance(cd, dict):
        cd = {}

    current_issues = _str_list(pd.get("current_issues"))
    problem_summary = (current_issues[0] if current_issues else None) or _clean(source.get("summary"))

    # Fallback extraction: Shunya leaves property_details null in production, but
    # the summary/service_requested text usually carries roof type, stories, size,
    # etc. Mine those deterministically and use them ONLY to fill fields Shunya
    # didn't provide (real property_details always wins when present).
    text_pd = extract_property_from_text(
        source.get("service_requested"), source.get("summary")
    )

    def _pd(field: str):
        """Prefer Shunya's structured value; fall back to text-extracted."""
        return _clean(pd.get(field)) or text_pd.get(field)

    # Decision makers may live under customer_details in a few shapes.
    decision_makers = _str_list(cd.get("decision_makers"))
    if not decision_makers:
        decision_makers = _str_list(cd.get("decision_maker"))

    return PropertyBrief(
        service_requested=_clean(source.get("service_requested")),
        problem_summary=problem_summary,
        current_issues=current_issues,
        property_size=_pd("property_size"),
        stories=_pd("stories"),
        roof_type=_pd("roof_type"),
        roof_age_years=pd.get("roof_age_years"),
        hoa_status=_pd("hoa_status"),
        hoa_name=_clean(pd.get("hoa_name")),
        gated_community=pd.get("gated_community"),
        gate_access=_clean(pd.get("gate_access")),
        property_access_notes=_clean(pd.get("property_access_notes")),
        pets=_clean(pd.get("pets")),
        pet_notes=_clean(pd.get("pet_notes")),
        decision_makers=decision_makers,
        service_address=_format_service_address(source.get("service_address_structured")),
        qualification_status=_clean(source.get("qualification_status")),
        booking_status=_clean(source.get("booking_status")),
        source_call_id=source.get("call_id"),
        source_call_date=source.get("call_date"),
        has_data=True,
    )


class AppointmentService:
    """Service for appointment-related operations."""

    # Pipeline → Appointments List View, audit issue #37 (APPT-STAGE):
    # how long after a scheduled appointment's start (or end) do we wait
    # before assuming a still-"pending" outcome with no recording is a
    # no_show. 24h is conservative — covers reps who finish late, drop
    # the recording the next morning, etc.
    STALE_PENDING_GRACE_HOURS = 24

    def __init__(self, session: AsyncSession):
        self.session = session
        self.appointment_repo = AppointmentRepository(session)
        self.contact_repo = ContactRepository(session)
        self.user_repo = UserRepository(session)
        self.analysis_repo = CallAnalysisRepository(session)
        self.call_repo = CallRepository(session)
        self.lead_repo = LeadRepository(session)
        self.pending_action_repo = PendingActionRepository(session)

    async def transition_stale_pending_appointments(
        self,
        company_id: UUID,
        grace_hours: int = STALE_PENDING_GRACE_HOURS,
    ) -> int:
        """
        Sweep stale "pending" appointments to ``no_show`` for a single tenant.

        Resolves audit issue #37 (Pipeline → Appointments List View):
        appointments with ``outcome == "pending"`` whose scheduled time is
        more than ``grace_hours`` in the past, and which have no recording
        uploaded, are flipped to ``no_show``. Appointments that have a
        recording (``recording_status``) or whose analysis is still in
        flight / failed are intentionally left alone — those are operator-
        triage cases, not silent no-shows.

        Returns the number of rows updated.

        Designed to be safe to call repeatedly (the WHERE clause is the
        idempotency gate). The list endpoints invoke this opportunistically
        so the UI converges without waiting for a separate cron worker.
        """
        from datetime import timedelta, timezone as _tz
        from sqlalchemy import update, or_, and_

        from app.infrastructure.database.models.appointment import AppointmentORM

        cutoff = datetime.now(_tz.utc) - timedelta(hours=grace_hours)

        try:
            stmt = (
                update(AppointmentORM)
                .where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.outcome == AppointmentOutcome.PENDING.value,
                    AppointmentORM.scheduled_start < cutoff,
                    or_(
                        AppointmentORM.recording_status.is_(None),
                        AppointmentORM.recording_status == "",
                    ),
                    or_(
                        AppointmentORM.analysis_status.is_(None),
                        and_(
                            AppointmentORM.analysis_status != "completed",
                            AppointmentORM.analysis_status != "failed",
                            AppointmentORM.analysis_status != "processing",
                        ),
                    ),
                )
                .values(outcome=AppointmentOutcome.NO_SHOW.value)
            )
            result = await self.session.execute(stmt)
            updated = result.rowcount or 0
            if updated:
                await self.session.commit()
                logger.info(
                    "Transitioned stale-pending appointments to no_show",
                    company_id=str(company_id),
                    updated=updated,
                )
            return updated
        except Exception as e:
            # Maintenance must never break the list endpoint. Roll back the
            # implicit transaction and continue — the list will still render,
            # just without the cleanup pass for this request.
            logger.warning(
                "Could not transition stale-pending appointments",
                company_id=str(company_id),
                error=str(e),
            )
            try:
                await self.session.rollback()
            except Exception:
                pass
            return 0

    async def get_by_id(self, appointment_id: UUID) -> Optional[Appointment]:
        """Get appointment by ID."""
        return await self.appointment_repo.get_by_id(appointment_id)

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """Get all appointments for a company."""
        return await self.appointment_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        """
        Get all appointments for a company assigned to a specific sales rep.

        Args:
            company_id: Company/tenant ID
            assigned_rep_id: Assigned sales rep user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
        """
        return await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )

    async def get_by_lead(
        self,
        lead_id: UUID,
    ) -> Optional[Appointment]:
        """Get appointment by associated lead ID."""
        return await self.appointment_repo.get_by_lead_id(lead_id)

    async def _sync_reminders_safe(self, appointment: Appointment) -> None:
        """Sync appointment reminders; non-fatal on failure."""
        try:
            from app.services.appointment_reminder_service import sync_appointment_reminders
            await sync_appointment_reminders(self.session, appointment)
        except Exception as e:
            logger.error(f"Failed to sync appointment reminders: {e}")

    async def create(self, appointment: Appointment) -> Appointment:
        """Create a new appointment from a domain model."""
        try:
            created = await self.appointment_repo.create(appointment)
            await self._sync_reminders_safe(created)
            return created
        except Exception as e:
            logger.error(f"Error creating appointment: {e}")
            raise

    async def create_from_schema(
        self,
        data: AppointmentCreate,
    ) -> Appointment:
        """Create a new appointment from an API schema."""
        try:
            appointment = Appointment(
                **data.model_dump(),
            )
            created = await self.appointment_repo.create(appointment)
            await self._sync_reminders_safe(created)
            return created
        except Exception as e:
            logger.error(f"Error creating appointment from schema: {e}")
            raise

    async def update(
        self,
        appointment_id: UUID,
        data: AppointmentUpdate,
    ) -> Optional[Appointment]:
        """Update an existing appointment from an API schema."""
        try:
            existing = await self.appointment_repo.get_by_id(appointment_id)
            if not existing:
                return None

            update_dict = data.model_dump(exclude_unset=True)
            assigned_rep_id = update_dict.get("assigned_rep_id")
            for key, value in update_dict.items():
                setattr(existing, key, value)
            existing.mark_updated()

            # If someone sets/changes the assigned rep via the appointment API while
            # the lead is still in `booked`, we must also advance `lead.pipeline_stage`
            # so the pipeline progress bar moves to "Appointment scheduled".
            #
            # This keeps UI consistent when the frontend updates the Appointment row
            # directly instead of calling the lead stage transition endpoint.
            if assigned_rep_id:
                from app.infrastructure.database.models.lead import LeadORM
                from sqlalchemy import select

                lead_orm_result = await self.session.execute(
                    select(LeadORM).where(LeadORM.id == existing.lead_id)
                )
                lead_orm = lead_orm_result.scalar_one_or_none()
                if lead_orm and lead_orm.pipeline_stage == PipelineStage.BOOKED.value:
                    lead_orm.pipeline_stage = PipelineStage.APPOINTMENT.value
                    # Keep lead-level assignment in sync for consistency
                    lead_orm.assigned_rep_id = assigned_rep_id
                    # status/deal_status already typically match booked, but set defensively
                    if lead_orm.status != LeadStatus.QUALIFIED_BOOKED.value:
                        lead_orm.status = LeadStatus.QUALIFIED_BOOKED.value
                    if lead_orm.deal_status != DealStatus.BOOKED.value:
                        lead_orm.deal_status = DealStatus.BOOKED.value

            updated = await self.appointment_repo.update(appointment_id, existing)
            if updated is not None:
                # Re-sync reminders: handles reschedule, outcome change, and rep
                # (re)assignment uniformly (cancels stale rows + recreates).
                await self._sync_reminders_safe(updated)
            return updated
        except Exception as e:
            logger.error(f"Error updating appointment: {e}")
            raise

    async def delete(self, appointment_id: UUID) -> bool:
        """Delete an appointment."""
        try:
            try:
                from app.services.appointment_reminder_service import cancel_appointment_reminders
                await cancel_appointment_reminders(self.session, appointment_id)
            except Exception as e:
                logger.error(f"Failed to cancel appointment reminders on delete: {e}")
            return await self.appointment_repo.delete(appointment_id)
        except Exception as e:
            logger.error(f"Error deleting appointment: {e}")
            raise

    async def get_appointment_counts(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
    ) -> Dict[str, int]:
        """
        Get appointment counts: total today, pending, and closed.

        Args:
            company_id: Company UUID
            assigned_rep_id: Optional filter by assigned sales rep

        Returns:
            Dictionary with total_today, pending, and closed counts
        """
        total_today = await self.appointment_repo.count_today(company_id, assigned_rep_id)
        pending = await self.appointment_repo.count_pending(company_id, assigned_rep_id)
        closed = await self.appointment_repo.count_closed(company_id, assigned_rep_id)
        return {
            "total_today": total_today,
            "pending": pending,
            "closed": closed,
        }

    async def get_today_summary(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        utc_start: datetime,
        utc_end: datetime,
    ) -> dict:
        """
        Get appointments and counts for a rep on a specific date.

        Args:
            company_id: Company UUID
            assigned_rep_id: Sales rep user ID
            utc_start: Start of day in UTC
            utc_end: End of day in UTC

        Returns:
            Dict with 'appointments' list and 'counts' dict
        """
        appointments = await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            start_date=utc_start,
            end_date=utc_end,
        )

        enriched = [
            await self._enrich_appointment_response(appt, include_full_details=False)
            for appt in appointments
        ]

        total = await self.appointment_repo.count_for_date_range(
            company_id, assigned_rep_id, utc_start, utc_end
        )
        pending = await self.appointment_repo.count_pending_for_date_range(
            company_id, assigned_rep_id, utc_start, utc_end
        )
        closed = await self.appointment_repo.count_closed_for_date_range(
            company_id, assigned_rep_id, utc_start, utc_end
        )

        return {
            "appointments": enriched,
            "counts": {
                "total_today": total,
                "pending": pending,
                "closed": closed,
            },
        }

    async def _fetch_phases(self, call_id: UUID, company_id: UUID) -> Optional[dict]:
        """
        Fetch live conversation phases from Shunya for a call.

        Returns the phases dict or None if unavailable.
        """
        try:
            shoonya = get_shoonya_client()
            if not shoonya.is_available():
                return None
            payload = await shoonya.get_call_conversation_phases(
                call_id=str(call_id),
                company_id=str(company_id),
            )
            phases = payload.get("phases")
            return phases if phases is not None else payload
        except Exception as e:
            logger.warning(f"Could not fetch phases for call {call_id}: {e}")
            return None

    async def _build_appointment_insights(self, interaction_id: UUID) -> Optional[AppointmentInsightSummary]:
        """
        Build comprehensive appointment insights from call analysis.

        Args:
            interaction_id: Call ID (from appointment.interaction_id)

        Returns:
            AppointmentInsightSummary with full recording analysis or None if not available
        """
        try:
            # Get call analysis
            analysis = await self.analysis_repo.get_by_call_id(interaction_id)
            if not analysis:
                return None

            # Build pending actions
            pending_actions = []
            if analysis.pending_actions:
                for action_dict in analysis.pending_actions:
                    pending_actions.append(PendingActionDetail(
                        type=action_dict.get("type", ""),
                        owner=action_dict.get("owner", ""),
                        raw_text=action_dict.get("raw_text", ""),
                        due_at=action_dict.get("due_at"),
                        confidence=action_dict.get("confidence"),
                        contact_method=action_dict.get("contact_method"),
                    ))

            # Build objections with details
            from app.services.pending_action_service import response_suggestions_for_objection
            objection_details = []
            if analysis.objections and analysis.objection_texts:
                for i, obj in enumerate(analysis.objections):
                    obj_text = analysis.objection_texts[i] if i < len(analysis.objection_texts) else ""
                    objection_details.append(ObjectionDetail(
                        category_id=i + 1,
                        category_text=obj.value if hasattr(obj, 'value') else str(obj),
                        objection_text=obj_text,
                        overcome=False,  # Not available in current data
                        severity="medium",  # Default
                        confidence_score=0.8,  # Default
                        # Recover dropped suggestions from the full Shunya payload.
                        response_suggestions=response_suggestions_for_objection(
                            getattr(analysis, "raw_analysis", None), obj_text
                        ),
                    ))

            # Build SOP stages
            sop_stages = {}
            for stage in analysis.sop_stages_completed or []:
                sop_stages[stage] = ComplianceStageDetail(score=1.0, issues=[])
            for stage in analysis.sop_stages_missed or []:
                sop_stages[stage] = ComplianceStageDetail(score=0.0, issues=["Stage not completed"])

            # Build BANT scores
            bant_scores = {}
            if analysis.bant_need_score is not None:
                bant_scores["need"] = analysis.bant_need_score
            if analysis.bant_budget_score is not None:
                bant_scores["budget"] = analysis.bant_budget_score
            if analysis.bant_authority_score is not None:
                bant_scores["authority"] = analysis.bant_authority_score
            if analysis.bant_timeline_score is not None:
                bant_scores["timeline"] = analysis.bant_timeline_score

            # Calculate lead score (0-100 scale)
            lead_score = None
            lead_band = None
            if analysis.qualification_overall_score is not None:
                lead_score = int(analysis.qualification_overall_score * 100)
                if lead_score >= 80:
                    lead_band = "hot"
                elif lead_score >= 60:
                    lead_band = "warm"
                elif lead_score >= 40:
                    lead_band = "cold"
                else:
                    lead_band = "unqualified"

            return AppointmentInsightSummary(
                # Summary section
                summary=analysis.summary,
                key_points=list(analysis.key_points) if analysis.key_points else [],
                pending_actions=pending_actions,
                sentiment_score=analysis.sentiment_score,
                # Objections section
                objections=objection_details,
                objections_total_count=analysis.objections_total_count or len(objection_details),
                # Compliance section
                sop_compliance_score=analysis.sop_compliance_score,
                sop_stages=sop_stages,
                sop_positive_behaviors=list(analysis.sop_compliance_positive_behaviors) if analysis.sop_compliance_positive_behaviors else [],
                sop_issues=list(analysis.sop_compliance_issues) if analysis.sop_compliance_issues else [],
                # Qualification section
                qualification_overall_score=analysis.qualification_overall_score,
                bant_scores=bant_scores,
                qualification_status=analysis.qualification_status,
                # Lead score section
                lead_total_score=lead_score,
                lead_band=lead_band,
                # Legacy fields
                action_items=list(analysis.action_items) if analysis.action_items else [],
                follow_up_required=analysis.follow_up_required,
                follow_up_reason=analysis.follow_up_reason,
            )
        except Exception as e:
            logger.error(f"Error building appointment insights: {e}", exc_info=True)
            return None

    async def _enrich_appointment_response(
        self,
        appointment: Appointment,
        include_full_details: bool = False,
    ) -> AppointmentResponse:
        """
        Enrich appointment with contact and user details, and recording insights.

        Args:
            appointment: Appointment domain model
            include_full_details: If True, includes full contact_details and assigned_rep_details

        Returns:
            Enriched AppointmentResponse with insights if recording analysis exists
        """
        response_data = AppointmentResponse.model_validate(appointment).model_dump()

        # Get contact details
        if appointment.contact_card_id:
            contact_card = await self.contact_repo.get_by_id(appointment.contact_card_id)
            if contact_card:
                first_name = contact_card.first_name or ""
                last_name = contact_card.last_name or ""
                response_data["appointment_name"] = f"{first_name} {last_name}".strip() or None

                # Fall back to contact card address if appointment location is missing
                if not response_data.get("location_address"):
                    parts = [contact_card.address, contact_card.city, contact_card.state, contact_card.postal_code]
                    fallback = ", ".join(p for p in parts if p)
                    if fallback:
                        response_data["location_address"] = fallback

                if include_full_details:
                    response_data["contact_details"] = {
                        "id": str(contact_card.id),
                        "first_name": contact_card.first_name,
                        "last_name": contact_card.last_name,
                        "email": contact_card.email,
                        "primary_phone": contact_card.primary_phone,
                        "secondary_phone": contact_card.secondary_phone,
                        "address": contact_card.address,
                        "city": contact_card.city,
                        "state": contact_card.state,
                        "postal_code": contact_card.postal_code,
                    }

        # Get assigned rep details
        if appointment.assigned_rep_id:
            rep_user = await self.user_repo.get_by_id(appointment.assigned_rep_id)
            if rep_user:
                first_name = rep_user.first_name or ""
                last_name = rep_user.last_name or ""
                response_data["sales_rep_name"] = f"{first_name} {last_name}".strip() or None

                if include_full_details:
                    response_data["assigned_rep_details"] = {
                        "id": str(rep_user.id),
                        "email": rep_user.email,
                        "first_name": rep_user.first_name,
                        "last_name": rep_user.last_name,
                        "role": rep_user.role.value if hasattr(rep_user.role, 'value') else str(rep_user.role),
                        "is_active": rep_user.is_active,
                    }

        # Fetch insights and conversation phases in parallel
        # (phases API takes ~14s; running concurrently avoids Heroku 30s timeout)
        async def _noop():
            return None

        insights_coro = (
            self._build_appointment_insights(appointment.interaction_id)
            if appointment.interaction_id
            else _noop()
        )
        phases_coro = (
            self._fetch_phases(
                appointment.interaction_id or appointment.id,
                appointment.company_id,
            )
            if include_full_details
            else _noop()
        )

        insights, phases = await asyncio.gather(insights_coro, phases_coro)

        if insights:
            response_data["insights"] = insights.model_dump()
        if phases:
            response_data["phases"] = phases

        return AppointmentResponse(**response_data)

    async def get_enriched_by_id(self, appointment_id: UUID) -> Optional[AppointmentResponse]:
        """
        Get appointment by ID with enriched contact and rep details.

        Args:
            appointment_id: Appointment UUID

        Returns:
            Enriched AppointmentResponse or None if not found
        """
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return None

        return await self._enrich_appointment_response(appointment, include_full_details=True)

    async def list_enriched_by_company(
        self,
        company_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        past_only: bool = False,
        skip: int = 0,
        limit: int = 100,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AppointmentResponse]:
        """
        Get all appointments for a company with enriched names.

        Args:
            company_id: Company UUID
            start_date: Filter appointments scheduled on or after this date
            end_date: Filter appointments scheduled on or before this date
            past_only: If True, only return appointments with scheduled_start in the past
            outcome: Optional outcome filter (pending, won, lost, no_show, rescheduled)
            search: Optional search on contact name/phone, rep name, location (whitespace tokens ANDed)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of enriched AppointmentResponse objects
        """
        # #37: opportunistic stale-pending sweep before the read so the
        # response reflects the freshest state. Idempotent + best-effort.
        await self.transition_stale_pending_appointments(company_id=company_id)

        appointments = await self.appointment_repo.get_by_company(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            past_only=past_only,
            skip=skip,
            limit=limit,
            outcome=outcome,
            search=search,
        )

        return [
            await self._enrich_appointment_response(appointment, include_full_details=False)
            for appointment in appointments
        ]

    async def list_enriched_by_assigned_rep(
        self,
        company_id: UUID,
        assigned_rep_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        past_only: bool = False,
        skip: int = 0,
        limit: int = 100,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AppointmentResponse]:
        """
        Get all appointments for a company assigned to a specific sales rep with enriched names.

        Args:
            company_id: Company UUID
            assigned_rep_id: Assigned sales rep user ID
            start_date: Filter appointments scheduled on or after this date
            end_date: Filter appointments scheduled on or before this date
            past_only: If True, only return appointments with scheduled_start in the past
            outcome: Optional outcome filter (pending, won, lost, no_show, rescheduled)
            search: Optional search on contact name/phone, rep name, location (whitespace tokens ANDed)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of enriched AppointmentResponse objects
        """
        # #37: opportunistic stale-pending sweep before the read.
        await self.transition_stale_pending_appointments(company_id=company_id)

        appointments = await self.appointment_repo.get_by_assigned_rep(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            start_date=start_date,
            end_date=end_date,
            past_only=past_only,
            skip=skip,
            limit=limit,
            outcome=outcome,
            search=search,
        )

        return [
            await self._enrich_appointment_response(appointment, include_full_details=False)
            for appointment in appointments
        ]

    async def list_upcoming_appointments(
        self,
        company_id: UUID,
        assigned_rep_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AppointmentResponse]:
        """
        Get upcoming appointments (future, pending status only).

        Returns appointments with:
        - scheduled_start >= now (future)
        - outcome is None or 'pending'
        - Sorted by scheduled_start ASC (soonest first)
        - Enriched with contact and rep names

        Args:
            company_id: Company UUID
            assigned_rep_id: Optional filter by assigned sales rep
            skip: Pagination offset
            limit: Max results

        Returns:
            List of enriched upcoming appointments
        """
        appointments = await self.appointment_repo.get_upcoming(
            company_id=company_id,
            assigned_rep_id=assigned_rep_id,
            skip=skip,
            limit=limit,
        )

        return [
            await self._enrich_appointment_response(appointment, include_full_details=False)
            for appointment in appointments
        ]

    async def get_enriched_by_lead(self, lead_id: UUID) -> Optional[AppointmentResponse]:
        """
        Get appointment by lead ID with enriched names.

        Args:
            lead_id: Lead UUID

        Returns:
            Enriched AppointmentResponse or None if not found
        """
        appointment = await self.appointment_repo.get_by_lead_id(lead_id)
        if not appointment:
            return None

        return await self._enrich_appointment_response(appointment, include_full_details=False)

    async def get_appointment_insights(self, appointment_id: UUID) -> Dict[str, Any]:
        """
        Get insights for an appointment.

        First checks appointment's own analysis fields (new flow where analysis is saved
        directly to the appointments table). Falls back to interaction_id → CallAnalysisORM
        (old flow) if no direct analysis is found.

        Args:
            appointment_id: Appointment UUID

        Returns:
            Dictionary with appointment_id, status, and insights
        """
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return {
                "appointment_id": str(appointment_id),
                "status": "not_found",
                "insights": None,
            }

        # NEW FLOW: Check if analysis is stored directly on the appointment
        if appointment.summary:
            extra = appointment.extra_metadata or {}
            analysis_meta = extra.get("analysis", {}) if isinstance(extra, dict) else {}

            objections = appointment.objections or []

            insights = {
                "summary": appointment.summary or "",
                "key_points": analysis_meta.get("key_points") or [],
                "sop_stages_completed": analysis_meta.get("sop_stages_completed") or [],
                "sop_stages_missed": analysis_meta.get("sop_stages_missed") or [],
                "objections": objections,
                "objections_found": objections,
                "action_items": [a.get("raw_text", "") for a in (analysis_meta.get("pending_actions") or [])],
                "tasks": [a.get("raw_text", "") for a in (analysis_meta.get("pending_actions") or [])],
                "follow_up_required": None,
                "follow_up_reason": None,
                "sentiment": analysis_meta.get("sentiment_score"),
                "sop_score": analysis_meta.get("sop_compliance_score"),
            }

            return {
                "appointment_id": str(appointment_id),
                "status": "completed",
                "insights": insights,
            }

        # OLD FLOW: Check interaction_id → CallAnalysisORM
        if not appointment.interaction_id:
            return {
                "appointment_id": str(appointment_id),
                "status": "not_found",
                "insights": None,
            }

        analysis = await self.analysis_repo.get_by_call_id(appointment.interaction_id)

        if not analysis:
            call = await self.call_repo.get_by_id(appointment.interaction_id)
            if call:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "pending",
                    "insights": None,
                }
            else:
                return {
                    "appointment_id": str(appointment_id),
                    "status": "not_found",
                    "insights": None,
                }

        objections = [
            obj.value if hasattr(obj, "value") else str(obj) for obj in analysis.objections
        ] if analysis.objections else []

        insights = {
            "summary": analysis.summary or "",
            "key_points": analysis.key_points or [],
            "sop_stages_completed": analysis.sop_stages_completed or [],
            "sop_stages_missed": analysis.sop_stages_missed or [],
            "objections": objections,
            "objections_found": objections,
            "action_items": analysis.action_items or [],
            "tasks": analysis.action_items or [],
            "follow_up_required": analysis.follow_up_required,
            "follow_up_reason": analysis.follow_up_reason,
            "sentiment": analysis.sentiment_score if analysis.sentiment_score is not None else None,
            "sop_score": analysis.sop_compliance_score if analysis.sop_compliance_score is not None else None,
        }

        return {
            "appointment_id": str(appointment_id),
            "status": analysis.status.value if hasattr(analysis.status, 'value') else str(analysis.status),
            "insights": insights,
        }

    async def get_appointment_details(
        self, appointment_id: UUID
    ) -> Optional[AppointmentDetailsResponse]:
        """
        Get appointment details for exec view: customer, rep, status, and overview
        (deal_size, deal_type, appointment_summary, sop_stages, appointment_booking).
        """
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return None

        # Customer name
        customer_name = "Unknown"
        if appointment.contact_card_id:
            contact = await self.contact_repo.get_by_id(appointment.contact_card_id)
            if contact:
                first = contact.first_name or ""
                last = contact.last_name or ""
                customer_name = f"{first} {last}".strip() or "Unknown"

        # Sales rep name
        sales_rep_name = "Unknown"
        if appointment.assigned_rep_id:
            rep_user = await self.user_repo.get_by_id(appointment.assigned_rep_id)
            if rep_user:
                first = rep_user.first_name or ""
                last = rep_user.last_name or ""
                sales_rep_name = f"{first} {last}".strip() or "Unknown"

        # Status (display string)
        outcome = getattr(appointment, "outcome", None)
        if isinstance(outcome, AppointmentOutcome):
            outcome = outcome.value if outcome else None
        status = OUTCOME_TO_STATUS.get(outcome, "In Progress")

        # Overview: deal_size, deal_type from lead or appointment.extra_metadata
        deal_size: Optional[float] = None
        deal_type: Optional[str] = None
        extra = getattr(appointment, "extra_metadata", None) or {}
        if isinstance(extra, dict):
            deal_size = extra.get("deal_size")
            if deal_size is not None and not isinstance(deal_size, (int, float)):
                deal_size = None
            deal_type = extra.get("deal_type") or extra.get("service_type") or extra.get("service_type_description")
        if deal_size is None or deal_type is None:
            lead = await self.lead_repo.get_by_id(appointment.lead_id)
            if lead:
                if deal_size is None and getattr(lead, "deal_size", None) is not None:
                    deal_size = float(lead.deal_size)
                if not deal_type:
                    lead_extra = getattr(lead, "extra_metadata", None) or {}
                    if isinstance(lead_extra, dict):
                        deal_type = lead_extra.get("deal_type") or lead_extra.get("service_type")
        if not deal_type:
            deal_type = extra.get("service_type") or "Appointment"

        # Summary and SOP from call analysis (interaction_id = sales call for this appointment)
        appointment_summary: List[str] = []
        sop_stages_completed: List[str] = []
        sop_stages_missed: List[str] = []

        # Resolve which call to use for analysis
        analysis_call_id = appointment.interaction_id
        if not analysis_call_id and appointment.lead_id:
            # Fallback: find the most recent call linked to this lead
            from sqlalchemy import select as sa_select, desc
            from app.infrastructure.database.models.call import CallORM
            call_result = await self.session.execute(
                sa_select(CallORM.id)
                .where(CallORM.lead_id == appointment.lead_id)
                .order_by(desc(CallORM.created_at))
                .limit(1)
            )
            fallback_call_id = call_result.scalar_one_or_none()
            if fallback_call_id:
                analysis_call_id = fallback_call_id

        if analysis_call_id:
            analysis = await self.analysis_repo.get_by_call_id(analysis_call_id)
            if analysis:
                sop_stages_completed = list(analysis.sop_stages_completed or [])
                sop_stages_missed = list(analysis.sop_stages_missed or [])
                if analysis.summary:
                    # Prefer key_points as bullets; otherwise split summary by newlines/sentences
                    if analysis.key_points:
                        appointment_summary = list(analysis.key_points)
                    else:
                        parts = [s.strip() for s in analysis.summary.replace("\n", " ").split(". ") if s.strip()]
                        appointment_summary = [p + "." if not p.endswith(".") else p for p in parts] if parts else [analysis.summary]

        # Appointment booking: data from CSR call that booked this appointment (if we have interaction_id and it's a booking call)
        appointment_booking: Optional[Dict[str, Any]] = None
        if appointment.interaction_id:
            call = await self.call_repo.get_by_id(appointment.interaction_id)
            if call:
                analysis_booking = await self.analysis_repo.get_by_call_id(call.id)
                booking_data: Dict[str, Any] = {
                    "call_id": str(call.id),
                    "handled_by_user_id": str(call.handled_by_user_id) if call.handled_by_user_id else None,
                }
                if getattr(call, "created_at", None):
                    booking_data["date"] = isoformat_utc(call.created_at) if hasattr(call.created_at, "isoformat") else str(call.created_at)
                if analysis_booking and analysis_booking.summary:
                    booking_data["summary"] = analysis_booking.summary
                appointment_booking = booking_data

        overview = AppointmentOverview(
            deal_size=deal_size,
            deal_type=deal_type,
            appointment_summary=appointment_summary,
            sop_stages_completed=sop_stages_completed,
            sop_stages_missed=sop_stages_missed,
            appointment_booking=appointment_booking,
        )
        return AppointmentDetailsResponse(
            appointment_id=appointment.id,
            customer_name=customer_name,
            sales_rep_name=sales_rep_name,
            status=status,
            appointment_overview=overview,
        )

    async def get_appointment_context(self, appointment_id: UUID) -> Optional[AppointmentContextResponse]:
        """
        Get comprehensive appointment context for pre-meeting intelligence.

        Returns appointment with lead, contact, call history, objections,
        pending actions, and AI-generated briefing.

        Args:
            appointment_id: Appointment UUID

        Returns:
            AppointmentContextResponse with full context or None if not found
        """
        # 1. Get appointment
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            logger.warning(f"Appointment {appointment_id} not found")
            return None

        # Fire phases fetch early — it runs ~14s on Shunya, so start it now
        # Cap at 20s to stay within Heroku's 30s timeout
        phase_call_id = appointment.interaction_id or appointment.id

        async def _fetch_phases_with_timeout():
            try:
                return await asyncio.wait_for(
                    self._fetch_phases(phase_call_id, appointment.company_id),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Phases fetch timed out for call {phase_call_id}")
                return None
            except Exception as e:
                logger.warning(f"Phases fetch failed: {e}")
                return None

        phases_task = asyncio.create_task(_fetch_phases_with_timeout())

        # 2. Get lead (required)
        lead = await self.lead_repo.get_by_id(appointment.lead_id)
        if not lead:
            logger.error(f"Lead {appointment.lead_id} not found for appointment {appointment_id}")
            phases_task.cancel()
            return None

        # 3. Get contact card (required)
        contact_card = await self.contact_repo.get_by_id(appointment.contact_card_id)
        if not contact_card:
            logger.error(f"Contact card {appointment.contact_card_id} not found")
            phases_task.cancel()
            return None

        # 4. Get sales rep name
        sales_rep_name = None
        if appointment.assigned_rep_id:
            rep_user = await self.user_repo.get_by_id(appointment.assigned_rep_id)
            if rep_user:
                first = rep_user.first_name or ""
                last = rep_user.last_name or ""
                sales_rep_name = f"{first} {last}".strip() or None

        # 5. Get all calls for this lead
        calls = await self.call_repo.get_by_lead_id(lead.id)

        # 6. Batch fetch call analyses — single query instead of N+1
        call_ids = [call.id for call in calls]
        analyses_map = {}
        if call_ids:
            from app.infrastructure.database.models.analysis import CallAnalysisORM
            analyses_result = await self.session.execute(
                select(CallAnalysisORM).where(CallAnalysisORM.call_id.in_(call_ids))
            )
            for a in analyses_result.scalars().all():
                analyses_map[a.call_id] = a

        # 7. Batch fetch handler names — single query instead of N+1
        handler_ids = list({call.handled_by_user_id for call in calls if call.handled_by_user_id})
        handlers_map = {}
        if handler_ids:
            from app.infrastructure.database.models.user import UserORM
            handlers_result = await self.session.execute(
                select(UserORM).where(UserORM.id.in_(handler_ids))
            )
            for u in handlers_result.scalars().all():
                handlers_map[u.id] = f"{u.first_name or ''} {u.last_name or ''}".strip() or None

        # 8. Build conversation history
        conversation_history = []
        all_objections = []

        for call in calls:
            analysis = analyses_map.get(call.id)
            handler_name = handlers_map.get(call.handled_by_user_id) if call.handled_by_user_id else None

            call_item = CallSummaryItem(
                call_id=call.id,
                call_type=call.call_type.value if hasattr(call.call_type, 'value') else str(call.call_type),
                call_date=call.created_at,
                duration_seconds=call.duration_seconds,
                audio_url=presign_audio_url_for_playback(call.audio_url),
                summary=analysis.summary if analysis else None,
                key_points=list(analysis.key_points) if analysis and analysis.key_points else [],
                objections=list(analysis.objections) if analysis and analysis.objections else [],
                sentiment_score=analysis.sentiment_score if analysis else None,
                handled_by_name=handler_name,
                service_requested=analysis.service_requested if analysis else None,
                property_details=dict(analysis.property_details) if analysis and analysis.property_details else None,
            )
            conversation_history.append(call_item)

            if analysis and analysis.objections:
                all_objections.extend(analysis.objections)

        conversation_history.sort(key=lambda x: x.call_date, reverse=True)

        # 8b. Consolidated property brief from CSR call analyses (deterministic;
        # reuses analyses already loaded above — no extra query, no new AI).
        brief_candidates = []
        for call in calls:
            analysis = analyses_map.get(call.id)
            if not analysis:
                continue
            brief_candidates.append({
                "call_id": call.id,
                "call_date": call.created_at,
                "call_type": call.call_type.value if hasattr(call.call_type, "value") else str(call.call_type),
                "property_details": dict(analysis.property_details) if analysis.property_details else None,
                "customer_details": dict(analysis.customer_details) if analysis.customer_details else None,
                "service_requested": analysis.service_requested,
                "qualification_status": analysis.qualification_status,
                "booking_status": analysis.booking_status,
                "summary": analysis.summary,
                "service_address_structured": (
                    dict(analysis.service_address_structured)
                    if analysis.service_address_structured else None
                ),
            })
        brief_candidates.sort(key=lambda c: c["call_date"], reverse=True)
        property_brief = build_property_brief(brief_candidates)

        # 9. Aggregate objections
        objection_counts = {}
        for obj in all_objections:
            obj_str = obj.value if hasattr(obj, 'value') else str(obj)
            objection_counts[obj_str] = objection_counts.get(obj_str, 0) + 1

        unique_objections = list(objection_counts.keys())
        top_objections = sorted(unique_objections, key=lambda x: objection_counts[x], reverse=True)[:3]

        aggregated_objections = AggregatedObjections(
            unique_objections=unique_objections,
            objection_counts=objection_counts,
            top_objections=top_objections,
        )

        # 10. Get pending actions — batch fetch owner names
        pending_actions_domain = await self.pending_action_repo.get_by_lead(
            lead_id=lead.id,
            status=PendingActionStatus.PENDING,
        )

        owner_ids = list({a.owner_id for a in pending_actions_domain[:5] if a.owner_id})
        owners_map = {}
        if owner_ids:
            from app.infrastructure.database.models.user import UserORM
            owners_result = await self.session.execute(
                select(UserORM).where(UserORM.id.in_(owner_ids))
            )
            for u in owners_result.scalars().all():
                owners_map[u.id] = f"{u.first_name or ''} {u.last_name or ''}".strip() or None

        pending_actions = []
        for action in pending_actions_domain[:5]:
            pending_actions.append(PendingActionItem(
                id=action.id,
                raw_text=action.raw_text or "",
                priority=action.priority,
                status=action.status.value if hasattr(action.status, 'value') else str(action.status),
                due_at=action.due_at,
                owner_name=owners_map.get(action.owner_id) if action.owner_id else None,
            ))

        # 10. Generate AI briefing (Ask Otto with deterministic local fallback)
        ai_briefing: Optional[AIBriefing] = None
        try:
            # Primary path: Ask Otto, guarded by a hard timeout so we never hang
            # the context endpoint on Shunya latency.
            try:
                ai_briefing = await asyncio.wait_for(
                    self._generate_ai_briefing(
                        company_id=str(lead.company_id),
                        contact_name=f"{contact_card.first_name or ''} {contact_card.last_name or ''}".strip(),
                        appointment_date=appointment.scheduled_start,
                        lead_status=lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                        deal_size=lead.deal_size,
                        conversation_history=conversation_history[:3],  # Last 3 calls
                        top_objections=top_objections,
                        pending_actions=pending_actions[:3],  # Top 3 actions
                    ),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                logger.warning("AI briefing generation timed out (Ask Otto)")
                ai_briefing = None
            except Exception as e:
                logger.warning(f"AI briefing generation failed via Ask Otto: {e}")
                ai_briefing = None

            # Fallback path: deterministic brief from local data when Ask Otto is
            # unavailable or returns an empty briefing.
            if not ai_briefing or not ai_briefing.briefing_text.strip():
                ai_briefing = self._build_local_ai_briefing(
                    appointment=appointment,
                    contact_card=contact_card,
                    property_brief=property_brief,
                    conversation_history=conversation_history,
                    aggregated_objections=aggregated_objections,
                    pending_actions=pending_actions,
                )
        except Exception as e:
            # Absolute guardrail: ai_briefing must never cause the context endpoint
            # to fail; in worst case we fall back to None (current behavior).
            logger.error(f"Error building AI briefing (Ask Otto + fallback): {e}", exc_info=True)
            ai_briefing = None

        company_row = (
            await self.session.execute(
                select(CompanyORM).where(CompanyORM.id == lead.company_id)
            )
        ).scalar_one_or_none()

        manual_review_enabled = (
            bool(company_row.follow_up_manual_review_enabled) if company_row else False
        )

        pending_messages: List[AppointmentContextFollowUpDraft] = []
        if manual_review_enabled:
            otto_result = await self.session.execute(
                select(FollowUpOttoORM)
                .where(
                    FollowUpOttoORM.lead_id == lead.id,
                    FollowUpOttoORM.status == "proposed",
                )
                .order_by(FollowUpOttoORM.created_at.desc())
            )
            for o in otto_result.scalars().all():
                pending_messages.append(
                    AppointmentContextFollowUpDraft(
                        id=o.id,
                        action_type=o.action_type,
                        status=o.status,
                        message_content=o.message_content,
                        scheduled_at=o.scheduled_at,
                        created_at=o.created_at,
                        queue_type=o.queue_type,
                        attempt_number=o.attempt_number,
                    )
                )

        follow_up_section = AppointmentContextFollowUpSection(
            manual_review_enabled=manual_review_enabled,
            pending_messages=pending_messages,
        )

        # 11. Await conversation phases (fired early in parallel with DB queries)
        phases = await phases_task

        # 12. Build response
        return AppointmentContextResponse(
            appointment_id=appointment.id,
            scheduled_start=appointment.scheduled_start,
            scheduled_end=appointment.scheduled_end,
            location_address=appointment.location_address,
            latitude=appointment.latitude,
            longitude=appointment.longitude,
            outcome=appointment.outcome.value if appointment.outcome and hasattr(appointment.outcome, 'value') else appointment.outcome,
            recording_status=appointment.recording_status,
            audio_url=presign_audio_url_for_playback(appointment.audio_url),
            appointment_analysis=AppointmentAnalysis(
                analysis_status=appointment.analysis_status,
                summary=appointment.summary,
                key_points=list(appointment.key_points) if appointment.key_points else [],
                action_items=list(appointment.action_items) if appointment.action_items else [],
                next_steps=list(appointment.next_steps) if appointment.next_steps else [],
                sentiment_score=appointment.sentiment_score,
                qualification_status=appointment.qualification_status,
                booking_status=appointment.booking_status,
                objection_texts=list(appointment.objection_texts) if appointment.objection_texts else [],
                objections_total_count=appointment.objections_total_count,
                sop_compliance_score=appointment.sop_compliance_score,
                sop_compliance_rate=appointment.sop_compliance_rate,
                sop_stages_completed=list(appointment.sop_stages_completed) if appointment.sop_stages_completed else [],
                sop_stages_missed=list(appointment.sop_stages_missed) if appointment.sop_stages_missed else [],
                sop_compliance_issues=list(appointment.sop_compliance_issues) if appointment.sop_compliance_issues else [],
                sop_compliance_positive_behaviors=list(appointment.sop_compliance_positive_behaviors) if appointment.sop_compliance_positive_behaviors else [],
            ),
            contact_info=ContactCardInfo(
                id=contact_card.id,
                first_name=contact_card.first_name,
                last_name=contact_card.last_name,
                email=contact_card.email,
                primary_phone=contact_card.primary_phone,
                address=contact_card.address,
                city=contact_card.city,
                state=contact_card.state,
            ),
            sales_rep_name=sales_rep_name,
            property_brief=property_brief,
            lead_info=LeadContextInfo(
                id=lead.id,
                status=lead.status.value if hasattr(lead.status, 'value') else str(lead.status),
                deal_size=lead.deal_size,
                deal_type=lead.extra_metadata.get("deal_type") if lead.extra_metadata else None,
                lead_score=None,  # Future: integrate with intelligence service
            ),
            conversation_history=conversation_history,
            objections=aggregated_objections,
            pending_actions=pending_actions,
            phases=phases,
            ai_briefing=ai_briefing,
            follow_up=follow_up_section,
        )

    async def _generate_ai_briefing(
        self,
        company_id: str,
        contact_name: str,
        appointment_date: datetime,
        lead_status: str,
        deal_size: Optional[float],
        conversation_history: List[CallSummaryItem],
        top_objections: List[str],
        pending_actions: List[PendingActionItem],
    ) -> Optional[AIBriefing]:
        """
        Generate AI briefing using Ask Otto.

        Creates a one-off conversation with Shoonya to generate a pre-meeting brief.
        Returns None if Shoonya is unavailable.
        """
        try:
            shoonya = get_shoonya_client()
            if not shoonya.is_available():
                logger.warning("Shoonya unavailable - cannot generate AI briefing")
                return None

            # Build briefing prompt
            prompt = self._build_briefing_prompt(
                contact_name=contact_name,
                appointment_date=appointment_date,
                lead_status=lead_status,
                deal_size=deal_size,
                conversation_history=conversation_history,
                top_objections=top_objections,
                pending_actions=pending_actions,
            )

            # Create temporary conversation for briefing
            conv_result = await shoonya.create_ask_otto_conversation(
                company_id=company_id,
                user_id=None,
                metadata={"purpose": "appointment_briefing"},
            )
            conv_id = conv_result.get("conversation_id") or conv_result.get("id")

            # Send message and get briefing
            response = await shoonya.send_ask_otto_message(
                conversation_id=conv_id,
                message=prompt,
                company_id=company_id,
            )

            briefing_text = response.get("answer") or response.get("message") or ""

            # Extract focus areas from briefing (simple keyword extraction)
            focus_areas = self._extract_focus_areas(briefing_text)

            return AIBriefing(
                briefing_text=briefing_text,
                focus_areas=focus_areas,
                generated_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Error generating AI briefing: {e}")
            return None

    def _build_briefing_prompt(
        self,
        contact_name: str,
        appointment_date: datetime,
        lead_status: str,
        deal_size: Optional[float],
        conversation_history: List[CallSummaryItem],
        top_objections: List[str],
        pending_actions: List[PendingActionItem],
    ) -> str:
        """Build prompt for AI briefing generation."""
        prompt_parts = [
            f"Generate a concise pre-meeting briefing for a sales appointment with {contact_name} scheduled for {appointment_date.strftime('%Y-%m-%d %H:%M')}.",
            f"\nLead Status: {lead_status}",
        ]

        if deal_size:
            prompt_parts.append(f"Deal Size: ${deal_size:,.2f}")

        if conversation_history:
            prompt_parts.append("\n\nRecent Conversations:")
            for i, call in enumerate(conversation_history[:3], 1):
                prompt_parts.append(f"\n{i}. {call.call_type} on {call.call_date.strftime('%Y-%m-%d')}:")
                if call.summary:
                    prompt_parts.append(f"   Summary: {call.summary[:200]}")

        if top_objections:
            prompt_parts.append("\n\nTop Objections Raised:")
            for i, obj in enumerate(top_objections[:3], 1):
                prompt_parts.append(f"{i}. {obj}")

        if pending_actions:
            prompt_parts.append("\n\nPending Actions:")
            for i, action in enumerate(pending_actions[:3], 1):
                prompt_parts.append(f"{i}. {action.raw_text}")

        prompt_parts.append("\n\nProvide a brief overview (3-5 sentences), key topics to discuss, how to handle objections, and recommended next steps.")

        return "".join(prompt_parts)

    def _extract_focus_areas(self, briefing_text: str) -> List[str]:
        """Extract focus areas from briefing text (simple keyword extraction)."""
        focus_keywords = ["focus on", "prioritize", "key topic", "important to", "should discuss", "address"]
        focus_areas = []

        for line in briefing_text.split("\n"):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in focus_keywords):
                focus_areas.append(line.strip("- •*"))

        return focus_areas[:5]  # Max 5 focus areas

    def _build_local_ai_briefing(
        self,
        appointment: Appointment,
        contact_card,
        property_brief: PropertyBrief,
        conversation_history: List[CallSummaryItem],
        aggregated_objections: AggregatedObjections,
        pending_actions: List[PendingActionItem],
    ) -> Optional[AIBriefing]:
        """
        Deterministic fallback briefing when Ask Otto is unavailable or empty.

        Uses only local, already-loaded data and never performs I/O.
        """
        pieces: List[str] = []

        contact_name = f"{contact_card.first_name or ''} {contact_card.last_name or ''}".strip() or "the customer"
        when = appointment.scheduled_start.strftime("%Y-%m-%d %H:%M") if getattr(appointment, "scheduled_start", None) else "the upcoming appointment"

        pieces.append(
            f"You are meeting {contact_name} on {when}. This briefing is generated from existing Otto call analysis and tasks."
        )

        # Property / problem context
        if getattr(property_brief, "has_data", False):
            if property_brief.service_requested:
                pieces.append(f"The customer is interested in {property_brief.service_requested}.")
            if property_brief.problem_summary:
                pieces.append(f"Main problem: {property_brief.problem_summary}.")
            if property_brief.current_issues:
                issues = "; ".join(property_brief.current_issues[:3])
                pieces.append(f"Current issues mentioned: {issues}.")

        # Recent conversations
        if conversation_history:
            latest = conversation_history[0]
            when_last = latest.call_date.strftime("%Y-%m-%d") if latest.call_date else "recently"
            pieces.append(f"The most recent call was a {latest.call_type} on {when_last}.")
            if latest.summary:
                pieces.append(f"On that call, the key summary was: {latest.summary[:200]}.")

        # Objections
        top_objs = aggregated_objections.top_objections or []
        if top_objs:
            joined = "; ".join(top_objs[:3])
            pieces.append(f"Top objections raised so far: {joined}.")

        # Pending actions
        if pending_actions:
            pa_summaries = []
            for idx, pa in enumerate(pending_actions[:3], 1):
                text = pa.raw_text or ""
                owner = pa.owner_name or "you"
                pa_summaries.append(f"{idx}. {text} (owner: {owner})")
            if pa_summaries:
                pieces.append("Open follow-up items you should be aware of:\n" + "\n".join(pa_summaries))

        # Appointment-level analysis (summary / next steps)
        if appointment.summary:
            pieces.append(f"Post-appointment summary so far: {appointment.summary[:200]}.")
        if appointment.next_steps:
            steps = "; ".join(appointment.next_steps[:3])
            pieces.append(f"Next steps already captured: {steps}.")

        # Determine if we have “enough local data” per design; otherwise keep null.
        has_any_local_signal = any(
            [
                getattr(property_brief, "has_data", False),
                bool(conversation_history),
                bool(top_objs),
                bool(pending_actions),
                bool(getattr(appointment, "summary", None)),
                bool(getattr(appointment, "next_steps", None)),
            ]
        )

        briefing_text = " ".join(pieces).strip()
        if not has_any_local_signal or not briefing_text:
            return None

        # Simple focus areas based on what we surfaced.
        focus_areas: List[str] = []
        if property_brief.service_requested or property_brief.problem_summary:
            focus_areas.append("Clarify the customer’s problem and desired service.")
        if top_objs:
            focus_areas.append("Prepare responses to the top objections mentioned so far.")
        if pending_actions:
            focus_areas.append("Confirm and complete the open follow-up items before and after the meeting.")

        if not focus_areas:
            focus_areas.append("Build rapport, restate the problem clearly, and agree on concrete next steps.")

        return AIBriefing(
            briefing_text=briefing_text,
            focus_areas=focus_areas[:5],
            generated_at=datetime.utcnow(),
        )

