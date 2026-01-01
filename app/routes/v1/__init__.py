"""API v1 routes."""
from fastapi import APIRouter

from app.routes.v1 import auth, calls, webhooks, rag

router = APIRouter()

# Include route modules
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(calls.router, prefix="/calls", tags=["calls"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(rag.router, prefix="/rag", tags=["rag"])

