"""Schemas for contextual follow-up agent HTTP APIs."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FollowUpOttoApproveSendRequest(BaseModel):
    """Optional final text; omit to send the stored draft as-is."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {},
                {
                    "message_content": "Hi — confirming we can meet Tuesday at 2pm. Reply YES to hold the slot."
                },
            ]
        }
    )

    message_content: Optional[str] = Field(
        None,
        description="Edited message body to send; defaults to current draft in DB",
    )


class FollowUpOttoApproveSendResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "status": "sent",
                    "external_message_id": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    "pending_action_id": None,
                    "error_message": None,
                },
                {
                    "id": "4fa85f64-5717-4562-b3fc-2c963f66afa7",
                    "status": "sent",
                    "external_message_id": None,
                    "pending_action_id": "8d8f8f8f-8d8f-8d8f-8d8f-8d8f8f8f8d8f",
                    "error_message": None,
                },
            ]
        }
    )

    id: UUID
    status: str
    external_message_id: Optional[str] = None
    pending_action_id: Optional[UUID] = None
    error_message: Optional[str] = None
