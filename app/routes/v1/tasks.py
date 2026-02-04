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


@router.get("", response_model=TaskListResponse, responses=RESPONSES)
async def list_tasks(
    company_id: UUID = Query(..., description="Company ID"),
    status: Optional[str] = Query(None, description="Filter by status: pending, in_progress, completed, cancelled"),
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
    db: DbSession = None,
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
            status=status,
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
        return TaskListResponse(
            summary=result["summary"],
            tasks=result["tasks"],
            total=result["total"],
            skip=result["skip"],
            limit=result["limit"],
        )
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{task_id}", response_model=TaskDetailResponse, responses=RESPONSES)
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


@router.post("", response_model=PendingAction, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
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


@router.patch("/{task_id}", response_model=PendingAction, responses=RESPONSES)
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
