"""
Task (pending action) API schemas for Task Management.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class SourceCallInfo(BaseModel):
    """Source call info for a task (from call logs)."""
    call_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    call_date: Optional[datetime] = None
    call_created_at: Optional[datetime] = None


class AssigneeInfo(BaseModel):
    """Assignee (owner) info for a task."""
    user_id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None


class TaskListItem(BaseModel):
    """Single task in list response."""
    id: UUID
    company_id: UUID
    action_type: str
    raw_text: Optional[str] = None
    status: str
    priority: Optional[int] = None
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    owner_id: Optional[UUID] = None
    assigned_to: Optional[AssigneeInfo] = None
    source_call: Optional[SourceCallInfo] = None
    call_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    assigned_by_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class TaskListSummary(BaseModel):
    """Summary counts for task management cards."""
    total_tasks: int = 0
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    cancelled: int = 0


class TaskListResponse(BaseModel):
    """Response for GET /tasks (list + summary)."""
    summary: TaskListSummary
    tasks: List[TaskListItem]
    total: int
    skip: int
    limit: int


class TaskDetailResponse(BaseModel):
    """Response for GET /tasks/{task_id} (single task full details)."""
    id: UUID
    company_id: UUID
    lead_id: Optional[UUID] = None
    call_id: Optional[UUID] = None
    appointment_id: Optional[UUID] = None
    action_type: str
    raw_text: Optional[str] = None
    status: str
    priority: Optional[int] = None
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    owner_id: Optional[UUID] = None
    assigned_to: Optional[AssigneeInfo] = None
    assigned_by_id: Optional[UUID] = None
    assigned_by: Optional[AssigneeInfo] = None
    source_call: Optional[SourceCallInfo] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class CreateTaskRequest(BaseModel):
    """Request to create a task manually (no call)."""
    company_id: UUID = Field(..., description="Company ID")
    action_type: str = Field(..., description="Type of action (e.g. follow_up_call, send_quote)")
    raw_text: Optional[str] = Field(None, description="Task title/description")
    status: Optional[str] = Field("pending", description="Status: pending, in_progress, completed, cancelled")
    priority: Optional[int] = Field(None, description="Priority (higher = more urgent)")
    due_at: Optional[datetime] = Field(None, description="Due date/time")
    owner_id: Optional[UUID] = Field(None, description="Assign to user (CSR or Sales Rep)")
    lead_id: Optional[UUID] = Field(None, description="Optional lead ID")
    call_id: Optional[UUID] = Field(None, description="Optional call ID (link to source call)")
    appointment_id: Optional[UUID] = Field(None, description="Optional appointment ID")


class UpdateTaskRequest(BaseModel):
    """Request to update a task (reassign, status, priority, due date, description)."""
    owner_id: Optional[UUID] = Field(None, description="Reassign to user (CSR or Sales Rep)")
    status: Optional[str] = Field(None, description="Status: pending, in_progress, completed, cancelled")
    priority: Optional[int] = Field(None, description="Priority (higher = more urgent)")
    due_at: Optional[datetime] = Field(None, description="Due date/time")
    raw_text: Optional[str] = Field(None, description="Task title/description")
