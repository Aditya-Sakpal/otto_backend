#!/usr/bin/env python3
"""
Script to reindex SOP documents to Milvus.
Uses the same approach as call processing for consistency.
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
from app.config import settings
import json
from datetime import datetime


async def reindex_sop_to_milvus(sop_id: str, company_id: str):
    """
    Reindex SOP document and metrics to Milvus vector database.
    
    This uses the same collection and schema as call processing,
    differentiated by corpus_type field.
    """
    
    print(f"\n{'='*70}")
    print(f"REINDEXING SOP TO MILVUS")
    print(f"{'='*70}")
    print(f"SOP ID: {sop_id}")
    print(f"Company: {company_id}")
    print()
    
    # Connect to MongoDB
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Get SOP document
    sop_doc = await db.sop_documents.find_one({"sop_id": sop_id})
    if not sop_doc:
        print(f"❌ ERROR: SOP {sop_id} not found in MongoDB")
        return False
    
    print(f"✓ Found SOP: {sop_doc.get('sop_name')}")
    
    # Get SOP chunks
    chunks = await db.sop_chunks.find({"sop_id": sop_id}).to_list(length=1000)
    print(f"✓ Found {len(chunks)} chunks")
    
    if len(chunks) == 0:
        print("❌ ERROR: No chunks found")
        return False
    
    # Get SOP metrics
    sop_metrics = await db.sop_metrics.find_one({"sop_id": sop_id})
    if sop_metrics:
        print(f"✓ Found {sop_metrics.get('total_metrics', 0)} metrics")
    
    # Initialize services
    get_milvus_client()  # Connect to Milvus
    collection = Collection(settings.MILVUS_COLLECTION)
    embedding_service = get_embedding_service()
    
    vectors_indexed = 0
    vectors_to_insert = []
    
    print(f"\nIndexing SOP chunks...")
    
    # Index each chunk
    for i, chunk in enumerate(chunks, 1):
        try:
            chunk_text = chunk.get('text', '')
            chunk_id = chunk.get('chunk_id')
            chunk_type = chunk.get('chunk_type', 'general')
            section_title = chunk.get('section_title', '')
            
            if not chunk_text:
                print(f"  ⚠ Skipping empty chunk {chunk_id}")
                continue
            
            # Determine corpus type
            if chunk_type == "metric":
                corpus_type = CorpusType.SOP_METRIC
            elif chunk_type == "criteria":
                corpus_type = CorpusType.SOP_CRITERIA  
            else:
                corpus_type = CorpusType.SOP_DOCUMENT
            
            # Generate embedding
            embedding = await embedding_service.generate_embedding(chunk_text)
            
            # Prepare vector data (same schema as call processing)
            vector_data = {
                "id": f"sop_{sop_id}_{chunk_id}",
                "tenant_id": company_id,
                "company_id": company_id,  # Required by schema
                "corpus_type": corpus_type.value,
                "doc_id": sop_id,
                "chunk_id": chunk_id,
                "text_content": chunk_text[:65000],  # Milvus VARCHAR limit
                "summary_json": json.dumps({"section": section_title, "chunk_type": chunk_type}),
                "embedding": embedding,
                "created_at": int(datetime.utcnow().timestamp()),
                "customer_phone": "",
                "call_date": "",
                "sentiment": 0.0,  # Not applicable for SOPs
                "qualification_status": "",  # Not applicable for SOPs
                "booking_status": "",  # Not applicable for SOPs
            }
            
            vectors_to_insert.append(vector_data)
            print(f"  [{i}/{len(chunks)}] Prepared: {section_title[:50]}... ({corpus_type.value})")
            
        except Exception as e:
            print(f"  ❌ Error preparing chunk {chunk_id}: {e}")
            continue
    
    # Batch insert chunks
    if vectors_to_insert:
        try:
            print(f"\nInserting {len(vectors_to_insert)} chunk vectors to Milvus...")
            collection.insert(vectors_to_insert)
            collection.flush()
            vectors_indexed += len(vectors_to_insert)
            print(f"✓ Inserted {len(vectors_to_insert)} chunk vectors")
        except Exception as e:
            print(f"❌ Error inserting chunks: {e}")
            return False
    
    # Index metric definitions
    if sop_metrics and sop_metrics.get('metrics'):
        metrics = sop_metrics['metrics']
        print(f"\nIndexing {len(metrics)} metric definitions...")
        
        metric_vectors = []
        
        for i, metric in enumerate(metrics, 1):
            try:
                metric_id = metric.get('metric_id')
                metric_name = metric.get('metric_name', '')
                
                # Create rich searchable text from metric
                eval_criteria = metric.get('evaluation_criteria', {})
                metric_text = f"""{metric_name}

Description: {metric.get('description', '')}

Evaluation Method: {metric.get('evaluation_method', '')}

Target: {metric.get('target_value', 1.0)}
Weight: {metric.get('weight', 0.0) * 100}%

Evaluation Criteria:
- Excellent: {eval_criteria.get('excellent', '')}
- Good: {eval_criteria.get('good', '')}
- Needs Improvement: {eval_criteria.get('needs_improvement', '')}
- Poor: {eval_criteria.get('poor', '')}

Applicable Roles: {', '.join(metric.get('applicable_roles', []))}
"""
                
                # Generate embedding
                embedding = await embedding_service.generate_embedding(metric_text)
                
                # Prepare vector data
                vector_data = {
                    "id": f"sop_metric_{sop_id}_{metric_id}",
                    "tenant_id": company_id,
                    "company_id": company_id,  # Required by schema
                    "corpus_type": CorpusType.SOP_METRIC.value,
                    "doc_id": sop_id,
                    "chunk_id": metric_id,
                    "text_content": metric_text[:65000],
                    "summary_json": json.dumps(metric),
                    "embedding": embedding,
                    "created_at": int(datetime.utcnow().timestamp()),
                    "customer_phone": "",
                    "call_date": "",
                    "sentiment": 0.0,  # Not applicable for metrics
                    "qualification_status": "",  # Not applicable for metrics
                    "booking_status": "",  # Not applicable for metrics
                }
                
                metric_vectors.append(vector_data)
                print(f"  [{i}/{len(metrics)}] Prepared: {metric_name}")
                
            except Exception as e:
                print(f"  ❌ Error preparing metric {metric_id}: {e}")
                continue
        
        # Batch insert metrics
        if metric_vectors:
            try:
                print(f"\nInserting {len(metric_vectors)} metric vectors to Milvus...")
                collection.insert(metric_vectors)
                collection.flush()
                vectors_indexed += len(metric_vectors)
                print(f"✓ Inserted {len(metric_vectors)} metric vectors")
            except Exception as e:
                print(f"❌ Error inserting metrics: {e}")
    
    # Update processing metadata in MongoDB
    await db.sop_documents.update_one(
        {"sop_id": sop_id},
        {"$set": {
            "processing_metadata.vectors_indexed": vectors_indexed,
            "processing_metadata.reindexed_at": datetime.utcnow()
        }}
    )
    
    print(f"\n{'='*70}")
    print(f"✓ REINDEXING COMPLETE")
    print(f"{'='*70}")
    print(f"Total vectors indexed: {vectors_indexed}")
    print(f"  - SOP chunks: {len(vectors_to_insert)}")
    print(f"  - SOP metrics: {len(metric_vectors) if 'metric_vectors' in locals() else 0}")
    
    # Close connections
    client.close()
    
    return True


async def main():
    """Main function"""
    print("=" * 70)
    print("SOP MILVUS REINDEXING UTILITY")
    print("=" * 70)
    print()
    print("This script reindexes SOP documents from MongoDB to Milvus.")
    print("It uses the same collection schema as call processing.")
    print()
    
    # Reindex the active SOP for test_company_123
    success = await reindex_sop_to_milvus("sop_666e39b1102d", "test_company_123")
    
    if success:
        print("\n" + "=" * 70)
        print("SUCCESS! ✓")
        print("=" * 70)
        print("\nSOP data is now searchable via Ask Otto!")
        print("Try asking: 'How should sales reps handle objections according to our SOP?'")
    else:
        print("\n" + "=" * 70)
        print("FAILED! ✗")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

