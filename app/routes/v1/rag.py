"""
RAG/Ask Otto API routes.

Ask Otto (company scope) - EXECUTIVE only
"""
from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/ask-otto")
async def query_ask_otto(
    body: RAGQueryRequest,
    db: DbSession,
    user: User = Depends(require_manager),  # EXECUTIVE only for company scope
):
    """
    Query Ask Otto (RAG-based AI copilot) - Company scope.

    Access: EXECUTIVE only

    Args:
        body: Query request
        user: Current authenticated user (EXECUTIVE)

    Returns:
        RAG query result
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

        result = await shoonya.query_ask_otto(
            company_id=company_id,
            query=body.query,
            target_role=target_role,
            context=body.context,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying Ask Otto: {e}")
        # Return 503 for Shunya connectivity issues (RetryError, connection errors)
        if "RetryError" in str(type(e).__name__) or "RetryError" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shunya service temporarily unavailable",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
