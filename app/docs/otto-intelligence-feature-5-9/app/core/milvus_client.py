"""
Milvus Zilliz Cloud client connection and management
"""

from pymilvus import connections, Collection, utility
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_milvus_connected: bool = False


def get_milvus_client() -> None:
    """Initialize Milvus Zilliz Cloud connection"""
    global _milvus_connected
    
    if not _milvus_connected:
        logger.info(f"Connecting to Milvus Zilliz Cloud: {settings.MILVUS_URI}")
        connections.connect(
            alias="default",
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN,
        )
        _milvus_connected = True
        logger.info("Milvus Zilliz Cloud connection established")


def get_milvus_collection() -> Collection:
    """Get Milvus collection instance"""
    get_milvus_client()
    
    # Check if collection exists
    if not utility.has_collection(settings.MILVUS_COLLECTION):
        raise ValueError(f"Collection '{settings.MILVUS_COLLECTION}' does not exist")
    
    return Collection(settings.MILVUS_COLLECTION)


def close_milvus_connection():
    """Close Milvus connection"""
    global _milvus_connected
    
    if _milvus_connected:
        connections.disconnect("default")
        _milvus_connected = False
        logger.info("Milvus connection closed")

