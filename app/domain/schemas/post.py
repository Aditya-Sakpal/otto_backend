"""
Post API schemas.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.infrastructure.database.models.post import PostTag


class PostCreate(BaseModel):
    """Schema for creating a post."""

    model_config = {"extra": "forbid"}

    appointment_id: UUID = Field(..., description="Appointment UUID")
    note: Optional[str] = Field(None, max_length=10_000, description="Post note/text")
    tags: Optional[PostTag] = Field(None, description="Tag: agenda_setting or objection_handling")


class PostUpdate(BaseModel):
    """Schema for updating a post."""

    model_config = {"extra": "forbid"}

    note: Optional[str] = Field(None, max_length=10_000, description="Post note/text")
    tags: Optional[PostTag] = Field(None, description="Tag: agenda_setting or objection_handling")


class PostResponse(BaseModel):
    """Schema for post response."""

    id: UUID
    appointment_id: UUID
    poster_id: UUID
    note: Optional[str] = None
    tags: Optional[str] = None
    likes: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
