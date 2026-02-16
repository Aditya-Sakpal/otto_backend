"""
Base domain model.

All domain models inherit from this base class.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel as PydanticBaseModel, Field, ConfigDict


class BaseModel(PydanticBaseModel):
    """
    Base domain model with common fields.
    
    All domain models should inherit from this.
    """
    model_config = ConfigDict(
        from_attributes=True,  # Allow ORM models
        validate_assignment=True,
        use_enum_values=True,
    )
    
    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    
    def mark_updated(self) -> None:
        """Mark model as updated."""
        self.updated_at = datetime.utcnow()

