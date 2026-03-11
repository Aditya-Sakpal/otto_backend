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
    users,
    invites,
    call_processing,
    ask_otto,
    insights,
    onboarding,
    appointments,
    recordings,
    contact_card,
    settings,
    tasks,
    sales_rep,
    posts,
    leaderboards,
    ghost_mode,
    coaching,
    tenant_config,
)

router = APIRouter()

# Include route modules
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(calls.router, prefix="/calls", tags=["calls"])
router.include_router(contact_card.router, prefix="/contact-card", tags=["contact-card"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(rag.router, prefix="/rag", tags=["rag"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(call_processing.router, tags=["call-processing"])
router.include_router(ask_otto.router, tags=["ask-otto"])
router.include_router(insights.router, tags=["insights"])
router.include_router(invites.router, prefix="/invites", tags=["invites"])
router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
router.include_router(appointments.router, prefix="/appointments", tags=["appointments"])
router.include_router(recordings.router, prefix="/recordings", tags=["recordings"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(tasks.router, tags=["tasks"])
router.include_router(sales_rep.router, prefix="/sales_rep", tags=["sales_rep"])
router.include_router(posts.router, prefix="/posts/sales_rep", tags=["posts"])
router.include_router(leaderboards.router, prefix="/leaderboards", tags=["leaderboards"])
router.include_router(ghost_mode.router, prefix="/ghost-mode", tags=["ghost-mode"])
router.include_router(coaching.router, prefix="/coaching", tags=["coaching"])
router.include_router(tenant_config.router, prefix="/tenant-config", tags=["tenant-config"])
