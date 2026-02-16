"""
Setup script for creating Milvus collection with correct schema.

This script should be run once to initialize the Milvus collection
with the proper schema for the embedding dimensions.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility
)
from app.config import get_settings

settings = get_settings()


def create_milvus_collection():
    """Create Milvus collection with proper schema"""
    
    print(f"Connecting to Milvus: {settings.MILVUS_URI}")
    connections.connect(
        alias="default",
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN,
    )
    
    collection_name = settings.MILVUS_COLLECTION
    
    # Check if collection exists
    if utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' already exists.")
        response = input("Do you want to drop and recreate it? (yes/no): ")
        if response.lower() == "yes":
            print(f"Dropping collection '{collection_name}'...")
            utility.drop_collection(collection_name)
        else:
            print("Exiting without changes.")
            return
    
    print(f"Creating collection '{collection_name}'...")
    
    # Define schema - must match all fields used in rag_service.py
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIMENSION),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="company_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=100),  # Added for rag_service
        FieldSchema(name="corpus_type", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="text_content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="summary_json", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="customer_phone", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="call_date", dtype=DataType.VARCHAR, max_length=50),  # Changed to VARCHAR for flexibility
        FieldSchema(name="created_at", dtype=DataType.INT64),  # Unix timestamp
        FieldSchema(name="sentiment", dtype=DataType.FLOAT),  # For sentiment scores
        FieldSchema(name="qualification_status", dtype=DataType.VARCHAR, max_length=50),  # For call summaries
        FieldSchema(name="booking_status", dtype=DataType.VARCHAR, max_length=50),  # For call summaries
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Otto Intelligence RAG Collection"
    )
    
    # Create collection
    collection = Collection(
        name=collection_name,
        schema=schema,
        using='default'
    )
    
    print(f"Collection '{collection_name}' created successfully!")
    
    # Create index for vector field
    print("Creating index on embedding field...")
    index_params = {
        "metric_type": "COSINE",
        "index_type": "AUTOINDEX",
        "params": {}
    }
    
    collection.create_index(
        field_name="embedding",
        index_params=index_params
    )
    
    print("Index created successfully!")
    
    # Load collection
    collection.load()
    print("Collection loaded and ready for use!")
    
    # Print summary
    print("\n" + "="*50)
    print(f"Collection Name: {collection_name}")
    print(f"Embedding Dimension: {settings.EMBEDDING_DIMENSION}")
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"Total Fields: {len(fields)}")
    print("="*50)


if __name__ == "__main__":
    try:
        create_milvus_collection()
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

