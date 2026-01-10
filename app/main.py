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
    - Start background workers
    - Cleanup on shutdown
    """
    # Startup
    setup_logging()
    
    # Start background scheduler for follow-up notifications
    logger.info("Starting background scheduler...")
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down background scheduler...")
    stop_scheduler()


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI app instance
    """
    # Enable docs based on ENABLE_DOCS setting (defaults to True)
    # Can be disabled by setting ENABLE_DOCS=False in environment
    app = FastAPI(
        title="Otto AI Backend",
        description="AI-powered Revenue Intelligence Platform",
        version="2.0.0",
        docs_url="/docs" if settings.ENABLE_DOCS else None,
        redoc_url="/redoc" if settings.ENABLE_DOCS else None,
        lifespan=lifespan,
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
    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers."""
        return {"status": "healthy", "version": "2.0.0"}
    
    return app


# Create app instance
app = create_app()

