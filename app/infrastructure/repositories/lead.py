"""
Lead repository.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, or_, and_, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import LeadDetail, ContactInfo, AgentInfo, OverallEngagement, Conversation
from app.domain.enums import DealStatus
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.pending_action import PendingActionORM
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

        # Convert to domain model
        lead_data = {
            "id": orm_obj.id,
            "company_id": orm_obj.company_id,
            "contact_card_id": orm_obj.contact_card_id,
            "status": orm_obj.status,
            "deal_status": deal_status,
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

            # Update extra_metadata to track assignment history
            if lead_orm.extra_metadata is None:
                lead_orm.extra_metadata = {}

            # Store assignment info
            from datetime import datetime, timezone
            assignment_info = {
                "assigned_by": str(assigned_by_user_id),
                "assigned_at": datetime.now(timezone.utc).isoformat(),
                "previous_rep_id": str(previous_rep_id) if previous_rep_id else None,
            }

            # Add to assignment history in metadata
            if "assignment_history" not in lead_orm.extra_metadata:
                lead_orm.extra_metadata["assignment_history"] = []

            lead_orm.extra_metadata["assignment_history"].append(assignment_info)
            lead_orm.extra_metadata["last_assignment"] = assignment_info

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
    ) -> Optional[Lead]:
        """Update lead status."""
        try:
            # Get the lead
            result = await self.session.execute(
                select(LeadORM).where(LeadORM.id == lead_id)
            )
            lead_orm = result.scalar_one_or_none()

            if not lead_orm:
                return None

            # Update status
            lead_orm.status = status

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
            logger.error(f"Error updating lead status: {e}")
            import traceback
            traceback.print_exc()
            raise e
