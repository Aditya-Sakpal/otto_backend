"""
LangGraph Service

Simple orchestration service for Ask Otto (simplified version without full LangGraph).
Includes SOP search integration.
"""

from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...config import get_settings
from ...core.llm import get_llm_client, get_active_model, get_max_tokens_param
from ...models.conversation import MessageSource, CustomerContext
from ...models.enums import CorpusType
from .rag_search_service import get_rag_search_service
from .customer_context_service import get_customer_context_service
from ...services.sop.document_service import DocumentService

settings = get_settings()


class LangGraphService:
    """
    Simplified orchestration service for Ask Otto using dynamic LLM.
    
    This is a streamlined implementation that performs:
    1. Query classification
    2. RAG search if needed (includes SOP content)
    3. Customer context lookup if needed
    4. SOP metrics lookup if needed
    5. Response synthesis
    """
    
    def __init__(self):
        self.rag_service = get_rag_search_service()
        self.customer_service = get_customer_context_service()
        self.model = get_active_model()
        self.client = get_llm_client()
    
    async def process_query(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        context_options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a user query and generate a response.
        
        Args:
            db: MongoDB database
            company_id: Company ID
            user_message: User's message
            conversation_history: Previous messages
            context_options: Options for context retrieval
            
        Returns:
            Dict with answer, sources, customer_context, follow_ups
        """
        # Step 1: Classify query and extract entities
        classification = await self._classify_query(user_message, conversation_history)
        
        # Step 2: Gather context
        context = {}
        
        # Check if query is about SOP/procedures/guidelines
        is_sop_query = self._is_sop_related_query(user_message, classification)
        
        # RAG search if requested (includes SOP content if relevant)
        if context_options.get("include_call_history", True) or is_sop_query:
            max_results = context_options.get("max_rag_results", 5)
            
            # If SOP query, search SOP corpus types
            corpus_types_list = None
            if is_sop_query:
                corpus_types_list = [
                    CorpusType.SOP_DOCUMENT,
                    CorpusType.SOP_METRIC,
                    CorpusType.SOP_CRITERIA
                ]
            
            rag_results = await self.rag_service.search(
                query=user_message,
                company_id=company_id,
                corpus_types=corpus_types_list,
                max_results=max_results,
                filters=context_options.get("search_filters")
            )
            context["rag_results"] = rag_results
        
        # SOP metrics lookup if query is about evaluation/performance
        if is_sop_query or "evaluat" in user_message.lower() or "metric" in user_message.lower():
            try:
                doc_service = DocumentService(db)
                
                # Extract role from query if mentioned
                entities = classification.get("entities", {})
                role = entities.get("role")
                
                sop_metrics = await doc_service.get_sop_metrics(company_id, role)
                
                if sop_metrics:
                    context["sop_metrics"] = sop_metrics
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to get SOP metrics: {e}")
        
        # Customer context if requested
        customer_context = None
        if context_options.get("include_customer_context", True):
            entities = classification.get("entities", {})
            if entities.get("customer_name") or entities.get("phone_number"):
                customer_result = await self.customer_service.get_customer_context(
                    db,
                    company_id,
                    name=entities.get("customer_name"),
                    phone=entities.get("phone_number"),
                    location=entities.get("location")
                )
                if customer_result:
                    context["customer"] = customer_result
                    customer_context = CustomerContext(
                        customer_id=customer_result.customer_id,
                        name=customer_result.name,
                        phone=customer_result.phone,
                        location=customer_result.location,
                        qualification_status=customer_result.qualification_status,
                        total_calls=customer_result.total_calls,
                        last_call_date=customer_result.last_call_date
                    )
        
        # Step 3: Synthesize response
        response = await self._synthesize_response(
            user_message,
            conversation_history,
            context
        )
        
        # Step 4: Extract sources
        sources = self._extract_sources(context.get("rag_results", []))
        
        # Step 5: Generate follow-up suggestions
        follow_ups = await self._generate_follow_ups(
            user_message,
            response["answer"],
            context
        )
        
        return {
            "answer": response["answer"],
            "sources": sources,
            "customer_context": customer_context,
            "follow_ups": follow_ups
        }
    
    def _is_sop_related_query(self, query: str, classification: Dict[str, Any]) -> bool:
        """Check if query is related to SOPs/procedures/guidelines"""
        query_lower = query.lower()
        
        sop_keywords = [
            "sop", "standard operating procedure", "procedure", "guideline",
            "protocol", "process", "should", "best practice", "how to",
            "metric", "evaluation", "criteria", "performance", "rating"
        ]
        
        return any(keyword in query_lower for keyword in sop_keywords)
    
    async def _classify_query(
        self,
        query: str,
        history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Classify query and extract entities"""
        prompt = f"""Analyze this user query and extract key information.

Query: {query}

Extract:
1. Customer name (if mentioned)
2. Phone number (if mentioned)
3. Location (if mentioned)
4. Topic (what they're asking about)

Return JSON with: {{"customer_name": "...", "phone_number": "...", "location": "...", "topic": "..."}}
Use null for missing fields."""
        
        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You extract entities from user queries. Return JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                **get_max_tokens_param(1024)
            )
            
            import json
            entities = json.loads(response.choices[0].message.content)
            return {"entities": entities}
            
        except Exception:
            return {"entities": {}}
    
    async def _synthesize_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        context: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generate response using LLM"""
        # Build context string
        context_parts = []
        
        if "customer" in context:
            customer = context["customer"]
            context_parts.append(f"Customer: {customer.name} ({customer.phone})")
            context_parts.append(f"Total calls: {customer.total_calls}")
            context_parts.append(f"Status: {customer.qualification_status}")
        
        if "rag_results" in context:
            context_parts.append("\nRelevant information:")
            for idx, result in enumerate(context["rag_results"][:3], 1):
                # Check corpus type
                if result.corpus_type in [CorpusType.SOP_DOCUMENT, CorpusType.SOP_METRIC, CorpusType.SOP_CRITERIA]:
                    context_parts.append(f"{idx}. [SOP] {result.text_content[:500]}...")
                else:
                    context_parts.append(f"{idx}. [Call] {result.text_content[:500]}...")
        
        if "sop_metrics" in context:
            sop = context["sop_metrics"]
            context_parts.append(f"\nActive SOP: {sop.get('sop_id', 'Unknown')}")
            metrics = sop.get("metrics", [])
            if metrics:
                context_parts.append(f"Performance metrics: {len(metrics)} defined")
                # Show first few metrics
                for metric in metrics[:3]:
                    context_parts.append(f"  - {metric.get('metric_name')}: {metric.get('description')}")
        
        context_str = "\n".join(context_parts) if context_parts else "No specific context available."
        
        # Build conversation history string
        history_str = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in conversation_history[-5:]  # Last 5 messages
        ])
        
        # Generate response
        prompt = f"""You are Otto, an AI sales assistant. Answer the user's question based on the provided context.

When answering questions about procedures or SOPs:
1. Reference specific SOP sections when available
2. Cite metric definitions when discussing performance
3. Explain evaluation criteria from the SOP
4. If SOP guidance exists, prioritize it over general knowledge

Conversation History:
{history_str}

Context:
{context_str}

User Question: {user_message}

Instructions:
1. Answer based ONLY on the provided context
2. Cite specific calls, SOPs, or information sources
3. If information is not in the context, say "I don't have that information"
4. Be helpful and concise

Answer:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are Otto, a helpful AI sales assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                **get_max_tokens_param(500)
            )
            
            return {"answer": response.choices[0].message.content}
            
        except Exception as e:
            return {"answer": f"I apologize, but I encountered an error: {str(e)}"}
    
    def _extract_sources(self, rag_results: List[Any]) -> List[MessageSource]:
        """Extract sources from RAG results"""
        sources = []
        
        for result in rag_results[:5]:
            sources.append(MessageSource(
                type=result.corpus_type,
                call_id=result.doc_id,
                chunk_id=result.chunk_id,
                confidence=result.score,
                excerpt=result.text_content[:200],
                url=f"/api/v1/call-processing/summary/{result.doc_id}"
            ))
        
        return sources
    
    async def _generate_follow_ups(
        self,
        user_message: str,
        answer: str,
        context: Dict[str, Any]
    ) -> List[str]:
        """Generate follow-up question suggestions"""
        # Simple predefined follow-ups
        follow_ups = []
        
        if "customer" in context:
            follow_ups.append("What other calls did this customer make?")
            follow_ups.append("What was their qualification status?")
        
        if "rag_results" in context and context["rag_results"]:
            follow_ups.append("Tell me more about this call")
            follow_ups.append("Were there any objections?")
        
        if not follow_ups:
            follow_ups = [
                "Show me recent calls",
                "What are the top objections this week?",
                "How are we performing?"
            ]
        
        return follow_ups[:3]


# Singleton
_langgraph_service: Optional[LangGraphService] = None


def get_langgraph_service() -> LangGraphService:
    """Get singleton instance"""
    global _langgraph_service
    if _langgraph_service is None:
        _langgraph_service = LangGraphService()
    return _langgraph_service

