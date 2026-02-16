#!/usr/bin/env python3
"""
Script to reindex SOP documents that were processed but not indexed to Milvus.
This fixes the issue where SOP data exists in MongoDB but not in Milvus vector DB.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from pymilvus import Collection
from app.core.milvus_client import get_milvus_client
from app.services.call_processing.embedding_service import get_embedding_service
from app.models.enums import CorpusType
import json
from datetime import datetime


async def reindex_sop(sop_id: str, company_id: str):
    """Reindex an SOP document to Milvus"""
    
    print(f"Reindexing SOP: {sop_id} for company: {company_id}")
    
    # Connect to MongoDB
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Get SOP document
    sop_doc = await db.sop_documents.find_one({"sop_id": sop_id})
    if not sop_doc:
        print(f"ERROR: SOP {sop_id} not found")
        return False
    
    # Get SOP chunks
    chunks = await db.sop_chunks.find({"sop_id": sop_id}).to_list(length=1000)
    print(f"Found {len(chunks)} chunks to index")
    
    if len(chunks) == 0:
        print("ERROR: No chunks found")
        return False
    
    # Get SOP metrics
    sop_metrics = await db.sop_metrics.find_one({"sop_id": sop_id})
    
    # Initialize services
    milvus_client = get_milvus_client()
    embedding_service = get_embedding_service()
    collection_name = os.getenv("MILVUS_COLLECTION", "otto_intelligence_v1")
    
    vectors_indexed = 0
    
    # Index each chunk
    for chunk in chunks:
        try:
            chunk_text = chunk.get('text', '')
            chunk_id = chunk.get('chunk_id')
            chunk_type = chunk.get('chunk_type', 'general')
            
            print(f"  Indexing chunk {chunk_id}...")
            
            # Determine corpus type based on chunk type
            if chunk_type == "metric":
                corpus_type = CorpusType.SOP_METRIC
            elif chunk_type == "criteria":
                corpus_type = CorpusType.SOP_CRITERIA
            else:
                corpus_type = CorpusType.SOP_DOCUMENT
            
            # Generate embedding
            embedding = await embedding_service.generate_embedding(chunk_text)
            
            # Prepare vector data
            vector_data = {
                "id": f"sop_{sop_id}_{chunk_id}",
                "tenant_id": company_id,
                "corpus_type": corpus_type.value,
                "doc_id": sop_id,
                "chunk_id": chunk_id,
                "text_content": chunk_text[:2000],  # Limit text length
                "summary_json": None,
                "embedding": embedding,
                "created_at": int(chunk.get('created_at', '').timestamp() if hasattr(chunk.get('created_at', ''), 'timestamp') else 0),
                "customer_phone": None,
                "call_date": None
            }
            
            # Insert to Milvus
            milvus_client.insert(
                collection_name=collection_name,
                data=[vector_data]
            )
            
            vectors_indexed += 1
            print(f"    ✓ Indexed as {corpus_type.value}")
            
        except Exception as e:
            print(f"    ✗ Error indexing chunk {chunk_id}: {e}")
            continue
    
    # Also index metric definitions if available
    if sop_metrics and sop_metrics.get('metrics'):
        print(f"\nIndexing {len(sop_metrics['metrics'])} metric definitions...")
        
        for metric in sop_metrics['metrics']:
            try:
                metric_id = metric.get('metric_id')
                
                # Create searchable text from metric
                metric_text = f"""
                {metric.get('metric_name', '')}
                
                Description: {metric.get('description', '')}
                
                Evaluation Method: {metric.get('evaluation_method', '')}
                
                Evaluation Criteria:
                - Excellent: {metric.get('evaluation_criteria', {}).get('excellent', '')}
                - Good: {metric.get('evaluation_criteria', {}).get('good', '')}
                - Needs Improvement: {metric.get('evaluation_criteria', {}).get('needs_improvement', '')}
                - Poor: {metric.get('evaluation_criteria', {}).get('poor', '')}
                """
                
                # Generate embedding
                embedding = await embedding_service.generate_embedding(metric_text)
                
                # Prepare vector data
                vector_data = {
                    "id": f"sop_metric_{sop_id}_{metric_id}",
                    "tenant_id": company_id,
                    "corpus_type": CorpusType.SOP_METRIC.value,
                    "doc_id": sop_id,
                    "chunk_id": metric_id,
                    "text_content": metric_text[:2000],
                    "summary_json": json.dumps(metric),
                    "embedding": embedding,
                    "created_at": int(sop_metrics.get('created_at', '').timestamp() if hasattr(sop_metrics.get('created_at', ''), 'timestamp') else 0),
                    "customer_phone": None,
                    "call_date": None
                }
                
                # Insert to Milvus
                milvus_client.insert(
                    collection_name=collection_name,
                    data=[vector_data]
                )
                
                vectors_indexed += 1
                print(f"  ✓ Indexed metric: {metric.get('metric_name')}")
                
            except Exception as e:
                print(f"  ✗ Error indexing metric {metric_id}: {e}")
                continue
    
    # Update processing metadata in MongoDB
    await db.sop_documents.update_one(
        {"sop_id": sop_id},
        {"$set": {"processing_metadata.vectors_indexed": vectors_indexed}}
    )
    
    print(f"\n✓ Successfully indexed {vectors_indexed} vectors for SOP {sop_id}")
    
    # Close connections
    client.close()
    
    return True


async def main():
    """Main function"""
    print("=" * 70)
    print("SOP REINDEXING SCRIPT")
    print("=" * 70)
    print()
    
    # Reindex the active SOP for test_company_123
    success = await reindex_sop("sop_666e39b1102d", "test_company_123")
    
    if success:
        print("\n" + "=" * 70)
        print("REINDEXING COMPLETE ✓")
        print("=" * 70)
        print("\nYou can now query SOP data via Ask Otto!")
    else:
        print("\n" + "=" * 70)
        print("REINDEXING FAILED ✗")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

