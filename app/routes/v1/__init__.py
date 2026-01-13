"""API v1 routes."""
from fastapi import APIRouter

from app.routes.v1 import auth, calls, webhooks, rag, metrics, leads, websocket, analytics

router = APIRouter()

# Include route modules
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(calls.router, prefix="/calls", tags=["calls"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(rag.router, prefix="/rag", tags=["rag"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
router.include_router(analytics.router)

