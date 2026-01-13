"""
RAG/Ask Otto API routes.

Ask Otto (company scope) - EXECUTIVE only
"""
import json
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbSession, CurrentUser
from app.core.permissions import require_manager
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class RAGQueryRequest(BaseModel):
    """RAG query request."""
    query: str
    context: dict = {}


def _extract_text_from_result(result: dict | str) -> str:
    """
    Extract text content from RAG result.

    Tries common fields: answer, response, text, message, content
    Falls back to JSON string if no text field found.
    """
    text_fields = ["answer", "response", "text", "message", "content"]

    for field in text_fields:
        if field in result and isinstance(result[field], str):
            return result[field]

    # If no text field found, convert the result to a string
    # This handles cases where the result is just a string or has a different structure
    if isinstance(result, str):
        return result

    # Return JSON representation as fallback
    return json.dumps(result, ensure_ascii=False)


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


@router.post("/ask-otto")
async def query_ask_otto(
    request: RAGQueryRequest,
    db: DbSession,
    user: User = Depends(require_manager),  # EXECUTIVE only for company scope
):
    """
    Query Ask Otto (RAG-based AI copilot) - Company scope.

    Access: EXECUTIVE only

    Returns streaming response with typing effect (Server-Sent Events format).

    Args:
        request: Query request
        user: Current authenticated user (EXECUTIVE)

    Returns:
        StreamingResponse with RAG query result streamed character by character
    """
    shoonya = get_shoonya_client()

    if not shoonya.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service not available",
        )

    try:
        # Map user role to Shoonya target role
        target_role = "sales_manager"  # Executive role (mapped to sales_manager for Shoonya)

        # Get company_id from user
        company_id = str(user.company_id) if user.company_id else None
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be associated with a company",
            )

        # Get the full result from Shoonya
        result = await shoonya.query_ask_otto(
            company_id=company_id,
            query=request.query,
            target_role=target_role,
            context=request.context,
        )

        # Extract text content from result
        text = _extract_text_from_result(result)

        # Return streaming response with SSE format
        return StreamingResponse(
            _stream_response_generator(text),
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
        logger.error(f"Error querying Ask Otto: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

