"""
Lead repository.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime, date

from sqlalchemy import select, or_, and_, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import (
    LeadDetail, ContactInfo, AgentInfo, OverallEngagement, Conversation,
    PipelineLeadDetail, PipelineLeadTab, PipelineEngagement, PipelineConversation,
    AppointmentTab, AppointmentDetails, SalesRepInfo, ResultTab,
    FollowUpTask, FollowUpTracking,
)
from app.domain.enums import DealStatus, PipelineStage
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.lead_status_change import LeadStatusChangeORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class LeadRepository(BaseRepository[LeadORM, Lead]):
    """Repository for Lead entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LeadORM, Lead)

    def _to_orm(self, domain_obj: Lead) -> LeadORM:
        """Convert domain model to ORM model, excluding computed fields."""
        # Exclude computed fields that don't exist in the ORM
        # These fields are derived from relationships (calls, contact_card, etc.)
        exclude_fields = {
            "call_audio_urls",  # Computed from calls relationship
            "name",  # Computed from contact_card relationship
            "phone_number",  # Computed from contact_card relationship
            "reason_not_booked",  # Computed from call analyses
            "objection",  # Computed from call analyses
            "response",  # Computed from call analyses
        }
        data = domain_obj.model_dump(
            exclude=exclude_fields | ({"id"} if domain_obj.id else set())
        )
        return self.orm_model(**data)

    async def get_by_id(self, id: UUID) -> Optional[Lead]:
        """Get lead by ID with call audio URLs."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.id == id)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting lead by ID: {e}")
            raise e

    def _to_domain(self, orm_obj: LeadORM) -> Lead:
        """Convert ORM model to domain model with call audio URLs."""
        # Extract audio URLs from associated calls
        # Check if the relationship is loaded to avoid lazy loading issues in async context
        call_audio_urls = None
        calls = []
        try:
            # Use inspect to check if relationship is loaded
            mapper = inspect(orm_obj)
            calls_attr = mapper.attrs.get('calls')

            # Check if relationship is loaded (loaded_value is not None means it was loaded, even if empty)
            if calls_attr and calls_attr.loaded_value is not None:
                # Relationship is loaded, safe to access
                calls = calls_attr.loaded_value
                if calls:  # calls could be an empty list if loaded but no items
                    call_audio_urls = [
                        call.audio_url for call in calls
                        if call.audio_url is not None
                    ]
                    # Return None if empty list instead of empty list
                    if not call_audio_urls:
                        call_audio_urls = None
        except (AttributeError, KeyError, TypeError) as e:
            # Relationship not loaded or not available, skip
            # This can happen if the object is detached or relationship wasn't eagerly loaded
            logger.debug(f"Could not access calls relationship for lead {orm_obj.id}: {e}")
            call_audio_urls = None
            calls = []

        # Extract contact information
        name = None
        phone_number = None
        try:
            mapper = inspect(orm_obj)
            contact_attr = mapper.attrs.get('contact_card')
            if contact_attr and contact_attr.loaded_value is not None:
                contact = contact_attr.loaded_value
                if contact:
                    # Build full name
                    first_name = contact.first_name or ""
                    last_name = contact.last_name or ""
                    name = f"{first_name} {last_name}".strip() or None
                    phone_number = contact.primary_phone
        except (AttributeError, KeyError, TypeError) as e:
            logger.debug(f"Could not access contact_card relationship for lead {orm_obj.id}: {e}")

        # Extract reason_not_booked, objection, and response from call analyses
        reason_not_booked = None
        objection = None
        response = None
        try:
            # Get the most recent call analysis with booking_status or objections
            if calls:
                # Sort calls by created_at descending to get most recent first
                sorted_calls = sorted(calls, key=lambda c: c.created_at if c.created_at else datetime.min, reverse=True)

                for call in sorted_calls:
                    # Check if call has analysis loaded
                    call_mapper = inspect(call)
                    analysis_attr = call_mapper.attrs.get('analysis')
                    if analysis_attr and analysis_attr.loaded_value is not None:
                        analysis = analysis_attr.loaded_value
                        if analysis:
                            # Get objection from objections column (first one)
                            if not objection:
                                if analysis.objections and len(analysis.objections) > 0:
                                    objection = str(analysis.objections[0])

                            # Get response from objection_texts column (first one)
                            if not response:
                                if analysis.objection_texts and len(analysis.objection_texts) > 0:
                                    response = analysis.objection_texts[0]

                            # Get reason_not_booked from booking_status or use first objection
                            if not reason_not_booked:
                                if analysis.booking_status:
                                    booking_status_lower = analysis.booking_status.lower()
                                    if booking_status_lower in ["not_booked", "unbooked", "qualified_unbooked"]:
                                        # If we have objection texts, use the first one as the reason
                                        if analysis.objection_texts and len(analysis.objection_texts) > 0:
                                            reason_not_booked = analysis.objection_texts[0]
                                        elif analysis.objections and len(analysis.objections) > 0:
                                            reason_not_booked = str(analysis.objections[0])
                                        else:
                                            reason_not_booked = analysis.booking_status

                            # If we found all fields, we can break
                            if reason_not_booked and objection and response:
                                break
        except (AttributeError, KeyError, TypeError) as e:
            logger.debug(f"Could not access call analysis for lead {orm_obj.id}: {e}")

        # Validate and convert deal_status
        deal_status = None
        if orm_obj.deal_status:
            try:
                deal_status = DealStatus(orm_obj.deal_status)
            except ValueError:
                logger.warning(
                    f"Invalid deal_status value: {orm_obj.deal_status} for lead {orm_obj.id}, "
                    "setting to None"
                )
                deal_status = None

        # Validate and convert pipeline_stage
        pipeline_stage = None
        if orm_obj.pipeline_stage:
            try:
                pipeline_stage = PipelineStage(orm_obj.pipeline_stage)
            except ValueError:
                logger.warning(
                    f"Invalid pipeline_stage value: {orm_obj.pipeline_stage} for lead {orm_obj.id}, "
                    "setting to None"
                )
                pipeline_stage = None

        # Convert to domain model
        lead_data = {
            "id": orm_obj.id,
            "company_id": orm_obj.company_id,
            "contact_card_id": orm_obj.contact_card_id,
            "status": orm_obj.status,
            "deal_status": deal_status,
            "pipeline_stage": pipeline_stage,
            "assigned_rep_id": orm_obj.assigned_rep_id,
            "deal_size": orm_obj.deal_size,
            "closed_at": orm_obj.closed_at,
            "extra_metadata": orm_obj.extra_metadata,
            "call_audio_urls": call_audio_urls,
            "created_at": orm_obj.created_at,
            "updated_at": orm_obj.updated_at,
            "name": name,
            "phone_number": phone_number,
            "reason_not_booked": reason_not_booked,
            "objection": objection,
            "response": response,
        }
        return Lead(**lead_data)

    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get all leads for a company."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.company_id == company_id)
                .offset(skip)
                .limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by company: {e}")
            raise e

    async def get_list_with_filters(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads for a company with optional date range, search (name/phone), and status filters."""
        try:
            query = (
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.company_id == company_id)
            )
            if start_date is not None:
                query = query.where(LeadORM.created_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date is not None:
                query = query.where(LeadORM.created_at <= datetime.combine(end_date, datetime.max.time()))
            if statuses:
                query = query.where(LeadORM.status.in_(statuses))
            if search and search.strip():
                # Build subquery to get lead IDs matching contact search to avoid DISTINCT over JSON columns
                search_term = f"%{search.strip().lower()}%"
                subq = (
                    select(LeadORM.id)
                    .outerjoin(ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id)
                    .where(
                        LeadORM.company_id == company_id,
                        or_(
                            func.lower(ContactCardORM.first_name).like(search_term),
                            func.lower(ContactCardORM.last_name).like(search_term),
                            func.lower(ContactCardORM.primary_phone).like(search_term),
                        ),
                    )
                    .distinct()
                    .subquery()
                )

                # Final query selects leads by id in subquery (avoids DISTINCT on whole row)
                final_q = (
                    select(LeadORM)
                    .options(
                        selectinload(LeadORM.contact_card),
                        selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                    )
                    .where(LeadORM.company_id == company_id, LeadORM.id.in_(select(subq.c.id)))
                )
                if start_date is not None:
                    final_q = final_q.where(LeadORM.created_at >= datetime.combine(start_date, datetime.min.time()))
                if end_date is not None:
                    final_q = final_q.where(LeadORM.created_at <= datetime.combine(end_date, datetime.max.time()))
                if statuses:
                    final_q = final_q.where(LeadORM.status.in_(statuses))

                result = await self.session.execute(final_q.order_by(LeadORM.created_at.desc()).offset(skip).limit(limit))
            else:
                result = await self.session.execute(
                    query.order_by(LeadORM.created_at.desc()).offset(skip).limit(limit)
                )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads with filters: {e}")
            raise e

    async def get_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads by multiple status values."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.status.in_(statuses),
                ).offset(skip).limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by statuses: {e}")
            raise e

    async def get_unbooked(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get unbooked leads (qualified_unbooked status)."""
        try:
            return await self.get_by_statuses(
                company_id=company_id,
                statuses=["qualified_unbooked"],
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting unbooked leads: {e}")
            raise e

    async def get_by_priority(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads sorted by priority (hot > warm > new > others)."""
        try:
            # Priority order: hot > warm > new > others
            priority_order = {
                "hot": 1,
                "warm": 2,
                "new": 3,
            }

            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(
                    LeadORM.company_id == company_id,
                ).order_by(
                    case(
                        (LeadORM.status == "hot", 1),
                        (LeadORM.status == "warm", 2),
                        (LeadORM.status == "new", 3),
                        else_=4,
                    ),
                    LeadORM.created_at.desc(),
                ).offset(skip).limit(limit)
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by priority: {e}")
            raise e

    async def get_pending_leads_for_rep(
        self,
        company_id: UUID,
        rep_id: UUID,
        status_filter: Optional[str] = None,
        urgency_only: bool = False,
        sort_by: str = "last_touched",
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[List[LeadORM], int]:
        """
        Get leads assigned to a rep with optional status/urgency filters and pagination.

        status_filter: "pending" (open), "closed", or "lost".
        sort_by: "last_touched" (lead.updated_at) or "appointment_date" (soonest appointment).
        Returns (list of LeadORM with contact_card and calls+analysis loaded, total_count).
        """
        try:
            PENDING_STATUSES = {"closed_won", "closed_lost", "abandoned", "dormant"}
            query = (
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                )
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.assigned_rep_id == rep_id,
                )
            )
            if status_filter == "pending":
                query = query.where(~LeadORM.status.in_(PENDING_STATUSES))
            elif status_filter == "closed":
                query = query.where(
                    or_(
                        LeadORM.status == "closed_won",
                        LeadORM.deal_status.in_(["won", "WON"]),
                    )
                )
            elif status_filter == "lost":
                query = query.where(
                    LeadORM.status.in_(["closed_lost", "abandoned", "dormant"])
                )

            if urgency_only:
                try:
                    dialect = self.session.get_bind().dialect.name
                    if dialect == "postgresql":
                        query = query.where(
                            text("(leads.extra_metadata->>'urgency_level') = 'high'")
                        )
                    else:
                        query = query.where(
                            text(
                                "json_extract(leads.extra_metadata, '$.urgency_level') = 'high'"
                            )
                        )
                except Exception:
                    pass

            count_query = select(func.count(LeadORM.id)).where(
                LeadORM.company_id == company_id,
                LeadORM.assigned_rep_id == rep_id,
            )
            if status_filter == "pending":
                count_query = count_query.where(~LeadORM.status.in_(PENDING_STATUSES))
            elif status_filter == "closed":
                count_query = count_query.where(
                    or_(
                        LeadORM.status == "closed_won",
                        LeadORM.deal_status.in_(["won", "WON"]),
                    )
                )
            elif status_filter == "lost":
                count_query = count_query.where(
                    LeadORM.status.in_(["closed_lost", "abandoned", "dormant"])
                )
            if urgency_only:
                try:
                    dialect = self.session.get_bind().dialect.name
                    if dialect == "postgresql":
                        count_query = count_query.where(
                            text("(leads.extra_metadata->>'urgency_level') = 'high'")
                        )
                    else:
                        count_query = count_query.where(
                            text(
                                "json_extract(leads.extra_metadata, '$.urgency_level') = 'high'"
                            )
                        )
                except Exception:
                    pass
            count_result = await self.session.execute(count_query)
            total = count_result.scalar() or 0

            if sort_by == "appointment_date":
                appt_subq = (
                    select(func.min(AppointmentORM.scheduled_start))
                    .where(AppointmentORM.lead_id == LeadORM.id)
                    .scalar_subquery()
                )
                query = query.order_by(appt_subq.desc().nulls_last())
            else:
                query = query.order_by(
                    LeadORM.updated_at.desc().nulls_last(),
                    LeadORM.created_at.desc(),
                )

            result = await self.session.execute(
                query.offset(offset).limit(limit)
            )
            orm_objs = result.scalars().all()
            return (list(orm_objs), total)
        except Exception as e:
            logger.error(f"Error getting pending leads for rep: {e}")
            raise e

    async def count_by_status(
        self,
        company_id: UUID,
        status: str,
    ) -> int:
        """Count leads by status."""
        try:
            result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status == status,
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting leads by status: {e}")
            raise e

    async def count_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
    ) -> int:
        """Count leads by multiple statuses."""
        try:
            result = await self.session.execute(
                select(func.count(LeadORM.id)).where(
                    LeadORM.company_id == company_id,
                    LeadORM.status.in_(statuses),
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting leads by statuses: {e}")
            raise e

    async def get_by_pipeline_stages(
        self,
        company_id: UUID,
    ) -> List[Lead]:
        """Get all leads for a company that have a pipeline_stage set, with relationships loaded."""
        try:
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                )
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.pipeline_stage.isnot(None),
                )
                .order_by(LeadORM.created_at.desc())
            )
            orm_objs = result.scalars().all()
            return [self._to_domain(obj) for obj in orm_objs]
        except Exception as e:
            logger.error(f"Error getting leads by pipeline stages: {e}")
            raise e

    async def get_detail_by_id(self, lead_id: UUID) -> Optional[LeadDetail]:
        """Get detailed lead information for lead details page."""
        try:
            # Get lead with all relationships
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            # Get contact info
            contact_info = ContactInfo(
                id=lead_orm.contact_card.id,
                first_name=lead_orm.contact_card.first_name,
                last_name=lead_orm.contact_card.last_name,
                primary_phone=lead_orm.contact_card.primary_phone,
                email=lead_orm.contact_card.email,
            )

            # Get agent info if assigned
            agent_info = None
            if lead_orm.assigned_rep_id:
                agent_result = await self.session.execute(
                    select(UserORM).where(UserORM.id == lead_orm.assigned_rep_id)
                )
                agent_orm = agent_result.scalar_one_or_none()
                if agent_orm:
                    agent_info = AgentInfo(
                        id=agent_orm.id,
                        first_name=agent_orm.first_name,
                        last_name=agent_orm.last_name,
                        email=agent_orm.email,
                    )

            # Get call analyses for this lead (via calls)
            # Safely access calls relationship to avoid lazy loading issues
            calls = []
            try:
                mapper = inspect(lead_orm)
                calls_attr = mapper.attrs.get('calls')
                if calls_attr and calls_attr.loaded_value is not None:
                    calls = calls_attr.loaded_value or []
            except (AttributeError, KeyError, TypeError):
                calls = []

            call_ids = [call.id for call in calls]
            summaries = []
            all_key_points = []

            if call_ids:
                analyses_result = await self.session.execute(
                    select(CallAnalysisORM)
                    .where(
                        CallAnalysisORM.call_id.in_(call_ids),
                        CallAnalysisORM.status == "completed",
                        CallAnalysisORM.summary.isnot(None),
                    )
                    .order_by(CallAnalysisORM.created_at.desc())
                )
                analyses = analyses_result.scalars().all()

                for analysis in analyses:
                    if analysis.summary:
                        summaries.append(analysis.summary)
                    if analysis.key_points:
                        all_key_points.extend(analysis.key_points)

            # Aggregate summary (combine all summaries)
            aggregated_summary = " ".join(summaries) if summaries else None

            # Get pending actions
            actions_result = await self.session.execute(
                select(PendingActionORM)
                .where(
                    PendingActionORM.lead_id == lead_id,
                    PendingActionORM.status == "pending",
                )
                .order_by(PendingActionORM.due_at.asc().nulls_last())
            )
            pending_actions = actions_result.scalars().all()
            action_items = [action.raw_text for action in pending_actions if action.raw_text]

            # Determine appointment status from lead status
            appointment_status = None
            if lead_orm.status == "qualified_service_not_offered":
                appointment_status = "Qualified but service not offered"
            elif lead_orm.status == "qualified_unbooked":
                appointment_status = "Qualified but unbooked"
            elif lead_orm.status == "qualified_booked":
                appointment_status = "Qualified and booked"

            overall_engagement = OverallEngagement(
                summary=aggregated_summary,
                key_points=list(set(all_key_points)),  # Remove duplicates
                action_items=action_items,
                appointment_status=appointment_status,
            )

            # Get conversations (calls) for this lead, sorted by most recent first
            conversations = []
            if calls:
                # Sort calls by created_at descending (most recent first)
                sorted_calls = sorted(calls, key=lambda c: c.created_at, reverse=True)

                for call in sorted_calls:
                    # Get analysis for this call - it's already loaded via selectinload
                    analysis = None
                    if hasattr(call, 'analysis') and call.analysis:
                        analysis = call.analysis

                    conversation = Conversation(
                        id=call.id,
                        call_type=call.call_type,
                        phone_number=call.phone_number,
                        duration_seconds=call.duration_seconds,
                        missed_call=call.missed_call,
                        transcript=call.transcript,
                        call_recording_url=call.audio_url,
                        handled_by_user_id=call.handled_by_user_id,
                        created_at=call.created_at,
                        summary=analysis.summary if analysis else None,
                        key_points=list(analysis.key_points) if analysis and analysis.key_points else [],
                        objections=list(analysis.objections) if analysis and analysis.objections else [],
                        sentiment_score=analysis.sentiment_score if analysis else None,
                        sop_compliance_score=analysis.sop_compliance_score if analysis else None,
                        qualification_status=analysis.qualification_status if analysis else None,
                        booking_status=analysis.booking_status if analysis else None,
                    )
                    conversations.append(conversation)

            return LeadDetail(
                id=lead_orm.id,
                company_id=lead_orm.company_id,
                status=lead_orm.status,
                deal_status=lead_orm.deal_status,
                pipeline_stage=lead_orm.pipeline_stage,
                deal_size=lead_orm.deal_size,
                created_at=lead_orm.created_at,
                updated_at=lead_orm.updated_at,
                contact=contact_info,
                agent=agent_info,
                overall_engagement=overall_engagement,
                conversations=conversations,
            )
        except Exception as e:
            logger.error(f"Error getting lead detail: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def get_pipeline_detail_by_id(self, lead_id: UUID) -> Optional[PipelineLeadDetail]:
        """
        Get 3-tab pipeline lead detail:
          - lead tab:        CSR stage — all inbound calls + their analyses
          - appointment tab: appointment details (if any)
          - result tab:      appointment outcome + its call analysis (if conducted)
        """
        try:
            # ── 1. Load lead with contact_card and calls (with analysis) ─────────
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()
            if not lead_orm:
                return None

            # ── 2. Calls — sort most recent first ────────────────────────────────
            try:
                mapper = inspect(lead_orm)
                calls_attr = mapper.attrs.get("calls")
                raw_calls = (calls_attr.loaded_value or []) if calls_attr else []
            except Exception:
                raw_calls = []
            sorted_calls = sorted(raw_calls, key=lambda c: c.created_at, reverse=True)

            # ── 3. Build Lead tab ─────────────────────────────────────────────────
            lead_conversations: List[PipelineConversation] = []
            summaries: List[str] = []
            all_key_points: List[str] = []
            last_touched = None
            next_move = None

            for call in sorted_calls:
                analysis = getattr(call, "analysis", None)
                if call.created_at and (last_touched is None or call.created_at > last_touched):
                    last_touched = call.created_at
                # Take next_move from the most recent call that has next_steps
                if next_move is None and analysis and analysis.next_steps:
                    next_move = analysis.next_steps[0] if isinstance(analysis.next_steps, list) else str(analysis.next_steps)

                if analysis and analysis.summary:
                    summaries.append(analysis.summary)
                if analysis and analysis.key_points:
                    all_key_points.extend(analysis.key_points)

                lead_conversations.append(
                    PipelineConversation(
                        id=call.id,
                        call_type=call.call_type,
                        duration_seconds=call.duration_seconds,
                        created_at=call.created_at,
                        booking_status=analysis.booking_status if analysis else None,
                        qualification_status=analysis.qualification_status if analysis else None,
                        summary=analysis.summary if analysis else None,
                        key_points=list(analysis.key_points) if analysis and analysis.key_points else [],
                        objections=list(analysis.objections) if analysis and analysis.objections else [],
                        call_recording_url=call.audio_url,
                    )
                )

            lead_tab = PipelineLeadTab(
                id=lead_orm.id,
                status=lead_orm.status,
                overall_engagement=PipelineEngagement(
                    last_touched=last_touched,
                    next_move=next_move,
                    summary=" ".join(summaries) if summaries else None,
                    key_points=list(dict.fromkeys(all_key_points)),  # dedupe, preserve order
                ),
                conversations=lead_conversations,
            )

            # ── 4. Load most recent appointment for this lead ─────────────────────
            appt_result = await self.session.execute(
                select(AppointmentORM)
                .where(AppointmentORM.lead_id == lead_id)
                .order_by(AppointmentORM.scheduled_start.desc())
                .limit(1)
            )
            appt_orm = appt_result.scalar_one_or_none()

            appointment_tab: Optional[AppointmentTab] = None
            result_tab: Optional[ResultTab] = None

            if appt_orm:
                # Contact name from contact_card
                contact_name = "Unknown"
                if lead_orm.contact_card:
                    first = lead_orm.contact_card.first_name or ""
                    last = lead_orm.contact_card.last_name or ""
                    contact_name = f"{first} {last}".strip() or "Unknown"

                # Sales rep info
                sales_rep_info: Optional[SalesRepInfo] = None
                if appt_orm.assigned_rep_id:
                    rep_result = await self.session.execute(
                        select(UserORM).where(UserORM.id == appt_orm.assigned_rep_id)
                    )
                    rep_orm = rep_result.scalar_one_or_none()
                    if rep_orm:
                        sales_rep_info = SalesRepInfo(
                            id=rep_orm.id,
                            first_name=rep_orm.first_name,
                            last_name=rep_orm.last_name,
                        )

                # Appointment status
                appt_status = appt_orm.outcome or "scheduled"

                # Meeting URL from extra_metadata if present
                meeting_url = None
                if appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                    meeting_url = appt_orm.extra_metadata.get("meeting_url") or appt_orm.extra_metadata.get("join_url")

                # ── 4b. Load follow-up tasks (pending_actions) for this lead ──────
                follow_up_result = await self.session.execute(
                    select(PendingActionORM)
                    .where(PendingActionORM.lead_id == lead_id)
                    .order_by(PendingActionORM.due_at.asc().nullslast())
                )
                follow_up_actions = list(follow_up_result.scalars().all())

                from datetime import timezone
                now_utc = datetime.now(timezone.utc)
                follow_up_tasks = [
                    FollowUpTask(
                        id=pa.id,
                        action_type=pa.action_type,
                        raw_text=pa.raw_text,
                        status=pa.status,
                        due_at=pa.due_at,
                        priority=pa.priority,
                    )
                    for pa in follow_up_actions
                ]
                completed_count = sum(1 for pa in follow_up_actions if pa.status == "completed")
                pending_count = sum(1 for pa in follow_up_actions if pa.status in ("pending", "in_progress"))
                is_overdue = any(
                    pa.due_at and pa.due_at < now_utc
                    for pa in follow_up_actions
                    if pa.status in ("pending", "in_progress")
                )
                pending_with_due = [
                    pa for pa in follow_up_actions
                    if pa.status in ("pending", "in_progress") and pa.due_at and pa.due_at >= now_utc
                ]
                next_follow_up = min((pa.due_at for pa in pending_with_due), default=None)
                last_touched_followup = max(
                    (pa.updated_at or pa.created_at for pa in follow_up_actions),
                    default=None,
                )

                follow_up_tracking = FollowUpTracking(
                    follow_up_attempts=completed_count + pending_count,
                    last_touched=last_touched_followup,
                    is_overdue=is_overdue,
                    next_follow_up=next_follow_up,
                    tasks=follow_up_tasks,
                )

                # Build appointment details sub-section
                appt_details = AppointmentDetails(
                    id=appt_orm.id,
                    contact_name=contact_name,
                    sales_rep=sales_rep_info,
                    status=appt_status,
                    outcome=appt_orm.outcome,
                    location_address=appt_orm.location_address,
                    scheduled_start=appt_orm.scheduled_start,
                    scheduled_end=appt_orm.scheduled_end,
                    meeting_url=meeting_url,
                    deal_size=lead_orm.deal_size,
                    audio_url=appt_orm.audio_url,
                    transcript=appt_orm.transcript,
                    duration_seconds=appt_orm.duration_seconds,
                    summary=appt_orm.summary,
                    key_points=list(appt_orm.key_points) if appt_orm.key_points else [],
                    objections=list(appt_orm.objections) if appt_orm.objections else [],
                )

                # Build sales rep full name for top-level summary
                sales_rep_name = None
                if sales_rep_info:
                    first = sales_rep_info.first_name or ""
                    last = sales_rep_info.last_name or ""
                    sales_rep_name = f"{first} {last}".strip() or None

                # Extract title and arrival_time from extra_metadata if present
                appt_title = None
                appt_arrival_time = None
                if appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                    appt_title = appt_orm.extra_metadata.get("title")
                    appt_arrival_time_str = appt_orm.extra_metadata.get("arrival_time")
                    if appt_arrival_time_str:
                        try:
                            from dateutil.parser import parse as parse_dt
                            appt_arrival_time = parse_dt(appt_arrival_time_str)
                        except Exception:
                            pass

                appointment_tab = AppointmentTab(
                    title=appt_title,
                    location_address=appt_orm.location_address,
                    sales_rep_name=sales_rep_name,
                    deal_size=lead_orm.deal_size,
                    status=appt_status,
                    scheduled_start=appt_orm.scheduled_start,
                    arrival_time=appt_arrival_time,
                    details=appt_details,
                    follow_up=follow_up_tracking,
                )

                # ── 5. Result tab — only if appointment has been conducted ─────────
                has_result = bool(
                    appt_orm.summary
                    or appt_orm.outcome
                    or appt_orm.audio_url
                    or appt_orm.qualification_status
                )
                if has_result:
                    # Build result conversation from appointment interaction call (if any)
                    result_conversations: List[PipelineConversation] = []
                    result_last_touched = None
                    result_next_move = None
                    result_summaries: List[str] = []
                    result_key_points: List[str] = []

                    if appt_orm.interaction_id:
                        interaction_result = await self.session.execute(
                            select(CallORM)
                            .options(selectinload(CallORM.analysis))
                            .where(CallORM.id == appt_orm.interaction_id)
                        )
                        interaction_call = interaction_result.scalar_one_or_none()
                        if interaction_call:
                            ia = getattr(interaction_call, "analysis", None)
                            result_last_touched = interaction_call.created_at
                            if ia and ia.next_steps:
                                result_next_move = ia.next_steps[0] if isinstance(ia.next_steps, list) else str(ia.next_steps)
                            if ia and ia.summary:
                                result_summaries.append(ia.summary)
                            if ia and ia.key_points:
                                result_key_points.extend(ia.key_points)
                            result_conversations.append(
                                PipelineConversation(
                                    id=interaction_call.id,
                                    call_type=interaction_call.call_type,
                                    duration_seconds=interaction_call.duration_seconds,
                                    created_at=interaction_call.created_at,
                                    booking_status=ia.booking_status if ia else appt_orm.booking_status,
                                    qualification_status=ia.qualification_status if ia else appt_orm.qualification_status,
                                    summary=ia.summary if ia else appt_orm.summary,
                                    key_points=list(ia.key_points) if ia and ia.key_points else [],
                                    objections=list(ia.objections) if ia and ia.objections else (list(appt_orm.objections) if appt_orm.objections else []),
                                    call_recording_url=interaction_call.audio_url or appt_orm.audio_url,
                                )
                            )

                    # If no interaction call, use appointment's own analysis fields
                    if not result_conversations and (appt_orm.summary or appt_orm.qualification_status):
                        result_last_touched = appt_orm.updated_at or appt_orm.created_at
                        if appt_orm.summary:
                            result_summaries.append(appt_orm.summary)

                    # Extract key_lesson from extra_metadata
                    key_lesson = None
                    if appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                        key_lesson = appt_orm.extra_metadata.get("key_lesson")

                    result_tab = ResultTab(
                        outcome=appt_orm.outcome,
                        outcome_summary=appt_orm.summary,
                        deal_size=lead_orm.deal_size,
                        key_lesson=key_lesson,
                        overall_engagement=PipelineEngagement(
                            last_touched=result_last_touched,
                            next_move=result_next_move,
                            summary=" ".join(result_summaries) if result_summaries else None,
                            key_points=list(dict.fromkeys(result_key_points)),
                        ),
                        conversations=result_conversations,
                        follow_up=follow_up_tracking,
                    )

            return PipelineLeadDetail(
                pipeline_stage=lead_orm.pipeline_stage,
                lead=lead_tab,
                appointment=appointment_tab,
                result=result_tab,
            )

        except Exception as e:
            logger.error(f"Error getting pipeline lead detail: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def get_customer_card(self, lead_id: UUID):
        """
        Build the full customer card payload for a lead.

        Returns a CustomerCard domain model or None if the lead doesn't exist.
        """
        from app.domain.models.customer_card import (
            CustomerCard, CardContact, CardRepInfo, PipelineStageInfo,
            CardEngagement, CardConversation, SOPChecklistItem,
            CardLeadTab, CardAppointmentTab, CardResultTab,
            CardFollowUpTracking, CardFollowUpTask,
            CardPost, CardPostAuthor,
        )
        from app.domain.enums import PipelineStage, PIPELINE_STAGE_ORDER
        from app.infrastructure.database.models.post import PostORM

        try:
            # ── 1. Load lead with contact_card and calls (+ analysis) ─────────
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis),
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()
            if not lead_orm:
                return None

            # ── 2. Contact info ───────────────────────────────────────────────
            contact = lead_orm.contact_card
            first = contact.first_name or "" if contact else ""
            last = contact.last_name or "" if contact else ""
            full_name = f"{first} {last}".strip() or None
            initials = (
                (first[:1] + last[:1]).upper()
                if (first or last) else None
            )

            # Build address string
            address_parts = []
            if contact:
                if contact.address:
                    address_parts.append(contact.address)
                loc_parts = ", ".join(filter(None, [
                    contact.city, contact.state, contact.postal_code
                ]))
                if loc_parts:
                    address_parts.append(loc_parts)

            card_contact = CardContact(
                id=contact.id if contact else lead_orm.contact_card_id,
                first_name=first or None,
                last_name=last or None,
                full_name=full_name,
                initials=initials,
                primary_phone=contact.primary_phone if contact else "",
                email=contact.email if contact else None,
                address=contact.address if contact else None,
                city=contact.city if contact else None,
                state=contact.state if contact else None,
                postal_code=contact.postal_code if contact else None,
            )

            # ── 3. Assigned rep info ──────────────────────────────────────────
            assigned_rep: CardRepInfo | None = None
            if lead_orm.assigned_rep_id:
                rep_result = await self.session.execute(
                    select(UserORM).where(UserORM.id == lead_orm.assigned_rep_id)
                )
                rep_orm = rep_result.scalar_one_or_none()
                if rep_orm:
                    rf = rep_orm.first_name or ""
                    rl = rep_orm.last_name or ""
                    assigned_rep = CardRepInfo(
                        id=rep_orm.id,
                        first_name=rf or None,
                        last_name=rl or None,
                        full_name=f"{rf} {rl}".strip() or None,
                    )

            # ── 4. Pipeline progress bar ──────────────────────────────────────
            # Display order for the progress bar (separate from PIPELINE_STAGE_ORDER
            # which is used for move validation). "review" is visually last.
            display_stages = [
                ("unqualified", "Unqualified", 0),
                ("qualified", "Qualified", 1),
                ("booked", "Booked", 2),
                ("appointment", "Appt Sched", 3),
                ("appointment_ran", "Appt Ran", 4),
                ("won", "Outcome", 5),
                ("review", "Review", 6),
            ]
            current_stage = lead_orm.pipeline_stage
            # Map current stage to its display order
            display_order_map = {name: order for name, _, order in display_stages}
            display_order_map["lost"] = 5  # lost shares the outcome position
            display_order_map["service_not_offered"] = 0
            current_display_order = display_order_map.get(current_stage, -1)

            pipeline_stages: list[PipelineStageInfo] = []
            for idx, (stage_name, stage_label, disp_order) in enumerate(display_stages):
                if stage_name == current_stage or (
                    stage_name in ("won", "lost") and current_stage in ("won", "lost")
                ):
                    s = "active"
                elif disp_order < current_display_order:
                    s = "done"
                else:
                    s = "future"
                pipeline_stages.append(PipelineStageInfo(
                    name=stage_name, label=stage_label, status=s, order=idx + 1,
                ))

            # ── 5. Calls — sort most recent first ─────────────────────────────
            try:
                mapper = inspect(lead_orm)
                calls_attr = mapper.attrs.get("calls")
                raw_calls = (calls_attr.loaded_value or []) if calls_attr else []
            except Exception:
                raw_calls = []
            sorted_calls = sorted(raw_calls, key=lambda c: c.created_at, reverse=True)

            # ── 6. Build Lead tab ─────────────────────────────────────────────
            lead_conversations: list[CardConversation] = []
            summaries: list[str] = []
            all_key_points: list[str] = []
            all_action_items: list[str] = []
            last_touched = None
            next_move = None

            for call in sorted_calls:
                analysis = getattr(call, "analysis", None)
                if call.created_at and (last_touched is None or call.created_at > last_touched):
                    last_touched = call.created_at
                if next_move is None and analysis and analysis.next_steps:
                    next_move = analysis.next_steps[0] if isinstance(analysis.next_steps, list) else str(analysis.next_steps)

                if analysis and analysis.summary:
                    summaries.append(analysis.summary)
                if analysis and analysis.key_points:
                    all_key_points.extend(analysis.key_points)
                if analysis and analysis.action_items:
                    all_action_items.extend(analysis.action_items)

                # SOP checklist from call analysis
                sop_checklist: list[SOPChecklistItem] = []
                if analysis:
                    for stage_name in (analysis.sop_stages_completed or []):
                        sop_checklist.append(SOPChecklistItem(stage_name=stage_name, status="completed"))
                    for stage_name in (analysis.sop_stages_missed or []):
                        sop_checklist.append(SOPChecklistItem(stage_name=stage_name, status="missed"))

                lead_conversations.append(CardConversation(
                    id=call.id,
                    call_type=call.call_type,
                    phone_number=call.phone_number,
                    duration_seconds=call.duration_seconds,
                    missed_call=call.missed_call,
                    created_at=call.created_at,
                    answered_at=call.answered_at,
                    call_recording_url=call.audio_url,
                    booking_status=analysis.booking_status if analysis else None,
                    qualification_status=analysis.qualification_status if analysis else None,
                    summary=analysis.summary if analysis else None,
                    key_points=list(analysis.key_points) if analysis and analysis.key_points else [],
                    objections=list(analysis.objections) if analysis and analysis.objections else [],
                    sentiment_score=analysis.sentiment_score if analysis else None,
                    sop_compliance_score=analysis.sop_compliance_score if analysis else None,
                    sop_compliance_rate=analysis.sop_compliance_rate if analysis else None,
                    sop_checklist=sop_checklist,
                    sop_compliance_issues=list(analysis.sop_compliance_issues) if analysis and analysis.sop_compliance_issues else [],
                    sop_compliance_positive_behaviors=list(analysis.sop_compliance_positive_behaviors) if analysis and analysis.sop_compliance_positive_behaviors else [],
                    compliance_target_role=analysis.compliance_target_role if analysis else None,
                ))

            lead_tab = CardLeadTab(
                id=lead_orm.id,
                status=lead_orm.status,
                overall_engagement=CardEngagement(
                    last_touched=last_touched,
                    next_move=next_move,
                    summary=" ".join(summaries) if summaries else None,
                    key_points=list(dict.fromkeys(all_key_points)),
                    action_items=list(dict.fromkeys(all_action_items)),
                ),
                conversations=lead_conversations,
                coaching_tips=lead_orm.coaching_tips if hasattr(lead_orm, 'coaching_tips') else None,
            )

            # ── 7. Load appointment ───────────────────────────────────────────
            appt_result = await self.session.execute(
                select(AppointmentORM)
                .where(AppointmentORM.lead_id == lead_id)
                .order_by(AppointmentORM.scheduled_start.desc())
                .limit(1)
            )
            appt_orm = appt_result.scalar_one_or_none()

            appointment_tab: CardAppointmentTab | None = None
            result_tab: CardResultTab | None = None

            if appt_orm:
                # Contact name
                contact_name = full_name or "Unknown"

                # Sales rep for appointment
                appt_rep: CardRepInfo | None = None
                rep_to_check = appt_orm.assigned_rep_id or lead_orm.assigned_rep_id
                if rep_to_check:
                    if assigned_rep and rep_to_check == lead_orm.assigned_rep_id:
                        appt_rep = assigned_rep
                    else:
                        rep_r = await self.session.execute(
                            select(UserORM).where(UserORM.id == rep_to_check)
                        )
                        rep_o = rep_r.scalar_one_or_none()
                        if rep_o:
                            rf2 = rep_o.first_name or ""
                            rl2 = rep_o.last_name or ""
                            appt_rep = CardRepInfo(
                                id=rep_o.id, first_name=rf2 or None, last_name=rl2 or None,
                                full_name=f"{rf2} {rl2}".strip() or None,
                            )

                appt_status = appt_orm.outcome or "scheduled"
                meeting_url = None
                if appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                    meeting_url = appt_orm.extra_metadata.get("meeting_url") or appt_orm.extra_metadata.get("join_url")

                # SOP checklist for appointment
                appt_sop_checklist: list[SOPChecklistItem] = []

                # First try: appointment's own SOP columns
                if appt_orm.sop_stages_completed or appt_orm.sop_stages_missed:
                    for sn in (appt_orm.sop_stages_completed or []):
                        appt_sop_checklist.append(SOPChecklistItem(stage_name=sn, status="completed"))
                    for sn in (appt_orm.sop_stages_missed or []):
                        appt_sop_checklist.append(SOPChecklistItem(stage_name=sn, status="missed"))

                # Fallback: use interaction call's analysis
                appt_analysis_summary = appt_orm.summary
                appt_analysis_key_points = list(appt_orm.key_points or []) if hasattr(appt_orm, 'key_points') and appt_orm.key_points else []
                appt_sop_score = appt_orm.sop_compliance_score if hasattr(appt_orm, 'sop_compliance_score') else None
                appt_sop_rate = appt_orm.sop_compliance_rate if hasattr(appt_orm, 'sop_compliance_rate') else None
                appt_sop_issues = list(appt_orm.sop_compliance_issues or []) if hasattr(appt_orm, 'sop_compliance_issues') and appt_orm.sop_compliance_issues else []
                appt_sop_positives = list(appt_orm.sop_compliance_positive_behaviors or []) if hasattr(appt_orm, 'sop_compliance_positive_behaviors') and appt_orm.sop_compliance_positive_behaviors else []
                appt_compliance_role = appt_orm.compliance_target_role if hasattr(appt_orm, 'compliance_target_role') else None

                if appt_orm.interaction_id and not appt_sop_checklist:
                    interaction_result = await self.session.execute(
                        select(CallORM)
                        .options(selectinload(CallORM.analysis))
                        .where(CallORM.id == appt_orm.interaction_id)
                    )
                    interaction_call = interaction_result.scalar_one_or_none()
                    if interaction_call:
                        ia = getattr(interaction_call, "analysis", None)
                        if ia:
                            for sn in (ia.sop_stages_completed or []):
                                appt_sop_checklist.append(SOPChecklistItem(stage_name=sn, status="completed"))
                            for sn in (ia.sop_stages_missed or []):
                                appt_sop_checklist.append(SOPChecklistItem(stage_name=sn, status="missed"))
                            if not appt_analysis_summary:
                                appt_analysis_summary = ia.summary
                            if not appt_analysis_key_points and ia.key_points:
                                appt_analysis_key_points = list(ia.key_points)
                            if appt_sop_score is None:
                                appt_sop_score = ia.sop_compliance_score
                            if appt_sop_rate is None:
                                appt_sop_rate = ia.sop_compliance_rate
                            if not appt_sop_issues and ia.sop_compliance_issues:
                                appt_sop_issues = list(ia.sop_compliance_issues)
                            if not appt_sop_positives and ia.sop_compliance_positive_behaviors:
                                appt_sop_positives = list(ia.sop_compliance_positive_behaviors)
                            if not appt_compliance_role:
                                appt_compliance_role = ia.compliance_target_role

                # Load posts/comments for this appointment
                posts_result = await self.session.execute(
                    select(PostORM)
                    .where(PostORM.appointment_id == appt_orm.id)
                    .order_by(PostORM.created_at.desc())
                )
                posts_orms = posts_result.scalars().all()

                # Batch-load poster users
                poster_ids = list({p.poster_id for p in posts_orms})
                poster_map: dict = {}
                if poster_ids:
                    poster_result = await self.session.execute(
                        select(UserORM).where(UserORM.id.in_(poster_ids))
                    )
                    for u in poster_result.scalars().all():
                        pf = u.first_name or ""
                        pl = u.last_name or ""
                        poster_map[u.id] = CardPostAuthor(
                            id=u.id,
                            first_name=pf or None,
                            last_name=pl or None,
                            full_name=f"{pf} {pl}".strip() or None,
                            initials=(pf[:1] + pl[:1]).upper() if (pf or pl) else None,
                        )

                card_posts = [
                    CardPost(
                        id=p.id,
                        author=poster_map.get(p.poster_id),
                        note=p.note,
                        tags=p.tags.value if p.tags else None,
                        likes=p.likes or 0,
                        created_at=p.created_at,
                    )
                    for p in posts_orms
                ]

                # Extract title and arrival_time from extra_metadata
                card_appt_title = None
                card_appt_arrival_time = None
                if appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                    card_appt_title = appt_orm.extra_metadata.get("title")
                    card_arrival_str = appt_orm.extra_metadata.get("arrival_time")
                    if card_arrival_str:
                        try:
                            from dateutil.parser import parse as parse_dt
                            card_appt_arrival_time = parse_dt(card_arrival_str)
                        except Exception:
                            pass

                appointment_tab = CardAppointmentTab(
                    id=appt_orm.id,
                    contact_name=contact_name,
                    sales_rep=appt_rep,
                    status=appt_status,
                    outcome=appt_orm.outcome,
                    location_address=appt_orm.location_address,
                    scheduled_start=appt_orm.scheduled_start,
                    scheduled_end=appt_orm.scheduled_end,
                    meeting_url=meeting_url,
                    deal_size=lead_orm.deal_size,
                    title=card_appt_title,
                    arrival_time=card_appt_arrival_time,
                    audio_url=appt_orm.audio_url,
                    transcript=appt_orm.transcript,
                    duration_seconds=appt_orm.duration_seconds,
                    summary=appt_analysis_summary,
                    key_points=appt_analysis_key_points,
                    objections=list(appt_orm.objections or []),
                    objection_texts=list(appt_orm.objection_texts or []),
                    sop_compliance_score=appt_sop_score,
                    sop_compliance_rate=appt_sop_rate,
                    sop_checklist=appt_sop_checklist,
                    sop_compliance_issues=appt_sop_issues,
                    sop_compliance_positive_behaviors=appt_sop_positives,
                    compliance_target_role=appt_compliance_role,
                    posts=card_posts,
                )

                # ── 8. Result tab ─────────────────────────────────────────────
                has_result = bool(
                    appt_orm.summary or appt_orm.outcome or appt_orm.audio_url
                    or appt_orm.qualification_status
                )
                if has_result:
                    result_convos: list[CardConversation] = []
                    result_last_touched = None
                    result_next_move = None
                    result_summaries: list[str] = []
                    result_key_points: list[str] = []
                    result_action_items: list[str] = []

                    if appt_orm.interaction_id:
                        ir = await self.session.execute(
                            select(CallORM)
                            .options(selectinload(CallORM.analysis))
                            .where(CallORM.id == appt_orm.interaction_id)
                        )
                        ic = ir.scalar_one_or_none()
                        if ic:
                            ia2 = getattr(ic, "analysis", None)
                            result_last_touched = ic.created_at
                            if ia2 and ia2.next_steps:
                                result_next_move = ia2.next_steps[0] if isinstance(ia2.next_steps, list) else str(ia2.next_steps)
                            if ia2 and ia2.summary:
                                result_summaries.append(ia2.summary)
                            if ia2 and ia2.key_points:
                                result_key_points.extend(ia2.key_points)
                            if ia2 and ia2.action_items:
                                result_action_items.extend(ia2.action_items)

                            sop_ck2: list[SOPChecklistItem] = []
                            if ia2:
                                for sn in (ia2.sop_stages_completed or []):
                                    sop_ck2.append(SOPChecklistItem(stage_name=sn, status="completed"))
                                for sn in (ia2.sop_stages_missed or []):
                                    sop_ck2.append(SOPChecklistItem(stage_name=sn, status="missed"))

                            result_convos.append(CardConversation(
                                id=ic.id,
                                call_type=ic.call_type,
                                phone_number=ic.phone_number,
                                duration_seconds=ic.duration_seconds,
                                missed_call=ic.missed_call,
                                created_at=ic.created_at,
                                answered_at=ic.answered_at,
                                call_recording_url=ic.audio_url or appt_orm.audio_url,
                                booking_status=ia2.booking_status if ia2 else appt_orm.booking_status,
                                qualification_status=ia2.qualification_status if ia2 else appt_orm.qualification_status,
                                summary=ia2.summary if ia2 else appt_orm.summary,
                                key_points=list(ia2.key_points) if ia2 and ia2.key_points else [],
                                objections=list(ia2.objections) if ia2 and ia2.objections else list(appt_orm.objections or []),
                                sentiment_score=ia2.sentiment_score if ia2 else None,
                                sop_compliance_score=ia2.sop_compliance_score if ia2 else None,
                                sop_compliance_rate=ia2.sop_compliance_rate if ia2 else None,
                                sop_checklist=sop_ck2,
                                sop_compliance_issues=list(ia2.sop_compliance_issues) if ia2 and ia2.sop_compliance_issues else [],
                                sop_compliance_positive_behaviors=list(ia2.sop_compliance_positive_behaviors) if ia2 and ia2.sop_compliance_positive_behaviors else [],
                                compliance_target_role=ia2.compliance_target_role if ia2 else None,
                            ))

                    if not result_convos and appt_orm.summary:
                        result_last_touched = appt_orm.updated_at or appt_orm.created_at
                        result_summaries.append(appt_orm.summary)

                    # Key lesson from coaching_tips on lead or from extra_metadata
                    key_lesson = None
                    if hasattr(lead_orm, 'coaching_tips') and lead_orm.coaching_tips:
                        key_lesson = lead_orm.coaching_tips
                    elif appt_orm.extra_metadata and isinstance(appt_orm.extra_metadata, dict):
                        key_lesson = appt_orm.extra_metadata.get("key_lesson")

                    # ── Follow-up tracking ────────────────────────────────────
                    pending_result = await self.session.execute(
                        select(PendingActionORM)
                        .where(PendingActionORM.lead_id == lead_id)
                        .order_by(PendingActionORM.due_at.asc().nullslast())
                    )
                    pending_actions = pending_result.scalars().all()

                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    follow_up_tasks = [
                        CardFollowUpTask(
                            id=pa.id,
                            action_type=pa.action_type,
                            raw_text=pa.raw_text,
                            status=pa.status,
                            due_at=pa.due_at,
                            priority=pa.priority,
                        )
                        for pa in pending_actions
                    ]
                    pending_count = sum(1 for pa in pending_actions if pa.status == "pending")
                    completed_count = sum(1 for pa in pending_actions if pa.status == "completed")
                    overdue = any(
                        pa.status == "pending" and pa.due_at and pa.due_at < now
                        for pa in pending_actions
                    )
                    next_fu = None
                    for pa in pending_actions:
                        if pa.status == "pending" and pa.due_at and pa.due_at >= now:
                            next_fu = pa.due_at
                            break

                    fu_last_touched = result_last_touched or lead_orm.updated_at or lead_orm.created_at

                    result_tab = CardResultTab(
                        outcome=appt_orm.outcome,
                        outcome_summary=appt_orm.summary,
                        deal_size=lead_orm.deal_size,
                        key_lesson=key_lesson,
                        overall_engagement=CardEngagement(
                            last_touched=result_last_touched,
                            next_move=result_next_move,
                            summary=" ".join(result_summaries) if result_summaries else None,
                            key_points=list(dict.fromkeys(result_key_points)),
                            action_items=list(dict.fromkeys(result_action_items)),
                        ),
                        conversations=result_convos,
                        follow_up=CardFollowUpTracking(
                            follow_up_attempts=completed_count + pending_count,
                            last_touched=fu_last_touched,
                            is_overdue=overdue,
                            next_follow_up=next_fu,
                            tasks=follow_up_tasks,
                        ),
                    )

            return CustomerCard(
                id=lead_orm.id,
                company_id=lead_orm.company_id,
                status=lead_orm.status,
                deal_status=lead_orm.deal_status,
                pipeline_stage=lead_orm.pipeline_stage,
                deal_size=lead_orm.deal_size,
                created_at=lead_orm.created_at,
                updated_at=lead_orm.updated_at,
                contact=card_contact,
                assigned_rep=assigned_rep,
                pipeline_stages=pipeline_stages,
                lead=lead_tab,
                appointment=appointment_tab,
                result=result_tab,
            )

        except Exception as e:
            logger.error(f"Error getting customer card: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def assign_to_rep(
        self,
        lead_id: UUID,
        sales_rep_id: UUID,
        assigned_by_user_id: UUID,
    ) -> Optional[Lead]:
        """Assign a lead to a sales rep."""
        try:
            # Get the lead
            result = await self.session.execute(
                select(LeadORM).where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            # Store previous assignment info
            previous_rep_id = lead_orm.assigned_rep_id

            # Update assignment
            lead_orm.assigned_rep_id = sales_rep_id

            # Transition pipeline_stage: booked -> appointment when rep is assigned
            from app.domain.enums import PipelineStage
            if lead_orm.pipeline_stage == PipelineStage.BOOKED.value:
                lead_orm.pipeline_stage = PipelineStage.APPOINTMENT.value
                logger.info(
                    f"Transitioned lead pipeline_stage from booked to appointment",
                    lead_id=str(lead_id),
                    assigned_rep_id=str(sales_rep_id),
                )

            # Update extra_metadata to track assignment history
            if lead_orm.extra_metadata is None:
                lead_orm.extra_metadata = {}

            # Store assignment info
            from datetime import datetime, timezone
            from app.core.datetime_utils import isoformat_utc
            assignment_info = {
                "assigned_by": str(assigned_by_user_id),
                "assigned_at": isoformat_utc(datetime.now(timezone.utc)),
                "previous_rep_id": str(previous_rep_id) if previous_rep_id else None,
            }

            # Add to assignment history in metadata
            if "assignment_history" not in lead_orm.extra_metadata:
                lead_orm.extra_metadata["assignment_history"] = []

            lead_orm.extra_metadata["assignment_history"].append(assignment_info)
            lead_orm.extra_metadata["last_assignment"] = assignment_info

            # Update any existing appointments for this lead so their assigned_rep_id matches
            try:
                from app.infrastructure.database.models.appointment import AppointmentORM
                appt_result = await self.session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
                )
                appts = appt_result.scalars().all()
                for ap in appts:
                    ap.assigned_rep_id = sales_rep_id
            except Exception:
                # Non-fatal: log and continue; assignment of lead is primary
                logger.debug(f"Failed to update appointments for lead {lead_id} when assigning to {sales_rep_id}")

            await self.session.commit()

            # Reload lead with relationships for _to_domain
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            return self._to_domain(lead_orm)
        except Exception as e:
            logger.error(f"Error assigning lead to rep: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def update_status(
        self,
        lead_id: UUID,
        status: str,
        changed_by_user_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
    ) -> Optional[Lead]:
        """Update lead status, pipeline_stage, and optionally log to lead_status_changes audit table."""
        try:
            result = await self.session.execute(
                select(LeadORM).where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            old_status = lead_orm.status
            old_deal_status = lead_orm.deal_status
            company_id = lead_orm.company_id

            lead_orm.status = status
            if pipeline_stage is not None:
                lead_orm.pipeline_stage = pipeline_stage
            new_deal_status = lead_orm.deal_status

            if changed_by_user_id is not None:
                audit = LeadStatusChangeORM(
                    lead_id=lead_id,
                    company_id=company_id,
                    changed_by_user_id=changed_by_user_id,
                    old_status=old_status,
                    new_status=status,
                    old_deal_status=old_deal_status,
                    new_deal_status=new_deal_status,
                    reason=reason,
                )
                self.session.add(audit)

            await self.session.commit()

            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            return self._to_domain(lead_orm)
        except Exception as e:
            logger.error(f"Error updating lead status: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def move_pipeline_stage(
        self,
        lead_id: UUID,
        target_stage: "PipelineStage",
        changed_by_user_id: UUID,
        scheduled_start=None,
        scheduled_end=None,
        location_address: str = None,
        assigned_rep_id: UUID = None,
        deal_size: float = None,
        reason: str = None,
    ) -> dict:
        """
        Move lead to a new pipeline stage, update related fields,
        handle appointment side effects, and log an audit trail.
        """
        from app.domain.enums import LeadStatus, AppointmentOutcome
        from uuid import uuid4
        from datetime import timezone

        try:
            result = await self.session.execute(
                select(LeadORM).where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()
            if not lead_orm:
                raise ValueError("Lead not found")

            # Capture old values for audit
            old_status = lead_orm.status
            old_deal_status = lead_orm.deal_status
            previous_stage = lead_orm.pipeline_stage

            appointment_created = False
            appointment_updated = False

            # --- Apply changes per target stage ---
            if target_stage == PipelineStage.QUALIFIED:
                lead_orm.status = LeadStatus.QUALIFIED_UNBOOKED.value
                lead_orm.deal_status = DealStatus.NURTURING.value
                lead_orm.pipeline_stage = PipelineStage.QUALIFIED.value

            elif target_stage == PipelineStage.BOOKED:
                lead_orm.status = LeadStatus.QUALIFIED_BOOKED.value
                lead_orm.deal_status = DealStatus.BOOKED.value
                lead_orm.pipeline_stage = PipelineStage.BOOKED.value
                # Create appointment if none exists
                appt_result = await self.session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
                )
                existing_appt = appt_result.scalar_one_or_none()
                if not existing_appt:
                    new_appt = AppointmentORM(
                        id=uuid4(),
                        company_id=lead_orm.company_id,
                        lead_id=lead_id,
                        contact_card_id=lead_orm.contact_card_id,
                        scheduled_start=scheduled_start,
                        scheduled_end=scheduled_end,
                        location_address=location_address,
                        outcome=AppointmentOutcome.PENDING.value,
                    )
                    self.session.add(new_appt)
                    appointment_created = True

            elif target_stage == PipelineStage.APPOINTMENT:
                lead_orm.status = LeadStatus.QUALIFIED_BOOKED.value
                lead_orm.deal_status = DealStatus.BOOKED.value
                lead_orm.pipeline_stage = PipelineStage.APPOINTMENT.value
                lead_orm.assigned_rep_id = assigned_rep_id
                # Create or update appointment(s)
                appt_result = await self.session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
                )
                existing_appts = appt_result.scalars().all()
                if existing_appts:
                    for existing_appt in existing_appts:
                        existing_appt.assigned_rep_id = assigned_rep_id
                        if scheduled_start:
                            existing_appt.scheduled_start = scheduled_start
                        if scheduled_end:
                            existing_appt.scheduled_end = scheduled_end
                        if location_address:
                            existing_appt.location_address = location_address
                    appointment_updated = True
                else:
                    new_appt = AppointmentORM(
                        id=uuid4(),
                        company_id=lead_orm.company_id,
                        lead_id=lead_id,
                        contact_card_id=lead_orm.contact_card_id,
                        scheduled_start=scheduled_start,
                        scheduled_end=scheduled_end,
                        location_address=location_address,
                        assigned_rep_id=assigned_rep_id,
                        outcome=AppointmentOutcome.PENDING.value,
                    )
                    self.session.add(new_appt)
                    appointment_created = True

            elif target_stage == PipelineStage.APPOINTMENT_RAN:
                lead_orm.pipeline_stage = PipelineStage.APPOINTMENT_RAN.value

            elif target_stage == PipelineStage.WON:
                lead_orm.status = LeadStatus.CLOSED_WON.value
                lead_orm.deal_status = DealStatus.WON.value
                lead_orm.pipeline_stage = PipelineStage.WON.value
                lead_orm.deal_size = deal_size
                lead_orm.closed_at = datetime.now(timezone.utc)
                # Update appointment outcome if exists
                appt_result = await self.session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
                )
                existing_appt = appt_result.scalar_one_or_none()
                if existing_appt:
                    existing_appt.outcome = AppointmentOutcome.WON.value
                    appointment_updated = True

            elif target_stage == PipelineStage.LOST:
                lead_orm.status = LeadStatus.CLOSED_LOST.value
                lead_orm.deal_status = DealStatus.LOST.value
                lead_orm.pipeline_stage = PipelineStage.LOST.value
                lead_orm.closed_at = datetime.now(timezone.utc)
                # Update appointment outcome if exists
                appt_result = await self.session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead_id)
                )
                existing_appt = appt_result.scalar_one_or_none()
                if existing_appt:
                    existing_appt.outcome = AppointmentOutcome.LOST.value
                    appointment_updated = True

            # Always log audit trail
            audit = LeadStatusChangeORM(
                lead_id=lead_id,
                company_id=lead_orm.company_id,
                changed_by_user_id=changed_by_user_id,
                old_status=old_status,
                new_status=lead_orm.status,
                old_deal_status=old_deal_status,
                new_deal_status=lead_orm.deal_status,
                reason=reason or f"Pipeline stage moved to {target_stage.value}",
            )
            self.session.add(audit)

            await self.session.commit()

            # Reload lead with relationships
            result = await self.session.execute(
                select(LeadORM)
                .options(
                    selectinload(LeadORM.contact_card),
                    selectinload(LeadORM.calls).selectinload(CallORM.analysis)
                )
                .where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()
            lead_domain = self._to_domain(lead_orm) if lead_orm else None

            return {
                "lead": lead_domain,
                "previous_stage": previous_stage,
                "new_stage": target_stage.value,
                "appointment_created": appointment_created,
                "appointment_updated": appointment_updated,
            }
        except Exception as e:
            logger.error(f"Error moving lead pipeline stage: {e}")
            import traceback
            traceback.print_exc()
            raise e
