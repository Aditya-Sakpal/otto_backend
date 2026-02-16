"""
Middleware for Otto Intelligence Service
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
import uuid

from app.config import settings
from app.core.exceptions import APIKeyInvalidError

logger = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to validate API key"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check, docs, and root
        if request.url.path in ["/", "/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Get API key from header
        api_key = request.headers.get("X-API-Key")
        
        # Check if API key is missing
        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Unauthorized",
                    "message": "API key is missing. Please provide a valid API key in the 'X-API-Key' header.",
                    "hint": "Get your API key from the .env file (API_KEY variable) or contact your administrator."
                },
                headers={"WWW-Authenticate": "ApiKey"},
            )
        
        # Check if API key is invalid
        if api_key != settings.API_KEY:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Unauthorized",
                    "message": "Invalid API key. Please provide a valid API key in the 'X-API-Key' header.",
                    "hint": "Verify your API key from the .env file (API_KEY variable) or contact your administrator."
                },
                headers={"WWW-Authenticate": "ApiKey"},
            )
        
        response = await call_next(request)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests"""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Add request ID to request state
        request.state.request_id = request_id
        
        logger.info(
            f"Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            }
        )
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        
        logger.info(
            f"Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": f"{process_time:.3f}s",
            }
        )
        
        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        
        return response


async def exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Handle HTTPException separately (these are expected errors)
    if isinstance(exc, HTTPException):
        logger.warning(
            f"HTTP exception",
            extra={
                "request_id": request_id,
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail if isinstance(exc.detail, str) else "Error",
                "message": exc.detail,
                "request_id": request_id,
            },
            headers=getattr(exc, "headers", None),
        )
    
    # Handle unexpected exceptions
    logger.error(
        f"Unhandled exception",
        extra={
            "request_id": request_id,
            "exception": str(exc),
            "type": type(exc).__name__,
        },
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support if this persists.",
            "request_id": request_id,
        },
    )

