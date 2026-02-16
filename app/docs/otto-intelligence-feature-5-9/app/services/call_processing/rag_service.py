"""
RAG Service

Service for RAG indexing and search using Milvus Zilliz Cloud.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pymilvus import Collection, connections, utility
from ...core.milvus_client import get_milvus_client
from ...models.enums import CorpusType
from .embedding_service import get_embedding_service


class RAGService:
    """Service for RAG operations"""
    
    def __init__(self):
        self.collection_name = "otto_intelligence_v1"
        self.embedding_service = get_embedding_service()
    
    async def index_call_summary(
        self,
        call_id: str,
        company_id: str,
        summary_text: str,
        summary_json: Dict[str, Any],
        customer_phone: Optional[str] = None,
        call_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Index call summary in Milvus.
        
        Args:
            call_id: Call identifier
            company_id: Company/tenant ID
            summary_text: Text to embed
            summary_json: Full summary JSON
            customer_phone: Customer phone number
            call_date: Call date
            metadata: Additional metadata
            
        Returns:
            Vector ID in Milvus
        """
        # Generate embedding
        embedding = await self.embedding_service.generate_embedding(summary_text)
        
        # Prepare data
        vector_id = f"vec_{call_id}_summary"
        
        # Handle call_date - it might be a datetime object or already a string
        if call_date:
            if isinstance(call_date, str):
                call_date_str = call_date
            else:
                call_date_str = call_date.isoformat()
        else:
            call_date_str = ""
        
        data = {
            "id": vector_id,
            "tenant_id": company_id,
            "company_id": company_id,  # Also include company_id field
            "corpus_type": CorpusType.CALL_SUMMARY.value,
            "doc_id": call_id,
            "chunk_id": "",
            "text_content": summary_text[:65000],  # Milvus VARCHAR limit
            "summary_json": json.dumps(summary_json),  # Convert dict to JSON string
            "created_at": int(datetime.utcnow().timestamp()),
            "embedding": embedding,
            "customer_phone": customer_phone or "",
            "call_date": call_date_str or "",
            "sentiment": metadata.get("sentiment", 0.0) if metadata else 0.0,
            "qualification_status": metadata.get("qualification_status", "") if metadata else "",
            "booking_status": metadata.get("booking_status", "") if metadata else ""
        }
        
        # Insert to Milvus
        try:
            client = get_milvus_client()
            collection = Collection(self.collection_name)
            collection.insert([data])
            collection.flush()
            
            return vector_id
            
        except Exception as e:
            raise Exception(f"Failed to index call summary: {str(e)}")
    
    async def index_chunk_summary(
        self,
        chunk_id: str,
        call_id: str,
        company_id: str,
        summary_text: str,
        summary_json: Dict[str, Any],
        chunk_index: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Index chunk summary in Milvus.
        
        Args:
            chunk_id: Chunk identifier
            call_id: Parent call ID
            company_id: Company/tenant ID
            summary_text: Text to embed
            summary_json: Chunk summary JSON
            chunk_index: Chunk sequence number
            metadata: Additional metadata
            
        Returns:
            Vector ID in Milvus
        """
        # Generate embedding
        embedding = await self.embedding_service.generate_embedding(summary_text)
        
        # Prepare data
        vector_id = f"vec_{chunk_id}"
        
        data = {
            "id": vector_id,
            "tenant_id": company_id,
            "company_id": company_id,  # Also include company_id field
            "corpus_type": CorpusType.CHUNK_SUMMARY.value,
            "doc_id": call_id,
            "chunk_id": chunk_id,
            "text_content": summary_text[:65000],
            "summary_json": json.dumps(summary_json),  # Convert dict to JSON string
            "created_at": int(datetime.utcnow().timestamp()),
            "embedding": embedding,
            "customer_phone": (metadata.get("customer_phone") or "") if metadata else "",
            "call_date": (metadata.get("call_date") or "") if metadata else "",
            "sentiment": metadata.get("sentiment", 0.0) if metadata else 0.0,
            "qualification_status": "",  # Empty for chunks, only used for call summaries
            "booking_status": ""  # Empty for chunks, only used for call summaries
        }
        
        # Insert to Milvus
        try:
            client = get_milvus_client()
            collection = Collection(self.collection_name)
            collection.insert([data])
            collection.flush()
            
            return vector_id
            
        except Exception as e:
            raise Exception(f"Failed to index chunk summary: {str(e)}")
    
    async def search(
        self,
        query: str,
        company_id: str,
        corpus_types: Optional[List[CorpusType]] = None,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents.
        
        Args:
            query: Search query text
            company_id: Company/tenant ID for filtering
            corpus_types: Types of documents to search
            limit: Maximum results
            filters: Additional filters
            
        Returns:
            List of search results with scores
        """
        if corpus_types is None:
            corpus_types = [CorpusType.CALL_SUMMARY, CorpusType.CHUNK_SUMMARY]
        
        # Generate query embedding
        query_embedding = await self.embedding_service.get_embedding_for_query(query)
        
        # Build filter expression
        filter_parts = [f'tenant_id == "{company_id}"']
        
        if corpus_types:
            corpus_values = [f'"{ct.value}"' for ct in corpus_types]
            filter_parts.append(f'corpus_type in [{", ".join(corpus_values)}]')
        
        if filters:
            if "date_range" in filters:
                date_range = filters["date_range"]
                if "start" in date_range:
                    filter_parts.append(f'call_date >= "{date_range["start"]}"')
                if "end" in date_range:
                    filter_parts.append(f'call_date <= "{date_range["end"]}"')
            
            if "qualification_status" in filters:
                statuses = filters["qualification_status"]
                if statuses:
                    status_values = [f'"{s}"' for s in statuses]
                    filter_parts.append(f'qualification_status in [{", ".join(status_values)}]')
        
        filter_expr = " && ".join(filter_parts)
        
        # Search
        try:
            client = get_milvus_client()
            collection = Collection(self.collection_name)
            collection.load()
            
            search_params = {
                "metric_type": "COSINE",  # Cosine similarity
                "params": {"nprobe": 10}
            }
            
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                expr=filter_expr,
                output_fields=[
                    "id", "doc_id", "chunk_id", "corpus_type",
                    "text_content", "summary_json", "customer_phone",
                    "call_date", "sentiment"
                ]
            )
            
            # Format results
            formatted_results = []
            for hit in results[0]:
                formatted_results.append({
                    "id": hit.entity.get("id"),
                    "score": float(hit.distance),
                    "corpus_type": hit.entity.get("corpus_type"),
                    "doc_id": hit.entity.get("doc_id"),
                    "chunk_id": hit.entity.get("chunk_id"),
                    "text_content": hit.entity.get("text_content"),
                    "summary_json": hit.entity.get("summary_json"),
                    "customer_phone": hit.entity.get("customer_phone"),
                    "call_date": hit.entity.get("call_date"),
                    "sentiment": hit.entity.get("sentiment")
                })
            
            return formatted_results
            
        except Exception as e:
            raise Exception(f"Failed to search Milvus: {str(e)}")
    
    async def delete_by_call_id(self, call_id: str, company_id: str) -> int:
        """Delete all vectors for a call"""
        try:
            client = get_milvus_client()
            collection = Collection(self.collection_name)
            
            expr = f'tenant_id == "{company_id}" && doc_id == "{call_id}"'
            collection.delete(expr)
            collection.flush()
            
            return 1  # Success
            
        except Exception as e:
            raise Exception(f"Failed to delete from Milvus: {str(e)}")


# Singleton instance
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get singleton RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

