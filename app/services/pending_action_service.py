"""
Pending action service.

Provides business logic for managing pending actions:
- Fetching by urgency
- Marking as completed/converted
- Conversion metrics
- Task management (list with summary, detail, update, create manual)
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.pending_action import PendingAction
from app.domain.enums import PendingActionStatus
from app.domain.schemas.tasks import (
    TaskListItem,
    TaskListSummary,
    TaskListResponse,
    TaskDetailResponse,
    AssigneeInfo,
    SourceCallInfo,
    ActionCenterItem,
    ActionCenterGroup,
    ActionCenterSummary,
    ActionCenterResponse,
    FollowUpGuidanceResponse,
    DoNext,
    SayNext,
    GuidanceContext,
    GuidanceObjectionResponse,
)
from app.core.config import settings
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.follow_up_otto import FollowUpOttoORM

logger = get_logger(__name__)

MISSED_CALL_CALLBACK_MINUTES = 15
MISSED_CALL_PRIORITY = 1

# ── Action Center ranking ────────────────────────────────────────────────

# Urgency tiers in display order.
ACTION_CENTER_TIER_ORDER = [
    "overdue",
    "due_now",
    "due_soon",
    "later_today",
    "upcoming",
    "no_due_date",
]
ACTION_CENTER_TIER_LABELS = {
    "overdue": "Overdue",
    "due_now": "Due now",
    "due_soon": "Due soon",
    "later_today": "Later today",
    "upcoming": "Upcoming",
    "no_due_date": "No due date",
}
# Aligns with NOTIFICATION_THRESHOLDS in followup_notification_service.
_DUE_NOW_MAX_MIN = 15
_DUE_SOON_MAX_MIN = 120


def normalize_action_family(action_type: Optional[str]) -> Optional[str]:
    """Map an action_type to one of the four Action Center families, else None."""
    if not action_type:
        return None
    t = action_type.strip().lower()
    if not t:
        return None
    if t in ("call_back", "callback"):
        return "call_back"
    if t == "appointment_reminder":
        return "appointment_reminder"
    if t == "rehash":
        return "rehash"
    if t.startswith("follow_up"):
        return "follow_up"
    return None


def compute_value_score(action_type: Optional[str], extra_metadata: Optional[dict]) -> int:
    """Business-value score within a tier (higher = surface sooner).

    Independent of the misleading DB `priority` column (lower=hotter in prod).
    """
    family = normalize_action_family(action_type)
    meta = extra_metadata or {}
    if family == "call_back":
        return 100
    if family == "appointment_reminder":
        kind = meta.get("reminder_kind")
        if kind == "one_hour_before":
            return 95
        if kind in ("morning_of", "day_before"):
            return 70
        return 75  # appointment_reminder with no/unknown kind
    if family == "follow_up":
        return 80
    if family == "rehash":
        category = meta.get("rehash_category")
        if category == "appointment_pending":
            return 65
        if category == "qualified_unbooked":
            return 60
        if category == "stale_lead":
            return 55
        return 50  # rehash, unknown category
    return 0


def compute_urgency_tier(
    due_at: Optional[datetime], now_utc: datetime, tz: ZoneInfo
) -> tuple[str, Optional[int]]:
    """Return (tier_id, minutes_until_due). minutes_until_due is None when no due_at."""
    if due_at is None:
        return "no_due_date", None
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo("UTC"))
    minutes_until_due = int((due_at - now_utc).total_seconds() / 60)
    if minutes_until_due < 0:
        return "overdue", minutes_until_due
    if minutes_until_due <= _DUE_NOW_MAX_MIN:
        return "due_now", minutes_until_due
    if minutes_until_due <= _DUE_SOON_MAX_MIN:
        return "due_soon", minutes_until_due
    # Later today vs upcoming uses local calendar day.
    if due_at.astimezone(tz).date() == now_utc.astimezone(tz).date():
        return "later_today", minutes_until_due
    return "upcoming", minutes_until_due


def _display_title(action_type: Optional[str], raw_text: Optional[str], meta: Optional[dict]) -> str:
    family = normalize_action_family(action_type)
    meta = meta or {}
    if raw_text:
        return raw_text
    if family == "call_back":
        return "Call back customer"
    if family == "appointment_reminder":
        kind = meta.get("reminder_kind")
        return f"Appointment reminder ({kind})" if kind else "Appointment reminder"
    if family == "rehash":
        return "Rehash opportunity"
    if family == "follow_up":
        return "Follow up"
    return action_type or "Action"


def _sort_key(item: ActionCenterItem):
    """Global sort: tier order, then value_score desc, due_at asc, created_at asc."""
    tier_rank = ACTION_CENTER_TIER_ORDER.index(item.urgency_tier)
    # due_at/created_at None sort last within their group.
    due_sort = item.due_at.timestamp() if item.due_at else float("inf")
    created_sort = item.created_at.timestamp() if item.created_at else float("inf")
    return (tier_rank, -item.value_score, due_sort, created_sort)


def objections_from_raw_analysis(raw_analysis: Optional[dict]) -> List[dict]:
    """Extract objections (with response suggestions) from a Shunya raw_analysis blob.

    Shunya stores rich objection objects under raw_analysis["objections"]["objections"]
    (or a bare list). Returns normalized dicts: {objection, suggested_response}. The
    structured ObjectionDetail APIs drop these suggestions today — this recovers them
    without re-calling the model.
    """
    if not raw_analysis or not isinstance(raw_analysis, dict):
        return []
    section = raw_analysis.get("objections")
    if isinstance(section, dict):
        items = section.get("objections", [])
    elif isinstance(section, list):
        items = section
    else:
        items = []

    out: List[dict] = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        text = obj.get("objection_text") or obj.get("text") or obj.get("category_text")
        if not text:
            continue
        # Suggestions may be a list or a single string under several key names.
        suggestions = (
            obj.get("response_suggestions")
            or obj.get("suggested_responses")
            or obj.get("suggested_response")
        )
        suggested_response = None
        if isinstance(suggestions, list):
            suggested_response = next((s for s in suggestions if s), None)
        elif isinstance(suggestions, str):
            suggested_response = suggestions or None
        out.append({"objection": text, "suggested_response": suggested_response})
    return out


def response_suggestions_for_objection(
    raw_analysis: Optional[dict], objection_text: Optional[str]
) -> List[str]:
    """Return response_suggestions list for a specific objection_text from raw_analysis.

    Used by call/appointment insight builders to fill ObjectionDetail.response_suggestions.
    """
    if not raw_analysis or not isinstance(raw_analysis, dict) or not objection_text:
        return []
    section = raw_analysis.get("objections")
    if isinstance(section, dict):
        items = section.get("objections", [])
    elif isinstance(section, list):
        items = section
    else:
        items = []
    target = objection_text.strip().lower()
    for obj in items:
        if not isinstance(obj, dict):
            continue
        text = (obj.get("objection_text") or obj.get("text") or "").strip().lower()
        if text and text == target:
            suggestions = (
                obj.get("response_suggestions")
                or obj.get("suggested_responses")
                or obj.get("suggested_response")
            )
            if isinstance(suggestions, list):
                return [s for s in suggestions if s]
            if isinstance(suggestions, str) and suggestions:
                return [suggestions]
    return []


async def create_missed_call_pending_action(
    session: AsyncSession,
    *,
    company_id: UUID,
    call_id: UUID,
    phone: str,
    lead_id: Optional[UUID] = None,
    owner_id: Optional[UUID] = None,
) -> PendingAction:
    """Create a standardized call_back pending action for missed calls."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    pending_action = PendingAction(
        company_id=company_id,
        lead_id=lead_id,
        call_id=call_id,
        action_type="call_back",
        raw_text=f"Give {phone} a call back",
        status=PendingActionStatus.PENDING,
        due_at=now_utc + timedelta(minutes=MISSED_CALL_CALLBACK_MINUTES),
        priority=MISSED_CALL_PRIORITY,
        owner_id=owner_id,
        source="manual",
    )
    repo = PendingActionRepository(session)
    existing = await repo.get_pending_call_back(company_id, call_id)
    if existing:
        logger.info(
            "Skipped duplicate missed-call pending action",
            call_id=str(call_id),
            phone=phone,
        )
        return existing

    created = await repo.create(pending_action)
    logger.info(
        "Created missed-call pending action",
        call_id=str(call_id),
        phone=phone,
        due_at=pending_action.due_at.isoformat() if pending_action.due_at else None,
    )
    return created


def _owner_to_assignee(owner_orm) -> Optional[AssigneeInfo]:
    if not owner_orm:
        return None
    first = getattr(owner_orm, "first_name", None) or ""
    last = getattr(owner_orm, "last_name", None) or ""
    full = f"{first} {last}".strip() or None
    return AssigneeInfo(
        user_id=owner_orm.id,
        first_name=getattr(owner_orm, "first_name", None),
        last_name=getattr(owner_orm, "last_name", None),
        full_name=full,
        role=getattr(owner_orm, "role", None),
        email=getattr(owner_orm, "email", None),
    )


def _build_source_call(call_orm) -> Optional[SourceCallInfo]:
    if not call_orm:
        return None
    contact = getattr(call_orm, "contact_card", None)
    customer_name = None
    customer_phone = None
    if contact:
        first = getattr(contact, "first_name", None) or ""
        last = getattr(contact, "last_name", None) or ""
        customer_name = f"{first} {last}".strip() or None
        customer_phone = getattr(contact, "primary_phone", None)
    return SourceCallInfo(
        call_id=getattr(call_orm, "id", None),
        customer_name=customer_name,
        customer_phone=customer_phone,
        call_date=getattr(call_orm, "answered_at", None) or getattr(call_orm, "created_at", None),
        call_created_at=getattr(call_orm, "created_at", None),
    )


class PendingActionService:
    """Service for pending action operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.pending_action_repo = PendingActionRepository(session)
    
    async def fetch_by_urgency(
        self,
        company_id: UUID,
        limit: int = 100,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Fetch pending actions sorted by urgency (due_at + priority).
        
        Args:
            company_id: Company ID
            limit: Maximum number of actions to return
            status: Optional status filter (defaults to PENDING)
            
        Returns:
            List of pending actions sorted by urgency
        """
        try:
            return await self.pending_action_repo.get_by_urgency(
                company_id=company_id,
                limit=limit,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error fetching pending actions by urgency: {e}")
            raise e
    
    async def mark_completed(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as completed.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.COMPLETED,
            )
        except Exception as e:
            logger.error(f"Error marking action as completed: {e}", action_id=str(action_id))
            raise e
    
    async def reopen(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Reopen a pending action (set status back to pending).
        Use when a CSR or sales rep mistakenly marked an action as complete.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.PENDING,
            )
        except Exception as e:
            logger.error(f"Error reopening pending action: {e}", action_id=str(action_id))
            raise e
    
    async def mark_converted(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as converted.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.CONVERTED,
            )
        except Exception as e:
            logger.error(f"Error marking action as converted: {e}", action_id=str(action_id))
            raise e
    
    async def get_conversion_metrics(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get conversion metrics (pending → converted).
        
        Args:
            company_id: Company ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dict with conversion metrics
        """
        try:
            # Convert dates to datetimes if provided
            start_dt = None
            end_dt = None
            if start_date:
                start_dt = datetime.combine(start_date, datetime.min.time())
            if end_date:
                end_dt = datetime.combine(end_date, datetime.max.time())
            
            return await self.pending_action_repo.get_conversion_metrics(
                company_id=company_id,
                start_date=start_dt,
                end_date=end_dt,
            )
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            raise e
    
    async def get_by_company(
        self,
        company_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a company.
        
        Args:
            company_id: Company ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_company(
                company_id=company_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by company: {e}")
            raise e
    
    async def get_by_lead(
        self,
        lead_id: UUID,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a lead.
        
        Args:
            lead_id: Lead ID
            status: Optional status filter
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_lead(
                lead_id=lead_id,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by lead: {e}")
            raise e
    
    async def get_by_owner(
        self,
        owner_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for an owner/user.
        
        Args:
            owner_id: Owner/user ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_owner(
                owner_id=owner_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by owner: {e}")
            raise e

    async def create_from_call(
        self,
        call_id: UUID,
        company_id: UUID,
        lead_id: Optional[UUID],
        owner_id: UUID,
        assigned_by_id: UUID,
        action_type: str,
        raw_text: Optional[str] = None,
        due_at: Optional[datetime] = None,
        priority: Optional[int] = None,
    ) -> PendingAction:
        """
        Create a pending action linked to a call, assigned to a user (e.g. executive assigning to CSR).
        
        Args:
            call_id: Call this action is tied to
            company_id: Company ID
            lead_id: Lead ID from the call (optional)
            owner_id: User to assign the action to (CSR)
            assigned_by_id: User creating/assigning the action (e.g. executive)
            action_type: Type of action
            raw_text: Optional description
            due_at: Optional due date
            priority: Optional priority
        Returns:
            Created PendingAction
        """
        pending = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            call_id=call_id,
            appointment_id=None,
            action_type=action_type,
            raw_text=raw_text,
            status=PendingActionStatus.PENDING,
            due_at=due_at,
            priority=priority,
            owner_id=owner_id,
            assigned_by_id=assigned_by_id,
            source="manual",
            extra_metadata=None,
        )
        return await self.pending_action_repo.create(pending)

    async def list_tasks_with_summary(
        self,
        company_id: UUID,
        *,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[UUID] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        due_date_from: Optional[datetime] = None,
        due_date_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """List tasks with filters and summary counts for Task Management page (CSR 'My Tasks' uses assignee_id=current user)."""
        # Query pending_actions for task management summaries
        counts_query = (
            select(PendingActionORM.status, func.count(PendingActionORM.id).label("count"))
            .where(PendingActionORM.company_id == company_id)
            .group_by(PendingActionORM.status)
        )
        res = await self.session.execute(counts_query)
        counts_rows = res.fetchall()
        counts = {row[0]: row[1] for row in counts_rows}
        # Build summary from pending_actions counts
        summary = TaskListSummary(
            total_tasks=sum(counts.values()),
            pending=counts.get(PendingActionStatus.PENDING.value, 0),
            in_progress=counts.get(PendingActionStatus.IN_PROGRESS.value, 0),
            completed=counts.get(PendingActionStatus.COMPLETED.value, 0),
            cancelled=counts.get(PendingActionStatus.CANCELLED.value, 0),
        )
        # Build base filter conditions
        filters = [PendingActionORM.company_id == company_id]

        if status:
            filters.append(PendingActionORM.status == status)
        if priority is not None:
            filters.append(PendingActionORM.priority == priority)
        if assignee_id:
            filters.append(PendingActionORM.owner_id == assignee_id)
        if start_date:
            filters.append(PendingActionORM.created_at >= start_date)
        if end_date:
            filters.append(PendingActionORM.created_at <= end_date)
        if due_date_from:
            filters.append(PendingActionORM.due_at >= due_date_from)
        if due_date_to:
            filters.append(PendingActionORM.due_at <= due_date_to)
        if search:
            search_term = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(PendingActionORM.raw_text).like(search_term),
                    func.lower(PendingActionORM.action_type).like(search_term),
                )
            )

        query = (
            select(PendingActionORM)
            .options(
                selectinload(PendingActionORM.call).selectinload(CallORM.contact_card),
                selectinload(PendingActionORM.owner),
                selectinload(PendingActionORM.assigned_by),
            )
            .where(*filters)
            .order_by(PendingActionORM.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        orm_list = result.scalars().all()
        # total count (with same filters applied)
        total_res = await self.session.execute(select(func.count(PendingActionORM.id)).where(*filters))
        total = total_res.scalar() or 0
        tasks = []
        for row in orm_list:
            owner = getattr(row, "owner", None)
            assigned_by = getattr(row, "assigned_by", None)
            call = getattr(row, "call", None)
            tasks.append(TaskListItem(
                id=row.id,
                company_id=row.company_id,
                action_type=row.action_type,
                raw_text=row.raw_text,
                status=row.status,
                priority=row.priority,
                due_at=row.due_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
                owner_id=row.owner_id,
                assigned_to=_owner_to_assignee(owner),
                assigned_by=_owner_to_assignee(assigned_by),
                source_call=_build_source_call(call),
                call_id=row.call_id,
                lead_id=row.lead_id,
                assigned_by_id=row.assigned_by_id,
            ))
        return {
            "summary": summary,
            "tasks": tasks,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def _to_action_center_item(
        self, row: PendingActionORM, now_utc: datetime, tz: ZoneInfo
    ) -> Optional[ActionCenterItem]:
        """Map an ORM row to a ranked ActionCenterItem; None if not in scope."""
        family = normalize_action_family(row.action_type)
        if family is None:
            return None
        meta = row.extra_metadata or None
        tier, minutes_until_due = compute_urgency_tier(row.due_at, now_utc, tz)
        value_score = compute_value_score(row.action_type, meta)
        # Surface stuck items above same-tier reminders.
        if tier == "overdue":
            value_score += 5
        owner = getattr(row, "owner", None)
        call = getattr(row, "call", None)
        return ActionCenterItem(
            id=row.id,
            company_id=row.company_id,
            action_type=row.action_type,
            raw_text=row.raw_text,
            status=row.status,
            priority=row.priority,
            due_at=row.due_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            owner_id=row.owner_id,
            assigned_to=_owner_to_assignee(owner),
            source_call=_build_source_call(call),
            call_id=row.call_id,
            lead_id=row.lead_id,
            assigned_by_id=row.assigned_by_id,
            urgency_tier=tier,
            value_score=value_score,
            minutes_until_due=minutes_until_due,
            action_family=family,
            source=row.source,
            appointment_id=row.appointment_id,
            extra_metadata=meta,
            display_title=_display_title(row.action_type, row.raw_text, meta),
        )

    async def get_action_center(
        self,
        *,
        company_id: UUID,
        owner_id: UUID,
        limit: int = 50,
        include_in_progress: bool = False,
    ) -> ActionCenterResponse:
        """Aggregate, rank, and group a rep's actionable pending items."""
        now_utc = datetime.now(ZoneInfo("UTC"))
        try:
            tz = ZoneInfo(settings.APPOINTMENT_REMINDER_TZ)
        except Exception:
            tz = ZoneInfo("America/New_York")

        statuses = [PendingActionStatus.PENDING.value]
        if include_in_progress:
            statuses.append(PendingActionStatus.IN_PROGRESS.value)

        # Safety cap at 2x limit so a huge queue can't blow up the response.
        rows = await self.pending_action_repo.list_for_action_center(
            company_id=company_id,
            owner_id=owner_id,
            statuses=statuses,
            limit=max(limit * 2, limit),
        )

        items = [
            item
            for row in rows
            if (item := self._to_action_center_item(row, now_utc, tz)) is not None
        ]
        items.sort(key=_sort_key)
        items = items[:limit]

        # Summary
        by_action_type: Dict[str, int] = {}
        for it in items:
            by_action_type[it.action_family] = by_action_type.get(it.action_family, 0) + 1
        summary = ActionCenterSummary(
            total=len(items),
            overdue=sum(1 for it in items if it.urgency_tier == "overdue"),
            due_now=sum(1 for it in items if it.urgency_tier == "due_now"),
            due_soon=sum(1 for it in items if it.urgency_tier == "due_soon"),
            by_action_type=by_action_type,
        )

        # Groups in tier display order (only non-empty tiers).
        groups: List[ActionCenterGroup] = []
        for tier in ACTION_CENTER_TIER_ORDER:
            tier_items = [it for it in items if it.urgency_tier == tier]
            if not tier_items:
                continue
            groups.append(
                ActionCenterGroup(
                    urgency_tier=tier,
                    label=ACTION_CENTER_TIER_LABELS[tier],
                    count=len(tier_items),
                    items=tier_items,
                )
            )

        return ActionCenterResponse(
            generated_at=now_utc,
            company_id=company_id,
            owner_id=owner_id,
            next=items[0] if items else None,
            summary=summary,
            groups=groups,
        )

    async def get_task_detail(self, task_id: UUID) -> Optional[Dict[str, Any]]:
        """Get single task with full details (owner, assigned_by, source call)."""
        query = (
            select(PendingActionORM)
            .where(PendingActionORM.id == task_id)
            .options(
                selectinload(PendingActionORM.owner),
                selectinload(PendingActionORM.assigned_by),
                selectinload(PendingActionORM.call).selectinload(CallORM.contact_card),
            )
        )
        result = await self.session.execute(query)
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "company_id": row.company_id,
            "lead_id": row.lead_id,
            "call_id": row.call_id,
            "appointment_id": row.appointment_id,
            "action_type": row.action_type,
            "raw_text": row.raw_text,
            "status": row.status,
            "priority": row.priority,
            "due_at": row.due_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "owner_id": row.owner_id,
            "assigned_to": _owner_to_assignee(getattr(row, "owner", None)),
            "assigned_by_id": row.assigned_by_id,
            "assigned_by": _owner_to_assignee(getattr(row, "assigned_by", None)),
            "source_call": _build_source_call(getattr(row, "call", None)),
            "source": row.source,
        }

    async def get_follow_up_guidance(
        self,
        task_id: UUID,
        *,
        include_sms: bool = False,
    ) -> Optional[FollowUpGuidanceResponse]:
        """Assemble read-only "say next" + "do next" guidance for a pending action.

        Resolver priority (first hit wins for say_next, context is merged):
          1. follow_up_otto row linked by pending_action_id → rep nudge script / SMS.
          2. linked call_analyses (via call_id) → next_steps, reason, objections.
          3. raw_analysis objections (recovers dropped response_suggestions).
          4. appointment row (next_steps/key_points) + its booking-call analysis.
          5. lead's most recent call analysis.
          6. fallback: pending_action.raw_text only.
        """
        # Load the action with its linked call + contact for context.
        query = (
            select(PendingActionORM)
            .where(PendingActionORM.id == task_id)
            .options(selectinload(PendingActionORM.call).selectinload(CallORM.contact_card))
        )
        result = await self.session.execute(query)
        action = result.scalar_one_or_none()
        if not action:
            return None

        family = normalize_action_family(action.action_type)
        sources: List[str] = []
        say = SayNext()
        context = GuidanceContext()

        # do_next from the action itself.
        do_next = DoNext(
            title=_display_title(action.action_type, action.raw_text, action.extra_metadata),
            action_text=action.raw_text,
            due_at=action.due_at,
        )

        # Context from a linked call's contact card.
        call = getattr(action, "call", None)
        contact = getattr(call, "contact_card", None) if call else None
        if contact is not None:
            first = (contact.first_name or "").strip()
            last = (contact.last_name or "").strip()
            context.customer_name = f"{first} {last}".strip() or None
            context.phone = contact.primary_phone

        # ── 1. follow_up_otto rep nudge / SMS ────────────────────────────
        otto = await self._load_follow_up_otto(action)
        if otto is not None:
            sources.append("follow_up_otto")
            say.opening_line = otto.opening_line
            say.close_approach = otto.close_approach
            if isinstance(otto.key_talking_points, list):
                say.talking_points = [str(p) for p in otto.key_talking_points if p]
            if isinstance(otto.objections, list):
                for o in otto.objections:
                    if isinstance(o, dict) and (o.get("objection") or o.get("suggested_response")):
                        say.objection_responses.append(
                            GuidanceObjectionResponse(
                                objection=o.get("objection") or "",
                                suggested_response=o.get("suggested_response"),
                            )
                        )
            if include_sms and otto.action_type == "sms_to_lead":
                say.sms_draft = otto.message_content

        # ── 2/3. call analysis (via call_id) + raw_analysis objections ───
        analysis = await self._load_call_analysis(action.call_id)
        # ── 4. appointment row / booking-call analysis ───────────────────
        if analysis is None and action.appointment_id is not None:
            analysis = await self._load_appointment_analysis(action.appointment_id, context)
        # ── 5. lead's most recent call analysis ──────────────────────────
        if analysis is None and action.lead_id is not None:
            analysis = await self._load_latest_lead_analysis(action.lead_id)

        if analysis is not None:
            sources.append("call_analysis")
            if not say.next_steps and isinstance(analysis.next_steps, list):
                say.next_steps = [str(s) for s in analysis.next_steps if s]
            if say.follow_up_reason is None:
                say.follow_up_reason = analysis.follow_up_reason
            if not context.key_points and isinstance(analysis.key_points, list):
                context.key_points = [str(k) for k in analysis.key_points if k]
            if context.summary is None:
                context.summary = analysis.summary
            if context.service_requested is None:
                context.service_requested = analysis.service_requested
            if context.customer_name is None:
                context.customer_name = analysis.customer_name
            # Recover dropped objection response suggestions from raw_analysis.
            if not say.objection_responses:
                parsed = objections_from_raw_analysis(analysis.raw_analysis)
                if parsed:
                    sources.append("raw_analysis")
                    say.objection_responses = [
                        GuidanceObjectionResponse(
                            objection=p["objection"], suggested_response=p.get("suggested_response")
                        )
                        for p in parsed
                    ]

        if not sources:
            sources.append("pending_action")

        return FollowUpGuidanceResponse(
            pending_action_id=action.id,
            action_family=family,
            do_next=do_next,
            say_next=say,
            context=context,
            sources=sources,
        )

    async def _load_follow_up_otto(self, action: PendingActionORM) -> Optional[FollowUpOttoORM]:
        """Load the best follow_up_otto row: by pending_action_id, else latest for lead."""
        # Prefer a direct link.
        res = await self.session.execute(
            select(FollowUpOttoORM)
            .where(FollowUpOttoORM.pending_action_id == action.id)
            .order_by(FollowUpOttoORM.created_at.desc())
            .limit(1)
        )
        row = res.scalar_one_or_none()
        if row is not None:
            return row
        # Else latest proposed/sent nudge for the lead.
        if action.lead_id is None:
            return None
        res = await self.session.execute(
            select(FollowUpOttoORM)
            .where(FollowUpOttoORM.lead_id == action.lead_id)
            .order_by(FollowUpOttoORM.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def _load_call_analysis(self, call_id: Optional[UUID]) -> Optional[CallAnalysisORM]:
        if call_id is None:
            return None
        res = await self.session.execute(
            select(CallAnalysisORM).where(CallAnalysisORM.call_id == call_id).limit(1)
        )
        return res.scalar_one_or_none()

    async def _load_appointment_analysis(
        self, appointment_id: UUID, context: GuidanceContext
    ) -> Optional[CallAnalysisORM]:
        """Load the booking-call analysis linked to an appointment via interaction_id."""
        res = await self.session.execute(
            select(AppointmentORM).where(AppointmentORM.id == appointment_id).limit(1)
        )
        appt = res.scalar_one_or_none()
        if appt is None:
            return None
        # Appointment-level fields as context fallback.
        if context.summary is None:
            context.summary = getattr(appt, "summary", None)
        if not context.key_points and isinstance(getattr(appt, "key_points", None), list):
            context.key_points = [str(k) for k in appt.key_points if k]
        if appt.interaction_id is not None:
            return await self._load_call_analysis(appt.interaction_id)
        return None

    async def _load_latest_lead_analysis(self, lead_id: UUID) -> Optional[CallAnalysisORM]:
        """Most recent call analysis for any call belonging to the lead."""
        res = await self.session.execute(
            select(CallAnalysisORM)
            .join(CallORM, CallORM.id == CallAnalysisORM.call_id)
            .where(CallORM.lead_id == lead_id)
            .order_by(CallAnalysisORM.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def update_task(
        self,
        task_id: UUID,
        *,
        owner_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        raw_text: Optional[str] = None,
        assigned_by_id: Optional[UUID] = None,
    ) -> Optional[PendingAction]:
        """Update task (reassign, status, priority, due_at, raw_text)."""
        # Update the pending_action fields directly
        orm_obj = await self.session.get(PendingActionORM, task_id)
        if not orm_obj:
            return None
        if owner_id is not None:
            orm_obj.owner_id = owner_id
        if status is not None:
            orm_obj.status = status
        if priority is not None:
            orm_obj.priority = priority
        if due_at is not None:
            orm_obj.due_at = due_at
        if raw_text is not None:
            orm_obj.raw_text = raw_text
        if assigned_by_id is not None:
            orm_obj.assigned_by_id = assigned_by_id
        await self.session.flush()
        await self.session.refresh(orm_obj)

        updated = PendingAction(
            id=orm_obj.id,
            company_id=orm_obj.company_id,
            lead_id=orm_obj.lead_id,
            call_id=orm_obj.call_id,
            appointment_id=orm_obj.appointment_id,
            action_type=orm_obj.action_type,
            raw_text=orm_obj.raw_text,
            status=orm_obj.status,
            priority=orm_obj.priority,
            due_at=orm_obj.due_at,
            owner_id=orm_obj.owner_id,
            assigned_by_id=orm_obj.assigned_by_id,
            source=orm_obj.source,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

        # If an owner (sales rep) was provided and the action item is linked to a lead,
        # ensure the lead is assigned to that rep and create an appointment record if the lead
        # is already booked (or deal_status indicates 'booked').
        try:
            if owner_id is not None:
                lead_id = orm_obj.lead_id
                company_id = orm_obj.company_id
                if lead_id and company_id:
                    from app.infrastructure.repositories.lead import LeadRepository
                    from app.infrastructure.repositories.appointment import AppointmentRepository
                    from app.domain.models.appointment import Appointment as AppointmentDomain
                    from datetime import datetime as dt_cls, timezone

                    lead_repo = LeadRepository(self.session)
                    appointment_repo = AppointmentRepository(self.session)

                    # Assign the lead to the sales rep
                    await lead_repo.assign_to_rep(lead_id=lead_id, sales_rep_id=owner_id, assigned_by_user_id=assigned_by_id)

                    # Reload lead to check status and contact_card
                    lead = await lead_repo.get_by_id(lead_id)
                    lead_deal_status = getattr(lead, "deal_status", None)
                    lead_status = getattr(lead, "status", None)
                    contact_card_id = getattr(lead, "contact_card_id", None)

                    is_booked = False
                    if lead_status and str(lead_status).lower() == "qualified_booked":
                        is_booked = True
                    if lead_deal_status and str(lead_deal_status).lower() == "booked":
                        is_booked = True

                    if is_booked and contact_card_id:
                        existing_appt = await appointment_repo.get_by_lead_id(lead_id)
                        if not existing_appt:
                            appt = AppointmentDomain(
                                company_id=company_id,
                                lead_id=lead_id,
                                contact_card_id=contact_card_id,
                                scheduled_start=dt_cls.now(timezone.utc),
                                scheduled_end=None,
                                location_address=None,
                                latitude=None,
                                longitude=None,
                                outcome=None,
                                assigned_rep_id=owner_id,
                                interaction_id=None,
                                audio_url=None,
                                extra_metadata={"created_from": "csr_assignment", "assigned_via": "task_update"},
                            )
                            await appointment_repo.create(appt)
        except Exception as e:
            logger.warning(f"Could not create appointment on assignment: {e}")

        return updated

    async def create_task_manual(
        self,
        company_id: UUID,
        assigned_by_id: UUID,
        action_type: str,
        *,
        raw_text: Optional[str] = None,
        status: Optional[str] = "pending",
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        owner_id: Optional[UUID] = None,
        lead_id: Optional[UUID] = None,
        call_id: Optional[UUID] = None,
        appointment_id: Optional[UUID] = None,
    ) -> PendingAction:
        """Create a task manually (not from a call)."""
        status_enum = PendingActionStatus.PENDING
        if status:
            try:
                status_enum = PendingActionStatus(status)
            except ValueError:
                pass
        pending = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            call_id=call_id,
            appointment_id=appointment_id,
            action_type=action_type,
            raw_text=raw_text,
            status=status_enum,
            due_at=due_at,
            priority=priority,
            owner_id=owner_id,
            assigned_by_id=assigned_by_id,
            source="manual",
            extra_metadata=None,
        )
        return await self.pending_action_repo.create(pending)
