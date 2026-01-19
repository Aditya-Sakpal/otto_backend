"""
Ask Otto (Conversational AI) API routes.

Handles conversational querying over calls, customers, and insights.
"""
import traceback
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.core.logging import get_logger
from app.infrastructure.database.models.ask_otto_conversation import AskOttoConversationORM, AskOttoMessageORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/ask-otto", tags=["ask-otto"])
logger = get_logger(__name__)


# Request/Response Models
class CreateConversationRequest(BaseModel):
    """Request to create a conversation."""
    company_id: str = Field(..., description="Company UUID")
    context: Optional[dict] = Field(None, description="Optional conversation context")


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    message: str = Field(..., description="User message")


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Create a new Ask Otto conversation.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
        # Create conversation in Shunya
        result = await shoonya.create_ask_otto_conversation(
            company_id=request.company_id,
            context=request.context,
        )
        
        # Store in database
        conversation = AskOttoConversationORM(
            company_id=UUID(request.company_id),
            user_id=current_user.id if current_user else None,
            shunya_conversation_id=result.get("conversation_id") or result.get("id"),
            context=request.context,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        
        return {
            **result,
            "id": str(conversation.id),
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


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
    current_user: User = Depends(require_any_role([UserRole.CSR, UserRole.SALES_REP, UserRole.EXECUTIVE])),
):
    """
    Send a message in an Ask Otto conversation.
    
    Returns assistant response.
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service not available",
            )
        
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
        
        # Use Shunya conversation ID if available, otherwise use our UUID
        shunya_conv_id = conversation.shunya_conversation_id or str(conversation_id)
        
        # Send message to Shunya
        result = await shoonya.send_ask_otto_message(
            conversation_id=shunya_conv_id,
            message=request.message,
            company_id=str(conversation.company_id),
        )
        
        # Store user message
        user_message = AskOttoMessageORM(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            shunya_message_id=result.get("message_id"),
        )
        db.add(user_message)
        
        # Store assistant response
        assistant_message = AskOttoMessageORM(
            conversation_id=conversation_id,
            role="assistant",
            content=result.get("response", result.get("message", "")),
            shunya_message_id=result.get("response_id"),
            message_metadata=result,
        )
        db.add(assistant_message)
        
        await db.commit()
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(e)}",
        )


@router.get("/conversations/{conversation_id}/messages")
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
