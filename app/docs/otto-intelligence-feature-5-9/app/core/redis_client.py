"""
Redis client connection and management
"""

import redis.asyncio as aioredis
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get Redis client (singleton)"""
    global _redis_client
    
    if _redis_client is None:
        logger.info(f"Connecting to Redis: {settings.REDIS_URL}")
        _redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        # Test connection
        await _redis_client.ping()
        logger.info("Redis connection established")
    
    return _redis_client


async def close_redis_connection():
    """Close Redis connection"""
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")

