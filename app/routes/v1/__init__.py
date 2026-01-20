"""API v1 routes."""
from fastapi import APIRouter

from app.routes.v1 import (
    auth,
    calls,
    webhooks,
    rag,
    metrics,
    leads,
    websocket,
    analytics,
    users,
    invites,
    call_processing,
    ask_otto,
    insights,
    onboarding,
    appointments,
    recordings,
)

router = APIRouter()

# Include route modules
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(calls.router, prefix="/calls", tags=["calls"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(rag.router, prefix="/rag", tags=["rag"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(call_processing.router, tags=["call-processing"])
router.include_router(ask_otto.router, tags=["ask-otto"])
router.include_router(insights.router, tags=["insights"])
router.include_router(invites.router, prefix="/invites", tags=["invites"])
router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
router.include_router(appointments.router, prefix="/appointments", tags=["appointments"])
router.include_router(recordings.router, prefix="/recordings", tags=["recordings"])
