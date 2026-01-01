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
        self.api_key = settings.UWC_API_KEY
        self.hmac_secret = settings.UWC_HMAC_SECRET
        self.jwt_secret = settings.UWC_JWT_SECRET
        
        if not self.base_url or not self.api_key:
            logger.warning("Shoonya not configured - features will be disabled")
            self._enabled = False
        else:
            self._enabled = True
    
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
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Company-Id": company_id,
                },
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
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Company-Id": company_id,
                },
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
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Company-Id": company_id,
                    "X-Target-Role": target_role,
                },
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

