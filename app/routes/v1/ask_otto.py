"""
Ask Otto (Conversational AI) API routes.

Handles conversational querying over calls, customers, and insights.
"""
import asyncio
import json
import traceback
from datetime import datetime
from typing import Any, AsyncGenerator, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.core.logging import get_logger
from app.infrastructure.database.models.ask_otto_conversation import AskOttoConversationORM, AskOttoMessageORM
from app.services.title_generation_service import generate_conversation_title
from app.infrastructure.database.session import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/ask-Gomotto", tags=["ask-Gomotto"])
logger = get_logger(__name__)


def _build_user_context(user: User) -> dict:
    """Build user identity context dict to send to Shunya for personalized responses."""
    ctx = {
        "user_id": str(user.id),
        "user_role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }
    name_parts = [user.first_name, user.last_name]
    full_name = " ".join(p for p in name_parts if p)
    if full_name:
        ctx["user_name"] = full_name
    if user.email:
        ctx["user_email"] = user.email
    if user.company_id:
        ctx["company_id"] = str(user.company_id)
    return ctx


async def _generate_title_in_background(conversation_id: UUID, user_message: str):
    """
    Background task: generate a title from the first user message and update the conversation.
    Uses its own DB session since the request session will be closed by the time this runs.
    """
    try:
        title = await generate_conversation_title(user_message)
        if not title:
            return
        async with AsyncSessionLocal() as session:
            conv_query = select(AskOttoConversationORM).where(
                AskOttoConversationORM.id == conversation_id
            )
            result = await session.execute(conv_query)
            conversation = result.scalar_one_or_none()
            if conversation and not conversation.title:
                conversation.title = title
                await session.commit()
                logger.info(f"Auto-generated title for conversation {conversation_id}: {title}")
    except Exception as e:
        logger.error(f"Background title generation failed for {conversation_id}: {e}")


# ──────────────────────────── Request Models ────────────────────────────

class CreateConversationRequest(BaseModel):
    """Request body to create a new Ask Otto conversation thread."""
    company_id: str = Field(
        ...,
        description="UUID of the company this conversation belongs to",
        json_schema_extra={"example": "6d40b509-82bc-4d21-9614-de91cc25dc1b"},
    )
    context: Optional[dict] = Field(
        None,
        description="Optional context/metadata to seed the conversation (e.g. page the user is on, selected lead, etc.)",
        json_schema_extra={"example": {"source": "dashboard", "lead_id": "abc-123"}},
    )


class SendMessageRequest(BaseModel):
    """Request body to send a user message in a conversation."""
    message: str = Field(
        ...,
        description="The user's message / question to Ask Otto",
        json_schema_extra={"example": "What are the top objections this week?"},
    )


# ──────────────────────────── Response Models ───────────────────────────

class CreateConversationResponse(BaseModel):
    """Response returned after creating a new conversation thread."""
    id: str = Field(..., description="Local database UUID of the conversation")
    conversation_id: str = Field(..., description="Shunya conversation ID (falls back to local UUID if Shunya is unavailable)")
    company_id: str = Field(..., description="UUID of the company")

    class Config:
        extra = "allow"
        json_schema_extra = {
            "example": {
                "id": "3cc9a055-30ce-44d2-b06e-d49e437293a7",
                "conversation_id": "288c269f-8fd2-4d9e-bd7e-8aaf27847610",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
            }
        }


class ConversationThread(BaseModel):
    """A single conversation thread summary (no messages)."""
    id: str = Field(..., description="Local database UUID of the conversation thread")
    conversation_id: Optional[str] = Field(None, description="Shunya conversation ID (may be null for local-only threads)")
    company_id: str = Field(..., description="UUID of the company this thread belongs to")
    title: Optional[str] = Field(None, description="Auto-generated or user-set title for the thread")
    context: Optional[dict] = Field(None, description="Context/metadata that was provided when the thread was created")
    created_at: str = Field(..., description="ISO 8601 timestamp of when the thread was created")
    updated_at: Optional[str] = Field(None, description="ISO 8601 timestamp of the last update (null if never updated)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "3cc9a055-30ce-44d2-b06e-d49e437293a7",
                "conversation_id": "288c269f-8fd2-4d9e-bd7e-8aaf27847610",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "title": "Weekly objections analysis",
                "context": {"source": "dashboard"},
                "created_at": "2026-01-31T09:16:34.937817+00:00",
                "updated_at": None,
            }
        }


class ListConversationsResponse(BaseModel):
    """Response containing all conversation threads for the authenticated user."""
    conversations: List[ConversationThread] = Field(..., description="List of conversation threads, ordered by most recent first")
    total: int = Field(..., description="Total number of conversation threads returned")

    class Config:
        json_schema_extra = {
            "example": {
                "conversations": [
                    {
                        "id": "3cc9a055-30ce-44d2-b06e-d49e437293a7",
                        "conversation_id": "288c269f-8fd2-4d9e-bd7e-8aaf27847610",
                        "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                        "title": "Weekly objections analysis",
                        "context": None,
                        "created_at": "2026-01-31T09:16:34.937817+00:00",
                        "updated_at": None,
                    }
                ],
                "total": 1,
            }
        }


class ChatMessage(BaseModel):
    """A single message within a conversation thread."""
    id: str = Field(..., description="UUID of this message")
    role: str = Field(..., description="Who sent this message: 'user' or 'assistant'")
    content: str = Field(..., description="The message text content (may contain markdown)")
    message_metadata: Optional[dict] = Field(None, description="Extra metadata from Shunya (conversation_id, message_id, citations, etc.)")
    created_at: str = Field(..., description="ISO 8601 timestamp of when this message was sent")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "7fa14583-4021-4860-a78e-47543108ac72",
                "role": "user",
                "content": "What are the top objections this week?",
                "message_metadata": None,
                "created_at": "2026-01-31T09:16:34.937817+00:00",
            }
        }


class ThreadChatsResponse(BaseModel):
    """Response containing all messages (chats) in a conversation thread."""
    thread_id: str = Field(..., description="UUID of the conversation thread")
    title: Optional[str] = Field(None, description="Title of the conversation thread (may be null)")
    company_id: str = Field(..., description="UUID of the company this thread belongs to")
    messages: List[ChatMessage] = Field(..., description="List of messages in chronological order (oldest first)")
    total: int = Field(..., description="Total number of messages in this thread")

    class Config:
        json_schema_extra = {
            "example": {
                "thread_id": "3cc9a055-30ce-44d2-b06e-d49e437293a7",
                "title": "Weekly objections analysis",
                "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
                "messages": [
                    {
                        "id": "7fa14583-4021-4860-a78e-47543108ac72",
                        "role": "user",
                        "content": "What are the top objections this week?",
                        "message_metadata": None,
                        "created_at": "2026-01-31T09:16:34.937817+00:00",
                    },
                    {
                        "id": "9c21a0e6-84f8-4d23-a27a-9351ab7daa6b",
                        "role": "assistant",
                        "content": "Based on the calls this week, the top objections were:\n1. **Scheduling confusion**...",
                        "message_metadata": {"conversation_id": "288c269f-...", "message_id": "msg_6095a2b5..."},
                        "created_at": "2026-01-31T09:16:38.123456+00:00",
                    },
                ],
                "total": 2,
            }
        }


# ──────────────────────────── Error Responses ───────────────────────────

RESPONSES = {
    401: {"description": "Unauthorized - Bearer token is missing or invalid"},
    403: {"description": "Forbidden - User does not have the required role (CSR / Sales Rep / Executive)"},
    404: {"description": "Conversation thread not found for the given ID"},
    500: {"description": "Internal server error"},
}


@router.get(
    "/conversations",
    response_model=ListConversationsResponse,
    summary="List all conversation threads for the logged-in user",
    description="""
Returns every Ask Otto conversation thread that belongs to the currently
authenticated user. The **user_id is automatically extracted from the
Bearer JWT token** — no need to pass it explicitly.

**Authentication:** Bearer token required (roles: CSR, Sales Rep, Executive).

**Ordering:** Threads are returned newest-first (`created_at DESC`).

**Frontend usage:** Call this endpoint on the Ask Otto sidebar / thread list page
to populate the user's conversation history.
""",
    responses={
        **RESPONSES,
        200: {
            "description": "List of conversation threads returned successfully",
            "model": ListConversationsResponse,
        },
    },
)
async def list_user_conversations(
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    try:
        query = (
            select(AskOttoConversationORM)
            .where(AskOttoConversationORM.user_id == current_user.id)
            .order_by(AskOttoConversationORM.created_at.desc())
        )
        result = await db.execute(query)
        conversations = result.scalars().all()

        return {
            "conversations": [
                {
                    "id": str(conv.id),
                    "conversation_id": conv.shunya_conversation_id,
                    "company_id": str(conv.company_id),
                    "title": conv.title,
                    "context": conv.context,
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                }
                for conv in conversations
            ],
            "total": len(conversations),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list conversations: {str(e)}",
        )


@router.get(
    "/thread/chats",
    response_model=ThreadChatsResponse,
    summary="Get all messages (chats) in a conversation thread",
    description="""
Returns every message in a single Ask Otto conversation thread, in
**chronological order** (oldest first), so the frontend can render the
chat history top-to-bottom.

**Query parameter:**
- `thread_id` (required, UUID) — the conversation thread ID obtained from
  the `GET /ask-otto/conversations` endpoint (use the `id` field).

**Authentication:** Bearer token required (roles: CSR, Sales Rep, Executive).

**Each message contains:**
| Field | Description |
|---|---|
| `id` | UUID of the message |
| `role` | `"user"` or `"assistant"` |
| `content` | Message text (may contain markdown) |
| `message_metadata` | Extra Shunya metadata (citations, sources) — nullable |
| `created_at` | ISO 8601 timestamp |
""",
    responses={
        **RESPONSES,
        200: {
            "description": "All messages in the thread returned successfully",
            "model": ThreadChatsResponse,
        },
    },
)
async def get_thread_chats(
    db: DbSession,
    thread_id: UUID = Query(..., description="UUID of the conversation thread to fetch messages for"),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    try:
        # Verify the conversation exists
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == thread_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation thread not found",
            )

        # Get all messages ordered by creation time
        messages_query = (
            select(AskOttoMessageORM)
            .where(AskOttoMessageORM.conversation_id == thread_id)
            .order_by(AskOttoMessageORM.created_at)
        )
        messages_result = await db.execute(messages_query)
        messages = messages_result.scalars().all()

        return {
            "thread_id": str(thread_id),
            "title": conversation.title,
            "company_id": str(conversation.company_id),
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "message_metadata": msg.message_metadata,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ],
            "total": len(messages),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thread chats: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get thread chats: {str(e)}",
        )


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateConversationResponse,
    responses=RESPONSES,
)
async def create_conversation(
    body: CreateConversationRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Create a new Ask Otto conversation.
    """
    try:
        # Check if user is the dummy user (RBAC disabled) - don't store user_id in that case
        is_dummy_user = current_user and current_user.email in ["open_access@system.local", "open_access@otto.ai"]
        user_id_for_db = None if is_dummy_user else (current_user.id if current_user else None)
        user_id_for_shunya = None if is_dummy_user else (str(current_user.id) if current_user else None)

        # Build user context for Shunya (so it knows who is asking)
        user_context = None if is_dummy_user else _build_user_context(current_user)

        shoonya = get_shoonya_client()
        shunya_conversation_id = None
        shunya_result = {}

        # Try to create conversation in Shunya if available
        if shoonya.is_available():
            try:
                shunya_result = await shoonya.create_ask_otto_conversation(
                    company_id=body.company_id,
                    user_id=user_id_for_shunya,
                    metadata=body.context,  # Use context as metadata
                    user_context=user_context,
                )
                shunya_conversation_id = shunya_result.get("conversation_id") or shunya_result.get("id")
            except Exception as e:
                # Log but don't fail - we can store locally without Shunya
                logger.warning(f"Shunya service unavailable, creating local conversation: {e}")
                shunya_result = {"message": "Shunya service unavailable - conversation created locally"}

        # Store in database (works even without Shunya)
        conversation = AskOttoConversationORM(
            company_id=UUID(body.company_id),
            user_id=user_id_for_db,
            shunya_conversation_id=shunya_conversation_id,
            context=body.context,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        return {
            **shunya_result,
            "id": str(conversation.id),
            "conversation_id": shunya_conversation_id or str(conversation.id),
            "company_id": body.company_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {str(e)}",
        )

@router.post(
    "/conversations/{conversation_id}/messages",
    responses={**RESPONSES, 200: {"description": "Streaming response (text/event-stream)"}},
)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Send a message in an Ask Otto conversation.

    Returns assistant response.
    """
    async def _stream_response_generator(text: str) -> AsyncGenerator[str, None]:
        """
        Generate streaming response chunks for typing effect.

        Streams text character by character with small delays for typing effect.
        Uses Server-Sent Events (SSE) format.
        """
        for char in text:
            yield f"data: {json.dumps({'chunk': char})}\n\n"
            await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'done': True})}\n\n"

    try:
        # Get conversation from database
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == conversation_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        shoonya = get_shoonya_client()
        response_text = ""
        result = {}

        # Build user identity for personalized responses
        is_dummy_user = current_user and current_user.email in ["open_access@system.local", "open_access@otto.ai"]
        user_id_for_shunya = None if is_dummy_user else (str(current_user.id) if current_user else None)
        user_context = None if is_dummy_user else _build_user_context(current_user)

        # Try to send message to Shunya if available
        if shoonya.is_available() and conversation.shunya_conversation_id:
            try:
                shunya_conv_id = conversation.shunya_conversation_id
                result = await shoonya.send_ask_otto_message(
                    conversation_id=shunya_conv_id,
                    message=body.message,
                    company_id=str(conversation.company_id),
                    user_id=user_id_for_shunya,
                    user_context=user_context,
                    context=conversation.context or {
                        "include_customer_context": True,
                        "include_call_history": True,
                    },
                )
                response_text = result.get("answer") or result.get("message") or ""
            except Exception as e:
                logger.warning(f"Shunya service unavailable, using local fallback: {e}")
                response_text = f"[Shunya service unavailable] Your question: '{body.message}' has been recorded. The AI assistant is currently offline."
                result = {"message": "Shunya service unavailable"}
        else:
            # Fallback response when Shunya is not available
            response_text = f"[Offline mode] Your question: '{body.message}' has been recorded. The AI assistant is currently unavailable."
            result = {"message": "AI assistant unavailable"}

        # Store user message
        user_message = AskOttoMessageORM(
            conversation_id=conversation_id,
            role="user",
            content=body.message,
            shunya_message_id=result.get("message_id"),
        )
        db.add(user_message)

        # Store assistant response
        assistant_message = AskOttoMessageORM(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            shunya_message_id=result.get("response_id"),
            message_metadata=result,
        )
        db.add(assistant_message)

        await db.commit()

        # Auto-generate title on the first message if conversation has no title yet
        if not conversation.title:
            asyncio.create_task(
                _generate_title_in_background(conversation.id, body.message)
            )

        # Return streaming response with SSE format, streaming only the assistant text
        return StreamingResponse(
            _stream_response_generator(response_text),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable buffering for nginx
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(e)}",
        )


@router.get("/conversations/{conversation_id}/messages", responses=RESPONSES)
async def get_messages(
    conversation_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get all messages in an Ask Otto conversation.
    """
    try:
        # Get conversation from database
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == conversation_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Try to get from Shunya first (for latest data)
        shoonya = get_shoonya_client()
        if shoonya.is_available() and conversation.shunya_conversation_id:
            try:
                result = await shoonya.get_ask_otto_messages(
                    conversation_id=conversation.shunya_conversation_id,
                    company_id=str(conversation.company_id),
                )
                return result
            except Exception as e:
                logger.warning(f"Failed to get messages from Shunya, using local: {e}")

        # Fallback to local database
        messages_query = select(AskOttoMessageORM).where(
            AskOttoMessageORM.conversation_id == conversation_id
        ).order_by(AskOttoMessageORM.created_at)
        messages_result = await db.execute(messages_query)
        messages = messages_result.scalars().all()

        return {
            "conversation_id": str(conversation_id),
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}",
        )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Get Ask Otto conversation details.
    """
    try:
        # Get from database
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == conversation_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Try to get from Shunya if available
        shoonya = get_shoonya_client()
        if shoonya.is_available() and conversation.shunya_conversation_id:
            try:
                result = await shoonya.get_ask_otto_conversation(
                    conversation_id=conversation.shunya_conversation_id,
                    company_id=str(conversation.company_id),
                )
                return result
            except Exception as e:
                logger.warning(f"Failed to get conversation from Shunya, using local: {e}")

        # Return local data
        return {
            "id": str(conversation.id),
            "conversation_id": conversation.shunya_conversation_id,
            "company_id": str(conversation.company_id),
            "user_id": str(conversation.user_id) if conversation.user_id else None,
            "context": conversation.context,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation: {str(e)}",
        )


class UpdateConversationRequest(BaseModel):
    """Request body to update a conversation (e.g. rename)."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="New title for the conversation thread",
        json_schema_extra={"example": "Weekly objections analysis"},
    )


@router.patch(
    "/conversations/{conversation_id}",
    summary="Rename a conversation thread",
    description="Update the title of an existing Ask Otto conversation thread.",
    responses=RESPONSES,
)
async def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """Update an Ask Otto conversation (currently supports renaming)."""
    try:
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == conversation_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        conversation.title = body.title
        await db.commit()
        await db.refresh(conversation)

        return {
            "id": str(conversation.id),
            "conversation_id": conversation.shunya_conversation_id,
            "company_id": str(conversation.company_id),
            "title": conversation.title,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update conversation: {str(e)}",
        )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Delete an Ask Otto conversation.
    """
    try:
        # Get conversation from database
        conv_query = select(AskOttoConversationORM).where(
            AskOttoConversationORM.id == conversation_id
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Delete from Shunya if available
        shoonya = get_shoonya_client()
        if shoonya.is_available() and conversation.shunya_conversation_id:
            try:
                await shoonya.delete_ask_otto_conversation(
                    conversation_id=conversation.shunya_conversation_id,
                    company_id=str(conversation.company_id),
                )
            except Exception as e:
                logger.warning(f"Failed to delete conversation from Shunya: {e}")

        # Delete from local database (cascade will delete messages)
        db.delete(conversation)  # delete() is synchronous in SQLAlchemy
        await db.commit()

        return {"message": "Conversation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {str(e)}",
        )
