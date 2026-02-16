"""
MongoDB database connection and management
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_mongodb_client: Optional[AsyncIOMotorClient] = None


async def get_mongodb_client() -> AsyncIOMotorClient:
    """Get MongoDB client (singleton)"""
    global _mongodb_client
    
    if _mongodb_client is None:
        logger.info(f"Connecting to MongoDB: {settings.MONGODB_URL}")
        _mongodb_client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=50,
            minPoolSize=10,
        )
        # Test connection
        await _mongodb_client.admin.command('ping')
        logger.info("MongoDB connection established")
    
    return _mongodb_client


async def get_database() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance"""
    client = await get_mongodb_client()
    return client[settings.MONGODB_DB_NAME]


async def close_mongodb_connection():
    """Close MongoDB connection"""
    global _mongodb_client
    
    if _mongodb_client is not None:
        _mongodb_client.close()
        _mongodb_client = None
        logger.info("MongoDB connection closed")


# Database collections helper
class Collections:
    """Database collection names"""
    CALLS = "calls"
    CALL_SUMMARIES = "call_summaries"
    CHUNK_SUMMARIES = "chunk_summaries"
    CUSTOMERS = "customers"
    WEEKLY_INSIGHTS = "weekly_insights"
    ASK_OTTO_CONVERSATIONS = "ask_otto_conversations"
    ASK_OTTO_MESSAGES = "ask_otto_messages"

