"""
RAG Search Service for Ask Otto

Multi-source RAG search combining call summaries, chunk summaries, and FAQs.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from ...services.call_processing.rag_service import get_rag_service
from ...models.enums import CorpusType
from ...models.conversation import RAGSearchResult


class RAGSearchService:
    """Service for RAG search in Ask Otto"""
    
    def __init__(self):
        self.rag_service = get_rag_service()
    
    async def search(
        self,
        query: str,
        company_id: str,
        corpus_types: Optional[List[CorpusType]] = None,
        max_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RAGSearchResult]:
        """
        Perform multi-source RAG search.
        
        Args:
            query: Search query text
            company_id: Company/tenant ID
            corpus_types: Types of documents to search
            max_results: Maximum number of results
            filters: Additional filters
            
        Returns:
            List of RAG search results
        """
        if corpus_types is None:
            corpus_types = [CorpusType.CALL_SUMMARY, CorpusType.CHUNK_SUMMARY]
        
        # Perform search using base RAG service
        results = await self.rag_service.search(
            query=query,
            company_id=company_id,
            corpus_types=corpus_types,
            limit=max_results,
            filters=filters or {}
        )
        
        # Convert to RAGSearchResult objects
        search_results = []
        for result in results:
            # Parse summary_json if it's a string
            summary_json = result.get("summary_json")
            if summary_json and isinstance(summary_json, str):
                try:
                    summary_json = json.loads(summary_json)
                except (json.JSONDecodeError, ValueError):
                    summary_json = None
            
            search_results.append(RAGSearchResult(
                id=result["id"],
                score=result["score"],
                corpus_type=CorpusType(result["corpus_type"]),
                doc_id=result["doc_id"],
                chunk_id=result.get("chunk_id"),
                text_content=result["text_content"],
                summary_json=summary_json,
                customer_phone=result.get("customer_phone"),
                call_date=result.get("call_date"),
                metadata={}
            ))
        
        return search_results
    
    async def search_with_context(
        self,
        query: str,
        company_id: str,
        conversation_history: List[Dict[str, str]],
        max_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RAGSearchResult]:
        """
        Search with conversation context.
        
        Enhances query using conversation history.
        """
        # For now, use the query as-is
        # TODO: Enhance with conversation context
        
        return await self.search(
            query=query,
            company_id=company_id,
            max_results=max_results,
            filters=filters
        )


# Singleton
_rag_search_service: Optional[RAGSearchService] = None


def get_rag_search_service() -> RAGSearchService:
    """Get singleton instance"""
    global _rag_search_service
    if _rag_search_service is None:
        _rag_search_service = RAGSearchService()
    return _rag_search_service

