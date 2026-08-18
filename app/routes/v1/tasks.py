"""
Task Management API routes.

Executives can list, create, update, and assign action items (tasks) to CSRs and Sales Reps.
Tasks are stored in pending_actions and may be linked to calls, leads, or appointments.
"""
import traceback
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role, require_executive
from app.core.logging import get_logger
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.models.pending_action import PendingAction
from app.domain.schemas.tasks import (
    TaskListResponse,
    TaskDetailResponse,
    TaskListSummary,
    TaskListItem,
    CreateTaskRequest,
    UpdateTaskRequest,
    ActionCenterResponse,
    FollowUpGuidanceResponse,
    RehashSyncResponse,
)
from app.services.pending_action_service import PendingActionService

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Task not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


@router.get("", response_model=TaskListResponse, responses=RESPONSES)  # type: ignore
async def list_tasks(
    db: DbSession,
    company_id: UUID = Query(..., description="Company ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, in_progress, completed, cancelled"),
    priority: Optional[int] = Query(None, description="Filter by priority (integer)"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee (owner) user ID"),
    search: Optional[str] = Query(None, description="Search in task title/description (raw_text) or customer name/phone/email from source call"),
    start_date: Optional[datetime] = Query(None, description="Filter tasks created on or after (ISO datetime)"),
    end_date: Optional[datetime] = Query(None, description="Filter tasks created on or before (ISO datetime)"),
    due_date_from: Optional[datetime] = Query(None, description="Filter by due_at on or after"),
    due_date_to: Optional[datetime] = Query(None, description="Filter by due_at on or before"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    List tasks (action items) for the company with summary counts.

    Returns summary cards (total, pending, in_progress, completed, cancelled) and
    paginated task list with assignee and source call info.
    Access: EXECUTIVE, CSR, SALES_REP
    """
    try:
        service = PendingActionService(db)
        result = await service.list_tasks_with_summary(
            company_id=company_id,
            status=status_filter,
            priority=priority,
            assignee_id=assignee_id,
            search=search,
            start_date=start_date,
            end_date=end_date,
            due_date_from=due_date_from,
            due_date_to=due_date_to,
            skip=skip,
            limit=limit,
        )
        summary = result["summary"]
        total_tasks = summary.total_tasks
        completion_rate = round((summary.completed / total_tasks) * 100, 2) if total_tasks > 0 else 0.0
        return TaskListResponse(
            completion_rate=completion_rate,
            summary=summary,
            tasks=result["tasks"],
            total=result["total"],
            skip=result["skip"],
            limit=result["limit"],
        )
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/action-center", response_model=ActionCenterResponse, responses=RESPONSES)  # type: ignore
async def get_action_center(
    db: DbSession,
    company_id: UUID = Query(..., description="Company ID"),
    owner_id: Optional[UUID] = Query(None, description="Executive-only: view another rep's queue. Reps/CSRs always see their own."),
    limit: int = Query(50, ge=1, le=200, description="Max items returned across all groups"),
    include_in_progress: bool = Query(False, description="Include in_progress actions in addition to pending"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    Rep-scoped "what should I do next?" feed.

    Aggregates the rep's pending call_back / follow_up / appointment_reminder /
    rehash actions, ranks them by urgency tier + business value, and returns a
    `next` item, summary counts, and grouped sections.

    Owner resolution:
    - EXECUTIVE: uses `owner_id` query param if provided, else self.
    - SALES_REP / CSR: always the current user (any `owner_id` is ignored).

    Access: EXECUTIVE, CSR, SALES_REP
    """
    # Tenant isolation: user must belong to the requested company.
    if user.company_id is not None and user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company mismatch")

    # Resolve whose queue to return.
    if user.role == UserRole.EXECUTIVE:
        target_owner_id = owner_id or user.id
    else:
        target_owner_id = user.id  # reps/CSRs cannot view others' queues

    try:
        service = PendingActionService(db)
        res = await service.get_action_center(
            company_id=company_id,
            owner_id=target_owner_id,
            limit=limit,
            include_in_progress=include_in_progress,
        )
        
        # --- FIX BUG 4: ENFORCE SYSTEMATIC RECOVERY FOR PENDING TASKS ---
        if res is None:
            return {"next_item": None, "summary": {"pending_count": 0}, "grouped_sections": []}
        return res
        
    except Exception as e:
        logger.error(f"Error building action center: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/rehash/scan", response_model=RehashSyncResponse, responses=RESPONSES)  # type: ignore
async def trigger_rehash_scan(
    db: DbSession,
    company_id: UUID = Query(..., description="Company to scan (must be the caller's company)"),
    user: User = Depends(require_executive),
):
    """
    On-demand rehash scan for a company (executive only).

    Runs the same `scan_and_sync_rehash` the daily 5 AM job runs, so missed-revenue
    opportunities (qualified-unbooked, appointment-pending, stale leads) can be
    materialized and validated immediately without waiting for the cron. Idempotent:
    a second run creates 0 (existing rehash rows are left untouched). Materialized
    rows surface through the existing Action Center / task list. Thresholds are
    env-configurable (REHASH_* in settings) and need no code change to tune.

    Access: EXECUTIVE
    """
    # Tenant isolation: executive must belong to the requested company.
    if user.company_id is not None and user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company mismatch")

    try:
        from app.services.rehash_service import scan_and_sync_rehash

        result = await scan_and_sync_rehash(db, company_id=company_id)
        await db.commit()
        return RehashSyncResponse(
            scanned=result.scanned,
            created=result.created,
            cancelled=result.cancelled,
            skipped=result.skipped,
            by_category=result.by_category,
        )
    except Exception as e:
        logger.error(f"Error running rehash scan: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{task_id}", response_model=TaskDetailResponse, responses=RESPONSES)  # type: ignore
async def get_task(
    task_id: UUID,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    Get a single task by ID with full details (assignee, source call, assigned by).
    Access: EXECUTIVE, CSR, SALES_REP
    """
    try:
        service = PendingActionService(db)
        detail = await service.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return TaskDetailResponse(**detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{task_id}/follow-up-guidance", response_model=FollowUpGuidanceResponse, responses=RESPONSES)  # type: ignore
async def get_follow_up_guidance(
    task_id: UUID,
    db: DbSession,
    include_sms: bool = Query(False, description="Include the homeowner SMS draft (only for sms_to_lead follow-ups)"),
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    Read-only "what should I say next?" guidance for a single task.

    Assembles coaching copy (opening line, talking points, objection responses,
    next steps, SMS draft) and personalization context from existing analysis and
    GoMotto follow-up rows — no new LLM call.

    Access: EXECUTIVE, CSR, SALES_REP. Reps/CSRs may only access their own tasks.
    """
    try:
        service = PendingActionService(db)
        detail = await service.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        # Tenant isolation.
        if user.company_id is not None and detail["company_id"] != user.company_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company mismatch")
        # Reps/CSRs may only view their own tasks; executives may view any in-company.
        if user.role != UserRole.EXECUTIVE and detail["owner_id"] != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")

        guidance = await service.get_follow_up_guidance(task_id, include_sms=include_sms)
        if not guidance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return guidance
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building follow-up guidance: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("", response_model=PendingAction, status_code=status.HTTP_201_CREATED, responses=RESPONSES)  # type: ignore
async def create_task(
    body: CreateTaskRequest,
    db: DbSession,
    user: User = Depends(require_executive),
):
    """
    Create a task manually (not from a call). Executives can optionally assign to a CSR or Sales Rep.
    Access: EXECUTIVE only
    """
    try:
        service = PendingActionService(db)
        task = await service.create_task_manual(
            company_id=body.company_id,
            assigned_by_id=user.id,
            action_type=body.action_type,
            raw_text=body.raw_text,
            status=body.status,
            priority=body.priority,
            due_at=body.due_at,
            owner_id=body.owner_id,
            lead_id=body.lead_id,
            call_id=body.call_id,
            appointment_id=body.appointment_id,
        )
        return task
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch("/{task_id}", response_model=PendingAction, responses=RESPONSES)  # type: ignore
async def update_task(
    task_id: UUID,
    body: UpdateTaskRequest,
    db: DbSession,
    user: User = Depends(require_any_role([UserRole.EXECUTIVE, UserRole.CSR, UserRole.SALES_REP])),
):
    """
    Update a task: reassign (owner_id), change status, priority, due date, or description.
    When reassigning, pass owner_id; the backend can set assigned_by_id to current user.
    Access: EXECUTIVE, CSR, SALES_REP
    """
    try:
        service = PendingActionService(db)
        updated = await service.update_task(
            task_id,
            owner_id=body.owner_id,
            status=body.status,
            priority=body.priority,
            due_at=body.due_at,
            raw_text=body.raw_text,
            assigned_by_id=user.id if body.owner_id is not None else None,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
