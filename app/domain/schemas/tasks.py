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
    customer_phone: Optional[str] = None
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
    assigned_by: Optional[AssigneeInfo] = None
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
    completion_rate: float = Field(0.0, description="Percentage of completed tasks (0-100)")
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
    action_type: str = Field(..., description="Type of action (e.g. follow_up_call, send_quote, schedule_appointment)")
    raw_text: Optional[str] = Field(None, description="Task title/description")
    status: Optional[str] = Field("pending", description="Task status. Allowed: pending, in_progress, completed, cancelled")
    priority: Optional[int] = Field(None, description="Priority (higher = more urgent, e.g. 1=low, 5=critical)")
    due_at: Optional[datetime] = Field(None, description="Due date/time in ISO 8601 format")
    owner_id: Optional[UUID] = Field(None, description="Assign to user (CSR or Sales Rep UUID)")
    lead_id: Optional[UUID] = Field(None, description="Optional lead ID to link the task to")
    call_id: Optional[UUID] = Field(None, description="Optional call ID (link to source call)")
    appointment_id: Optional[UUID] = Field(None, description="Optional appointment ID to link the task to")

    model_config = {
        "json_schema_extra": {
            "example": {
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "action_type": "follow_up_call",
                "raw_text": "Follow up with customer about plumbing quote",
                "status": "pending",
                "priority": 3,
                "due_at": "2026-03-22T14:00:00Z",
                "owner_id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
                "lead_id": "b1c2d3e4-f5a6-7890-abcd-ef1234567890",
            }
        }
    }


class UpdateTaskRequest(BaseModel):
    """Request to update a task (reassign, status, priority, due date, description). All fields optional — only send fields you want to change."""
    owner_id: Optional[UUID] = Field(None, description="Reassign to user (CSR or Sales Rep UUID)")
    status: Optional[str] = Field(None, description="New status. Allowed: pending, in_progress, completed, cancelled")
    priority: Optional[int] = Field(None, description="Priority (higher = more urgent, e.g. 1=low, 5=critical)")
    due_at: Optional[datetime] = Field(None, description="Due date/time in ISO 8601 format")
    raw_text: Optional[str] = Field(None, description="Task title/description")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "in_progress",
                "priority": 4,
                "due_at": "2026-03-25T10:00:00Z",
            }
        }
    }
