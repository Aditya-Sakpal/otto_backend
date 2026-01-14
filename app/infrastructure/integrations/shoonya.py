"""
Shoonya/UWC client.

Abstraction for Shoonya AI/ML services.
"""
from typing import Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ShoonyaClient:
    """
    Client for Shoonya/UWC API.
    
    Handles all interactions with Shoonya services:
    - Transcription
    - Analysis
    - RAG queries
    """
    
    def __init__(self):
        self.base_url = settings.UWC_BASE_URL
        # Use API_KEY (new) or fall back to UWC_API_KEY (legacy)
        self.api_key = settings.API_KEY or settings.UWC_API_KEY
        self.hmac_secret = settings.UWC_HMAC_SECRET
        self.jwt_secret = settings.UWC_JWT_SECRET
        
        if not self.base_url or not self.api_key:
            logger.warning("Shoonya not configured - features will be disabled")
            self._enabled = False
        else:
            self._enabled = True
    
    def _get_headers(self, company_id: Optional[str] = None) -> Dict[str, str]:
        """Get standard headers for Shunya API requests."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if company_id:
            headers["X-Company-Id"] = company_id
        return headers
    
    def is_available(self) -> bool:
        """Check if Shoonya is available."""
        return self._enabled
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def transcribe_audio(
        self,
        company_id: str,
        audio_url: str,
        call_id: Optional[int] = None,
        call_type: str = "csr_call",
    ) -> Dict[str, Any]:
        """
        Transcribe audio file.
        
        Args:
            company_id: Company/tenant ID
            audio_url: Public URL to audio file
            call_id: Optional call ID
            call_type: Type of call (csr_call, sales_call)
            
        Returns:
            Transcription result with task_id/job_id
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/transcription/transcribe",
                json={
                    "company_id": company_id,
                    "audio_url": audio_url,
                    "call_id": call_id,
                    "call_type": call_type,
                },
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_complete_analysis(
        self,
        company_id: str,
        call_id: int,
    ) -> Dict[str, Any]:
        """
        Get complete call analysis.
        
        Args:
            company_id: Company/tenant ID
            call_id: Call ID
            
        Returns:
            Complete analysis result
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/analysis/{call_id}/complete",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def query_ask_otto(
        self,
        company_id: str,
        query: str,
        target_role: str = "customer_rep",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query Ask Otto (RAG).
        
        Args:
            company_id: Company/tenant ID
            query: User query
            target_role: Target role for context
            context: Additional context
            
        Returns:
            RAG query result
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/rag/ask-otto",
                json={
                    "company_id": company_id,
                    "query": query,
                    "target_role": target_role,
                    "context": context or {},
                },
                headers={
                    **self._get_headers(company_id),
                    "X-Target-Role": target_role,
                },
            )
            response.raise_for_status()
            return response.json()
    
    # ============================================================================
    # Call Processing APIs
    # ============================================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def process_call(
        self,
        call_id: str,
        company_id: str,
        audio_url: str,
        phone_number: str,
        duration: int,
        call_date: str,
        metadata: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit a call for AI processing.
        
        Args:
            call_id: Call UUID
            company_id: Company UUID
            audio_url: Public URL to audio file
            phone_number: Phone number
            duration: Call duration in seconds
            call_date: ISO 8601 datetime string
            metadata: Additional metadata
            webhook_url: Optional webhook URL for completion notification
            options: Processing options (skip_rag_indexing, skip_summary_generation, priority)
            
        Returns:
            Job response with job_id, status, etc.
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        payload = {
            "call_id": call_id,
            "company_id": company_id,
            "audio_url": audio_url,
            "phone_number": phone_number,
            "duration": duration,
            "call_date": call_date,
            "metadata": metadata or {},
            "options": options or {},
        }
        
        if webhook_url:
            payload["webhook_url"] = webhook_url
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/call-processing/process",
                json=payload,
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call_processing_status(
        self,
        job_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get call processing job status.
        
        Args:
            job_id: Shunya job ID
            company_id: Optional company ID for context
            
        Returns:
            Job status with progress, results, etc.
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/call-processing/status/{job_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call_summary(
        self,
        call_id: str,
        company_id: Optional[str] = None,
        include_chunks: bool = False,
    ) -> Dict[str, Any]:
        """
        Get call summary.
        
        Args:
            call_id: Call UUID
            company_id: Optional company ID
            include_chunks: Whether to include chunks in response
            
        Returns:
            Call summary with compliance, objections, qualification, etc.
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        params = {}
        if include_chunks:
            params["include_chunks"] = "true"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/call-processing/summary/{call_id}",
                params=params,
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call_chunks(
        self,
        call_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get call chunks.
        
        Args:
            call_id: Call UUID
            company_id: Optional company ID
            
        Returns:
            Call chunks with summaries and Milvus IDs
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/call-processing/chunks/{call_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def retry_failed_job(
        self,
        job_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retry a failed call processing job.
        
        Args:
            job_id: Shunya job ID to retry
            company_id: Optional company ID
            
        Returns:
            New job response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/call-processing/retry/{job_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    # ============================================================================
    # Ask Otto (Conversational AI) APIs
    # ============================================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_ask_otto_conversation(
        self,
        company_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new Ask Otto conversation.
        
        Args:
            company_id: Company UUID
            context: Optional conversation context
            
        Returns:
            Conversation data with conversation_id
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        payload = {
            "company_id": company_id,
        }
        if context:
            payload["context"] = context
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/ask-otto/conversations",
                json=payload,
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def send_ask_otto_message(
        self,
        conversation_id: str,
        message: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message in an Ask Otto conversation.
        
        Args:
            conversation_id: Conversation UUID
            message: User message
            company_id: Optional company ID
            
        Returns:
            Assistant response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=60.0) as client:  # Longer timeout for AI responses
            response = await client.post(
                f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}/messages",
                json={"message": message},
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_ask_otto_messages(
        self,
        conversation_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get all messages in an Ask Otto conversation.
        
        Args:
            conversation_id: Conversation UUID
            company_id: Optional company ID
            
        Returns:
            List of messages
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}/messages",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_ask_otto_conversation(
        self,
        conversation_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get Ask Otto conversation details.
        
        Args:
            conversation_id: Conversation UUID
            company_id: Optional company ID
            
        Returns:
            Conversation data
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def delete_ask_otto_conversation(
        self,
        conversation_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete an Ask Otto conversation.
        
        Args:
            conversation_id: Conversation UUID
            company_id: Optional company ID
            
        Returns:
            Deletion confirmation
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json() if response.content else {}
    
    # ============================================================================
    # Insights APIs
    # ============================================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_insights(
        self,
        week_start: str,
        week_end: str,
        company_ids: list[str],
        insight_types: list[str],
        company_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate insights for specified companies and week range.
        
        Args:
            week_start: Start date (YYYY-MM-DD)
            week_end: End date (YYYY-MM-DD)
            company_ids: List of company UUIDs
            insight_types: List of insight types (company, customer, objection, etc.)
            company_id: Optional company ID for context
            webhook_url: Optional webhook URL for completion notification
            options: Options (force_regenerate, include_inactive_customers)
            
        Returns:
            Job response with job_id
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        payload = {
            "week_start": week_start,
            "week_end": week_end,
            "company_ids": company_ids,
            "insight_types": insight_types,
            "options": options or {},
        }
        
        if webhook_url:
            payload["webhook_url"] = webhook_url
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/insights/generate",
                json=payload,
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_insight_job_status(
        self,
        job_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get insight generation job status.
        
        Args:
            job_id: Shunya job ID
            company_id: Optional company ID
            
        Returns:
            Job status
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/insights/status/{job_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_current_company_insight(
        self,
        company_id: str,
    ) -> Dict[str, Any]:
        """
        Get current company insight.
        
        Args:
            company_id: Company UUID
            
        Returns:
            Current company insight data
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/insights/company/{company_id}/current",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_customer_insights(
        self,
        company_id: str,
        week_start: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get customer insights.
        
        Args:
            company_id: Company UUID
            week_start: Optional week start date (YYYY-MM-DD)
            status: Optional status filter
            priority: Optional priority filter
            page: Page number (default: 1)
            limit: Results per page (default: 50, max: 200)
            
        Returns:
            Paginated customer insights
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        params = {
            "company_id": company_id,
            "page": page,
            "limit": min(limit, 200),
        }
        if week_start:
            params["week_start"] = week_start
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/insights/customers",
                params=params,
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_objection_insights(
        self,
        company_id: str,
    ) -> Dict[str, Any]:
        """
        Get objection insights for a company.
        
        Args:
            company_id: Company UUID
            
        Returns:
            Objection insights data
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/insights/objections/{company_id}",
                headers=self._get_headers(company_id),
            )
            response.raise_for_status()
            return response.json()


# Global client instance
_shoonya_client: Optional[ShoonyaClient] = None


def get_shoonya_client() -> ShoonyaClient:
    """Get Shoonya client instance."""
    global _shoonya_client
    if _shoonya_client is None:
        _shoonya_client = ShoonyaClient()
    return _shoonya_client

