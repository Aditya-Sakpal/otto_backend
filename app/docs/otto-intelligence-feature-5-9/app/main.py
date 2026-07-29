"""
Main FastAPI application for Otto Intelligence Service
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.openapi.utils import get_openapi
import logging
from contextlib import asynccontextmanager

from app.config import get_settings

settings = get_settings()
from app.core.middleware import (
    APIKeyMiddleware,
    RequestLoggingMiddleware,
    exception_handler,
)
from app.core.database import get_mongodb_client, close_mongodb_connection
from app.core.redis_client import get_redis_client, close_redis_connection
from app.core.milvus_client import get_milvus_client, close_milvus_connection
from app.core.scheduler import start_scheduler, stop_scheduler, get_scheduler_status
from app.services.call_processing.embedding_service import preload_embedding_model


# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Starting Otto Intelligence Service...")
    
    # Initialize connections
    await get_mongodb_client()
    await get_redis_client()
    get_milvus_client()
    
    # Start background scheduler for periodic tasks (weekly insights, etc.)
    await start_scheduler()

    # Preload embedding model (CUDA if available)
    logger.info("Preloading embedding model...")
    preload_embedding_model()

    
    logger.info("All connections established successfully")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"API running on {settings.API_HOST}:{settings.API_PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Otto Intelligence Service...")
    
    # Stop the scheduler first
    await stop_scheduler()
    
    await close_mongodb_connection()
    await close_redis_connection()
    close_milvus_connection()
    logger.info("All connections closed")


# Create FastAPI app
app = FastAPI(
    title="Otto Intelligence Service",
    description="AI-powered call intelligence, insights, and conversational AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Define API Key security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Custom OpenAPI schema with security
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Otto Intelligence Service",
        version="1.0.0",
        description="AI-powered call intelligence, insights, and conversational AI",
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API Key for authentication. Get it from your .env file (API_KEY variable)."
        }
    }
    
    # Apply security globally to all endpoints except health and docs
    for path in openapi_schema["paths"]:
        if path not in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            for method in openapi_schema["paths"][path]:
                if method != "parameters":
                    openapi_schema["paths"][path][method]["security"] = [
                        {"APIKeyHeader": []}
                    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(APIKeyMiddleware)

# Add exception handlers
app.add_exception_handler(Exception, exception_handler)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "otto-intelligence",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "service": "Otto Intelligence Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# Import and include routers
from app.api.v1 import call_processing, insights, ask_otto, sop, tenant_config, coaching
app.include_router(call_processing.router)
app.include_router(insights.router)
app.include_router(ask_otto.router)
app.include_router(sop.router)
app.include_router(tenant_config.router)
app.include_router(coaching.router)


# Placeholder routes for demonstration
@app.get("/api/v1/status", tags=["Status"])
async def api_status():
    """API status endpoint"""
    return {
        "api_version": "v1",
        "features": {
            "call_processing": "pending_implementation",
            "insights_engine": "pending_implementation",
            "ask_otto": "pending_implementation",
        },
        "database": {
            "mongodb": "connected",
            "redis": "connected",
            "milvus": "connected",
        }
    }


@app.get("/api/v1/scheduler/status", tags=["Status"])
async def scheduler_status():
    """Get the status of the background scheduler and its jobs."""
    return get_scheduler_status()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.is_development,
    )

