"""
FastAPI application entry point.

This is a thin layer that wires together:
- API routes
- Middleware
- Dependencies
- Background task workers
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import json
from datetime import datetime
from app.core.datetime_utils import isoformat_utc




class UTCJSONResponse(JSONResponse):
    """Custom JSONResponse that serializes datetimes to ISO 8601 UTC (+00:00)."""

    def render(self, content: any) -> bytes:
        def _default(o):
            if isinstance(o, datetime):
                return isoformat_utc(o)
            # fall back to FastAPI's default behavior for other types
            raise TypeError

        return json.dumps(content, default=_default, ensure_ascii=False).encode("utf-8")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.scheduler import start_scheduler, stop_scheduler
from app.routes.v1 import router as api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown tasks:
    - Initialize database connections
    - Auto-create tables (development only)
    - Start background workers
    - Cleanup on shutdown
    """
    # Startup
    setup_logging()

    # Auto-create tables in development (optional)
    # For production, use Alembic migrations instead
    if settings.is_development and settings.AUTO_CREATE_TABLES:
        try:
            from app.infrastructure.database.init_db import create_tables
            await create_tables()
        except Exception as e:
            logger.warning(f"Could not auto-create tables: {e}")
            logger.info("Continuing without auto-creation. Use migrations or run init_db.py manually.")

    # Background scheduler disabled — run workers separately if needed
    # start_scheduler()

    yield

    # stop_scheduler()


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    # Enable docs based on ENABLE_DOCS setting (defaults to True)
    # Can be disabled by setting ENABLE_DOCS=False in environment

    openapi_tags = [
        {
            "name": "auth",
            "description": "Authentication endpoints — signup, login, token refresh, and current user info. Uses JWT Bearer tokens.",
        },
        {
            "name": "users",
            "description": "User management — CRUD operations for users, list sales reps, list companies, and assignees dropdown.",
        },
        {
            "name": "calls",
            "description": "Call management — list calls, call logs with advanced filtering, objection details, and action items.",
        },
        {
            "name": "call-processing",
            "description": "Async call processing — submit calls for AI analysis, check job status, get summaries and chunks.",
        },
        {
            "name": "leads",
            "description": "Lead management — list/filter/search leads, pipeline view, lead details, customer card, assign to reps, update status, and move pipeline stage.",
        },
        {
            "name": "appointments",
            "description": "Appointment management — CRUD, reschedule, update location, list past/upcoming, counts, and pre-meeting intelligence context.",
        },
        {
            "name": "metrics",
            "description": "Analytics & metrics — executive dashboard (company overview, CSR dashboard, missed calls, booking rate, close rate, objections, coaching opportunities, conversion metrics, company performance) and CSR dashboard.",
        },
        {
            "name": "coaching",
            "description": "Coaching dashboard — team overview, individual rep coaching, coaching sessions CRUD, smart nudges, coaching cycle management.",
        },
        {
            "name": "tasks",
            "description": "Task management — list/create/update/delete action items (pending actions) with filters for status, priority, assignee, date range, and search.",
        },
        {
            "name": "ask-otto",
            "description": "Ask Otto conversational AI — create/list/delete conversation threads, send messages (SSE streaming), get chat history.",
        },
        {
            "name": "settings",
            "description": "Company settings — integrations (CRM, telephony) and knowledge base documents management.",
        },
        {
            "name": "sales_rep",
            "description": "Sales rep endpoints — follow-ups, pending leads, sales rep stats, appointment details, ridealongs, sales team stats, and dashboard.",
        },
        {
            "name": "posts",
            "description": "Posts — CRUD for sales rep team posts, like/unlike.",
        },
        {
            "name": "leaderboards",
            "description": "Leaderboards — ranked CSR/rep performance with period filtering (daily, weekly, monthly, quarterly, yearly).",
        },
        {
            "name": "insights",
            "description": "Insights generation — trigger async insight generation jobs and check status.",
        },
        {
            "name": "onboarding",
            "description": "Onboarding — validate GoHighLevel, CallTrackingMetrics, and ServiceTitan integrations, then complete onboarding.",
        },
        {
            "name": "invites",
            "description": "Invitations — create, list, and accept team member invitations.",
        },
        {
            "name": "recordings",
            "description": "Recordings — initiate pre-signed S3 upload URLs for call recordings.",
        },
        {
            "name": "contact-card",
            "description": "Contact card — get contact card data for a call.",
        },
        {
            "name": "ghost-mode",
            "description": "Ghost mode — get/update ghost mode settings for sales reps (silent ride-along monitoring).",
        },
        {
            "name": "rag",
            "description": "RAG (Retrieval-Augmented Generation) — query the Ask Otto knowledge base.",
        },
        {
            "name": "webhooks",
            "description": "Webhooks — inbound endpoints for telephony call completion, Shunya job completion, and CRM lead updates.",
        },
        {
            "name": "websocket",
            "description": "WebSocket — real-time notifications channel.",
        },
        {
            "name": "tenant-config",
            "description": "Tenant configuration — create, read, and update per-company configuration.",
        },
        {
            "name": "Pipeline",
            "description": "Pipeline operations — move leads through pipeline stages with validation and side-effects.",
        },
    ]

    app = FastAPI(
        title="Otto AI Backend",
        description=(
            "# Otto AI — Revenue Intelligence Platform API\n\n"
            "AI-powered platform for call analysis, lead management, coaching, and sales pipeline tracking.\n\n"
            "## Authentication\n"
            "All endpoints (except `/auth/signup`, `/auth/login`, `/auth/refresh`, webhooks, and onboarding) require a **Bearer JWT token** "
            "in the `Authorization` header.\n\n"
            "```\nAuthorization: Bearer <access_token>\n```\n\n"
            "## Roles\n"
            "| Role | Value | Description |\n"
            "|------|-------|-------------|\n"
            "| CSR | `csr` | Customer Service Representative |\n"
            "| Sales Rep | `sales_rep` | Sales Representative |\n"
            "| Executive | `executive` | Executive / Admin |\n\n"
            "## Common Patterns\n"
            "- **Pagination**: Most list endpoints accept `skip` (offset, default 0) and `limit` (page size, default 100, max 1000).\n"
            "- **Date filtering**: Use `start_date` and `end_date` in `YYYY-MM-DD` format. Defaults to last 30 days.\n"
            "- **company_id vs user_id**: Many endpoints accept either. If `user_id` is provided, it takes precedence and `company_id` is derived from the user.\n\n"
            "## Enums Reference\n"
            "All enum values are documented in their respective schema definitions below. Key enums:\n"
            "- **UserRole**: `csr`, `sales_rep`, `executive`\n"
            "- **LeadStatus**: `new`, `warm`, `hot`, `qualified_booked`, `qualified_unbooked`, `qualified_service_not_offered`, `nurturing`, `dormant`, `abandoned`, `closed_won`, `closed_lost`\n"
            "- **DealStatus**: `new`, `nurturing`, `booked`, `no_show`, `rescheduled`, `in_progress`, `won`, `lost`\n"
            "- **PipelineStage**: `qualified`, `unqualified`, `service_not_offered`, `booked`, `appointment`, `appointment_ran`, `won`, `lost`, `review`\n"
            "- **AppointmentOutcome**: `pending`, `won`, `lost`, `no_show`, `rescheduled`\n"
            "- **CallType**: `csr_call`, `sales_call`, `missed_call`\n"
            "- **CallScope**: `in`, `out`\n"
            "- **TaskStatus**: `open`, `in_progress`, `completed`, `cancelled`\n"
            "- **PendingActionStatus**: `pending`, `in_progress`, `completed`, `cancelled`, `converted`\n"
            "- **CSRObjectionType**: `immediate_service_unavailability`, `phone_connection_issues`, `customer_needs_time_to_decide`, "
            "`scheduling_conflicts`, `service_fee_concerns`, `in_person_estimates_only`, `inefficient_agent_communication`, "
            "`customer_data_privacy_concerns`, `insurance_related`, `trust_credibility_concerns`, `not_the_decision_maker`, "
            "`workmanship_quality_complaints`, `other`, `service_not_catered`, `competitor_related_concerns`\n"
            "- **SOPStage**: `greeting`, `qualification`, `presentation`, `objection_handling`, `close`, `follow_up`\n"
            "- **LeaderboardPeriod**: `daily`, `weekly`, `monthly`, `quarterly`, `yearly`\n"
            "- **AnalysisStatus / CallStatus**: `pending`, `processing`, `completed`, `failed`\n"
            "- **InvitationStatus**: `pending`, `accepted`, `expired`\n"
        ),
        version="2.0.0",
        docs_url="/docs" if settings.ENABLE_DOCS else None,
        redoc_url="/redoc" if settings.ENABLE_DOCS else None,
        default_response_class=UTCJSONResponse,
        lifespan=lifespan,
        openapi_tags=openapi_tags,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Trusted host middleware (production)
    if settings.ENVIRONMENT == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts_list,
        )

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    # Health check endpoint
    @app.get("/")
    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers."""
        return {"status": "healthy", "version": "2.0.0"}

    return app


# Create app instance
app = create_app()

__reload_marker__ = "reload-for-call-logs-fix"
