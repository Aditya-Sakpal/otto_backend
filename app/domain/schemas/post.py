"""
Post API schemas.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    """Schema for creating a post."""

    appointment_id: UUID = Field(..., description="Appointment UUID")
    note: Optional[str] = Field(None, description="Post note/text")
    tags: Optional[str] = Field(None, description="Tag: agenda_setting or objection_handling")


class PostUpdate(BaseModel):
    """Schema for updating a post."""

    note: Optional[str] = Field(None, description="Post note/text")
    tags: Optional[str] = Field(None, description="Tag: agenda_setting or objection_handling")


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
