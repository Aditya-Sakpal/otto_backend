"""
Milvus Collection Manager - Handles multiple collections for different data types
"""

from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from typing import Optional, Dict
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_milvus_connected: bool = False


# Collection definitions
COLLECTIONS = {
    "call_summaries": "otto_call_summaries",      # Call summary vectors
    "chunk_summaries": "otto_chunk_summaries",    # Chunk summary vectors  
    "sop_documents": "otto_sop_documents",        # SOP document chunk vectors
    "sop_metrics": "otto_sop_metrics",            # SOP metric definition vectors
    "customer_data": "otto_customer_data",        # Customer profile vectors (future)
}


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


def get_collection_schema() -> CollectionSchema:
    """Define the schema for all collections (same schema for consistency)"""
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=200),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="corpus_type", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=200),
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=200),
        FieldSchema(name="text_content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="summary_json", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="created_at", dtype=DataType.INT64),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),
        FieldSchema(name="customer_phone", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="call_date", dtype=DataType.VARCHAR, max_length=50),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Otto Intelligence Vector Store"
    )
    
    return schema


def get_milvus_collection(collection_type: str = "default") -> Collection:
    """
    Get Milvus collection instance by type.
    
    Args:
        collection_type: Type of collection ('call_summaries', 'sop_documents', etc.)
                        or 'default' to use the main collection
    
    Returns:
        Collection instance
    """
    get_milvus_client()
    
    # For backward compatibility, use main collection if 'default' requested
    if collection_type == "default":
        collection_name = settings.MILVUS_COLLECTION
    else:
        collection_name = COLLECTIONS.get(collection_type, settings.MILVUS_COLLECTION)
    
    # Check if collection exists, if not create it
    if not utility.has_collection(collection_name):
        logger.warning(f"Collection '{collection_name}' does not exist, falling back to default")
        collection_name = settings.MILVUS_COLLECTION
        
        # If default also doesn't exist, raise error
        if not utility.has_collection(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
    
    return Collection(collection_name)


def create_collection(collection_type: str) -> Collection:
    """
    Create a new collection with proper schema and indexes.
    
    Args:
        collection_type: Type of collection to create
        
    Returns:
        Created collection instance
    """
    get_milvus_client()
    
    collection_name = COLLECTIONS.get(collection_type)
    if not collection_name:
        raise ValueError(f"Unknown collection type: {collection_type}")
    
    # Check if already exists
    if utility.has_collection(collection_name):
        logger.info(f"Collection '{collection_name}' already exists")
        return Collection(collection_name)
    
    # Create collection
    schema = get_collection_schema()
    collection = Collection(
        name=collection_name,
        schema=schema,
        using='default'
    )
    
    # Create index on embedding field for similarity search
    index_params = {
        "metric_type": "COSINE",
        "index_type": "AUTOINDEX",
        "params": {}
    }
    
    collection.create_index(
        field_name="embedding",
        index_params=index_params
    )
    
    # Create indexes on commonly filtered fields
    collection.create_index(field_name="tenant_id")
    collection.create_index(field_name="corpus_type")
    collection.create_index(field_name="doc_id")
    
    collection.load()
    
    logger.info(f"Created collection '{collection_name}' with indexes")
    
    return collection


def ensure_collections_exist():
    """
    Ensure all required collections exist. Create them if they don't.
    This should be called during application startup.
    """
    get_milvus_client()
    
    # For now, just ensure the default collection exists
    # In production, you might want to create separate collections
    if not utility.has_collection(settings.MILVUS_COLLECTION):
        logger.warning(f"Main collection '{settings.MILVUS_COLLECTION}' does not exist")
        logger.info("Using existing Milvus setup")


def get_collection_for_corpus_type(corpus_type: str) -> Collection:
    """
    Get the appropriate collection based on corpus type.
    
    Args:
        corpus_type: Corpus type (call_summary, chunk_summary, sop_document, etc.)
        
    Returns:
        Collection instance
    """
    # Map corpus types to collection types
    corpus_to_collection = {
        "call_summary": "call_summaries",
        "chunk_summary": "chunk_summaries",
        "sop_document": "sop_documents",
        "sop_metric": "sop_metrics",
        "sop_criteria": "sop_metrics",  # Same collection as metrics
        "faq": "default",
        "customer": "customer_data",
    }
    
    collection_type = corpus_to_collection.get(corpus_type, "default")
    return get_milvus_collection(collection_type)


def close_milvus_connection():
    """Close Milvus connection"""
    global _milvus_connected
    
    if _milvus_connected:
        connections.disconnect("default")
        _milvus_connected = False
        logger.info("Milvus connection closed")


# For backward compatibility
def get_milvus_client_legacy():
    """Legacy function name - initializes connection"""
    return get_milvus_client()

