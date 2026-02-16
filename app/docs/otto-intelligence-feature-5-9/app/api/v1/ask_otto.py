"""
Ask Otto API Endpoints

REST API for conversational AI chat.
"""

from fastapi import APIRouter, HTTPException, Depends, Path
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...schemas.ask_otto import (
    CreateConversationRequest,
    CreateConversationResponse,
    SendMessageRequest,
    SendMessageResponse,
    GetConversationResponse,
    GetMessagesResponse,
    MessageHistoryItem,
    GetMessagesQueryParams
)
from ...models.conversation import MessageMetadata
from ...core.database import get_database
from ...services.ask_otto.conversation_service import get_conversation_service
from ...services.ask_otto.langgraph_service import get_langgraph_service
from ...utils.uuid_validator import validate_uuid
from datetime import datetime


router = APIRouter(prefix="/api/v1/ask-otto", tags=["Ask Otto"])


@router.post("/conversations", response_model=CreateConversationResponse, status_code=201)
async def create_conversation(
    request: CreateConversationRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new conversation session."""
    try:
        conversation_service = get_conversation_service()
        
        conversation = await conversation_service.create_conversation(
            db,
            company_id=request.company_id,
            user_id=request.user_id,
            metadata=request.metadata
        )
        
        return CreateConversationResponse(
            conversation_id=conversation.conversation_id,
            company_id=conversation.company_id,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            message_count=0,
            expires_at=conversation.expires_at
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create conversation: {str(e)}"
        )


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: str = Path(..., description="Conversation ID (UUID format)"),
    request: SendMessageRequest = ...,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Send a message and get AI response."""
    # Validate conversation_id is UUID
    try:
        validate_uuid(conversation_id, "conversation_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        conversation_service = get_conversation_service()
        langgraph_service = get_langgraph_service()
        
        # Get conversation
        conversation = await conversation_service.get_conversation(db, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get conversation history
        history = await conversation_service.get_conversation_history(
            db, conversation_id, limit=10
        )
        
        # Store user message
        user_message = await conversation_service.add_message(
            db,
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            metadata=MessageMetadata()
        )
        
        # Process query and generate response
        start_time = datetime.utcnow()
        
        result = await langgraph_service.process_query(
            db=db,
            company_id=conversation.company_id,
            user_message=request.message,
            conversation_history=history,
            context_options=request.context.dict()
        )
        
        response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Store assistant response
        metadata = MessageMetadata(
            tokens_used=None,  # TODO: Track tokens
            response_time_ms=response_time_ms,
            rag_results_count=len(result.get("sources", [])),
            customer_context_found=result.get("customer_context") is not None
        )
        
        assistant_message = await conversation_service.add_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=result["answer"],
            sources=[s.dict() for s in result.get("sources", [])],
            customer_context=result.get("customer_context").dict() if result.get("customer_context") else None,
            suggested_follow_ups=result.get("follow_ups", []),
            metadata=metadata
        )
        
        return SendMessageResponse(
            conversation_id=conversation_id,
            message_id=assistant_message.message_id,
            answer=result["answer"],
            sources=result.get("sources", []),
            customer_context=result.get("customer_context"),
            suggested_follow_ups=result.get("follow_ups", []),
            metadata=metadata,
            created_at=assistant_message.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/conversations/{conversation_id}/messages", response_model=GetMessagesResponse)
async def get_messages(
    conversation_id: str = Path(..., description="Conversation ID (UUID format)"),
    limit: int = 50,
    before: str = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get conversation message history."""
    # Validate conversation_id is UUID
    try:
        validate_uuid(conversation_id, "conversation_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        conversation_service = get_conversation_service()
        
        # Check if conversation exists
        conversation = await conversation_service.get_conversation(db, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get messages
        messages, has_more = await conversation_service.get_messages(
            db, conversation_id, limit, before
        )
        
        # Format response
        message_items = [
            MessageHistoryItem(
                message_id=msg.message_id,
                role=msg.role,
                content=msg.content,
                sources=msg.sources,
                created_at=msg.created_at
            )
            for msg in messages
        ]
        
        return GetMessagesResponse(
            conversation_id=conversation_id,
            messages=message_items,
            total_messages=conversation.message_count,
            has_more=has_more
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get messages: {str(e)}"
        )


@router.get("/conversations/{conversation_id}", response_model=GetConversationResponse)
async def get_conversation(
    conversation_id: str = Path(..., description="Conversation ID (UUID format)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get conversation details."""
    # Validate conversation_id is UUID
    try:
        validate_uuid(conversation_id, "conversation_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        conversation_service = get_conversation_service()
        
        conversation = await conversation_service.get_conversation(db, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return GetConversationResponse(
            conversation_id=conversation.conversation_id,
            company_id=conversation.company_id,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            expires_at=conversation.expires_at,
            metadata=conversation.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation: {str(e)}"
        )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str = Path(..., description="Conversation ID (UUID format)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Delete a conversation and all its messages."""
    # Validate conversation_id is UUID
    try:
        validate_uuid(conversation_id, "conversation_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        conversation_service = get_conversation_service()
        
        deleted = await conversation_service.delete_conversation(db, conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete conversation: {str(e)}"
        )

