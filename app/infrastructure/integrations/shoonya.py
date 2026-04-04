"""
Shoonya/UWC client.

Abstraction for Shoonya AI/ML services.
"""
from typing import Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import traceback
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Peer-comparison can be slow on Shunya (heavy aggregates); shared client default is 30s read.
# httpx.Timeout requires either one default or all of connect/read/write/pool (see httpx._config).
_PEER_COMPARISON_TIMEOUT = httpx.Timeout(
    connect=20.0,
    read=120.0,
    write=30.0,
    pool=30.0,
)


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
        # Use API_KEY (new) or fall back to UWC_API_KEY (legacy) or UWC_JWT_SECRET
        self.api_key = settings.API_KEY or settings.UWC_API_KEY or settings.UWC_JWT_SECRET
        self.hmac_secret = settings.UWC_HMAC_SECRET
        self.jwt_secret = settings.UWC_JWT_SECRET

        # Ensure base_url doesn't have trailing slash and is correct
        if self.base_url:
            self.base_url = self.base_url.rstrip('/')
            # Validate URL format
            if not self.base_url.startswith('http'):
                logger.error(f"Invalid UWC_BASE_URL format: {self.base_url}. Must start with http:// or https://")
                self._enabled = False
            elif 'otto.shunyalabs.ai' in self.base_url and 'ottoai' not in self.base_url:
                # Fix common typo: otto.shunyalabs.ai -> ottoai.shunyalabs.ai
                logger.warning(f"Detected incorrect base URL: {self.base_url}. Should be https://ottoai.shunyalabs.ai")
                self.base_url = self.base_url.replace('otto.shunyalabs.ai', 'ottoai.shunyalabs.ai')
                logger.info(f"Auto-corrected base URL to: {self.base_url}")

        if not self.base_url or not self.api_key:
            logger.warning("Shoonya not configured - features will be disabled")
            self._enabled = False
        else:
            self._enabled = True
            logger.info(f"Shoonya client initialized with base URL: {self.base_url}")

        # Persistent HTTP client shared across all calls — avoids a new TCP/TLS
        # handshake on every request (critical for parallel coaching dashboard calls).
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def _get_headers(self, company_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, str]:
        """Get standard headers for Shunya API requests."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if company_id:
            headers["X-Company-Id"] = company_id
        if user_id:
            headers["X-User-Id"] = user_id
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
        user_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query Ask Otto (RAG).

        Args:
            company_id: Company/tenant ID
            query: User query
            target_role: Target role for context
            context: Additional context
            user_id: Optional user ID for personalized responses
            user_context: Optional user identity (name, role, email)

        Returns:
            RAG query result
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        payload = {
            "company_id": company_id,
            "query": query,
            "target_role": target_role,
            "context": context or {},
        }
        if user_id:
            payload["user_id"] = user_id
        if user_context:
            payload["user_context"] = user_context

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/rag/ask-otto",
                json=payload,
                headers={
                    **self._get_headers(company_id, user_id=user_id),
                    "X-Target-Role": target_role,
                },
            )
            response.raise_for_status()
            return response.json()

    # ============================================================================
    # Health & Status APIs
    # ============================================================================

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the service is healthy and running.

        Returns:
            Health status response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/health"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error checking health: {e}")
            traceback.print_exc()
            raise

    async def get_root_info(self) -> Dict[str, Any]:
        """
        Get basic service information and links.

        Returns:
            Service info response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting root info: {e}")
            traceback.print_exc()
            raise

    async def get_api_status(self) -> Dict[str, Any]:
        """
        Get API version and feature status.

        Returns:
            API status response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/status"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting API status: {e}")
            traceback.print_exc()
            raise

    async def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get the status of background scheduler and scheduled jobs.

        Returns:
            Scheduler status response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/scheduler/status"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            traceback.print_exc()
            raise

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
        try:
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

            url = f"{self.base_url}/api/v1/call-processing/process"
            logger.info(f"Calling Shunya API: {url}")
            logger.debug(f"Payload: {payload}")
            logger.debug(f"Headers: {self._get_headers(company_id)}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url if 'url' in locals() else f"{self.base_url}/api/v1/call-processing/process",
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error processing call: {e}")
            traceback.print_exc()
            raise


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

        url = f"{self.base_url}/api/v1/call-processing/status/{job_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call processing status: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/call-processing/summary/{call_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call summary: {e}")
            traceback.print_exc()
            raise

    async def get_call_detail(
        self,
        call_id: str,
        company_id: Optional[str] = None,
        include_transcript: bool = True,
        include_segments: bool = False,
    ) -> Dict[str, Any]:
        """
        Get call detail including transcript and diarized segments.

        Args:
            call_id: Call UUID
            company_id: Optional company ID
            include_transcript: Whether to include full transcript (default: True)
            include_segments: Whether to include diarized segments (default: False)

        Returns:
            Call detail with transcript, segments, metadata, etc.
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        params = {
            "include_transcript": str(include_transcript).lower(),
            "include_segments": str(include_segments).lower(),
        }

        url = f"{self.base_url}/api/v1/call-processing/calls/{call_id}/detail"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya call detail API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call detail: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/call-processing/chunks/{call_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call chunks: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/call-processing/retry/{job_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error retrying call processing job: {e}")
            traceback.print_exc()
            raise

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
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new Ask Otto conversation.

        Args:
            company_id: Company UUID
            user_id: Optional user ID (defaults to "anonymous" if not provided)
            metadata: Optional metadata (source, user_role, etc.)
            user_context: Optional user identity context (name, role, email)

        Returns:
            Conversation data with conversation_id
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        # user_id is required by Shunya API - use "anonymous" as default
        effective_user_id = user_id or "anonymous"
        payload = {
            "company_id": company_id,
            "user_id": effective_user_id,
        }
        # Merge user_context into metadata so Shunya knows who is asking
        merged_metadata = dict(metadata or {})
        if user_context:
            merged_metadata["user_context"] = user_context
        if merged_metadata:
            payload["metadata"] = merged_metadata

        url = f"{self.base_url}/api/v1/ask-otto/conversations"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(company_id, user_id=effective_user_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error creating Ask Otto conversation: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def send_ask_otto_message(
        self,
        conversation_id: str,
        message: str,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to Otto and get an AI-powered response with context from call data.

        Args:
            conversation_id: Conversation UUID
            message: User message
            company_id: Optional company ID
            user_id: Optional user ID for personalized responses
            user_context: Optional user identity (name, role, email) for personalized responses
            context: Optional context (include_customer_context, include_call_history, max_rag_results, search_filters)
            options: Optional options (stream, include_sources, suggest_follow_ups)

        Returns:
            Assistant response with answer, sources, customer_context, suggested_follow_ups
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        payload = {"message": message}
        # Include user identity so Shunya can personalize responses
        if user_id:
            payload["user_id"] = user_id
        if user_context:
            payload["user_context"] = user_context
        if context:
            payload["context"] = context
        if options:
            payload["options"] = options

        url = f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}/messages"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:  # Longer timeout for AI responses
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(company_id, user_id=user_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error sending Ask Otto message: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_ask_otto_messages(
        self,
        conversation_id: str,
        company_id: Optional[str] = None,
        limit: Optional[int] = None,
        before: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve message history for a conversation.

        Args:
            conversation_id: Conversation UUID
            company_id: Optional company ID
            limit: Optional number of messages to return (default: 50, max: 200)
            before: Optional message ID for pagination (returns messages before this ID)

        Returns:
            List of messages with pagination info
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        params = {}
        if limit:
            params["limit"] = min(limit, 200)
        if before:
            params["before"] = before

        url = f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}/messages"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params if params else None,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting Ask Otto messages: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting Ask Otto conversation: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/ask-otto/conversations/{conversation_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json() if response.content else {}
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error deleting Ask Otto conversation: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/insights/generate"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/insights/status/{job_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting insight job status: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/insights/company/{company_id}/current"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting company insight: {e}")
            traceback.print_exc()
            raise

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

        url = f"{self.base_url}/api/v1/insights/customers"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting customer insights: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_objection_insights(
        self,
        company_id: str,
        week_start: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get objection insights for a company showing common objections and handling effectiveness.

        Args:
            company_id: Company UUID
            week_start: Optional week start date (YYYY-MM-DD)
            category_id: Optional objection category ID (1-10)

        Returns:
            Objection insights data
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        params = {}
        if week_start:
            params["week_start"] = week_start
        if category_id:
            params["category_id"] = category_id

        url = f"{self.base_url}/api/v1/insights/objections/{company_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params if params else None,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting objection insights: {e}")
            traceback.print_exc()
            raise

    # ============================================================================
    # SOP Document Ingestion APIs
    # ============================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def upload_sop_document(
        self,
        file_path: Optional[str] = None,
        file_url: Optional[str] = None,
        company_id: str = None,
        sop_name: str = None,
        target_role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a Standard Operating Procedure document for processing.

        Supports two methods:
        1. Direct file upload via file_path (existing behavior)
        2. URL-based upload via file_url (new - supports S3 URLs, HTTP/HTTPS URLs)

        Args:
            file_path: Path to the SOP document file (PDF, DOC, DOCX) - for direct upload
            file_url: URL to download document from (S3, HTTP/HTTPS) - for URL-based upload
            company_id: Company identifier
            sop_name: Name of the SOP
            target_role: Optional target role (None for company-wide).
                        Use "customer_rep" for CSR phone call SOPs, "sales_rep" for sales meeting SOPs
            metadata: Optional additional metadata
            webhook_url: Optional callback URL for completion notification

        Returns:
            Job response with job_id

        Raises:
            ValueError: If neither file_path nor file_url is provided, or both are provided
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        # Validate that exactly one of file_path or file_url is provided
        if not file_path and not file_url:
            raise ValueError("Either 'file_path' (for file upload) or 'file_url' (for URL download) must be provided")
        if file_path and file_url:
            raise ValueError("Provide either 'file_path' OR 'file_url', not both")

        url = f"{self.base_url}/api/v1/sop/documents/upload"
        logger.info(f"Calling Shunya API: {url}")

        try:
            # Prepare form data
            data = {
                "company_id": company_id,
                "sop_name": sop_name,
            }
            if target_role:
                data["target_role"] = target_role
            if metadata:
                import json
                data["metadata"] = json.dumps(metadata)
            if webhook_url:
                data["webhook_url"] = webhook_url

            # For multipart/form-data, don't set Content-Type header (httpx will set it)
            headers = {"X-API-Key": self.api_key}
            if company_id:
                headers["X-Company-Id"] = company_id

            async with httpx.AsyncClient(timeout=60.0) as client:
                if file_path:
                    # Method 1: Direct file upload (existing behavior)
                    import os
                    file_name = os.path.basename(file_path)

                    # Determine content type based on file extension
                    content_type = "application/pdf"
                    if file_name.lower().endswith(".doc"):
                        content_type = "application/msword"
                    elif file_name.lower().endswith(".docx"):
                        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                    # Open file and prepare multipart form data
                    with open(file_path, "rb") as f:
                        files = {"file": (file_name, f, content_type)}
                        response = await client.post(
                            url,
                            files=files,
                            data=data,
                            headers=headers,
                        )
                else:
                    # Method 2: URL-based upload (new)
                    data["file_url"] = file_url
                    response = await client.post(
                        url,
                        data=data,
                        headers=headers,
                    )

                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error uploading SOP document: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_sop_processing_status(
        self,
        job_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check the processing status of an uploaded SOP document.

        Args:
            job_id: The job ID from upload response
            company_id: Optional company ID

        Returns:
            Job status response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/sop/documents/status/{job_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting SOP processing status: {e}")
            traceback.print_exc()
            raise

    async def get_sop_metrics(
        self,
        company_id: str,
        role: Optional[str] = None,
        sop_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get all active SOP metrics for a company.

        Args:
            company_id: Company identifier
            role: Optional filter by target role
            sop_id: Optional get specific SOP metrics

        Returns:
            SOP metrics response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        params = {}
        if role:
            params["role"] = role
        if sop_id:
            params["sop_id"] = sop_id

        url = f"{self.base_url}/api/v1/sop/metrics/{company_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params if params else None,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting SOP metrics: {e}")
            traceback.print_exc()
            raise

    async def get_sop_document(
        self,
        sop_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific SOP document.

        Args:
            sop_id: The SOP document identifier
            company_id: Optional company ID

        Returns:
            SOP document details
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/sop/documents/{sop_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting SOP document: {e}")
            traceback.print_exc()
            raise

    async def list_sop_documents(
        self,
        company_id: str,
        status: Optional[str] = None,
        target_role: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Get a paginated list of SOP documents for a company.

        Args:
            company_id: Company identifier
            status: Optional filter by status (active, inactive, draft)
            target_role: Optional filter by target role
            page: Page number (default: 1)
            limit: Results per page (default: 20, max: 100)

        Returns:
            Paginated list of SOP documents
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        params = {
            "company_id": company_id,
            "page": page,
            "limit": min(limit, 100),
        }
        if status:
            params["status"] = status
        if target_role:
            params["target_role"] = target_role

        url = f"{self.base_url}/api/v1/sop/documents"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error listing SOP documents: {e}")
            traceback.print_exc()
            raise

    async def update_sop_status(
        self,
        sop_id: str,
        status: str,
        reason: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update the status of an SOP document (activate/deactivate).

        Args:
            sop_id: The SOP document identifier
            status: New status (active, inactive)
            reason: Optional reason for status change
            company_id: Optional company ID

        Returns:
            Update response
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        payload = {"status": status}
        if reason:
            payload["reason"] = reason

        url = f"{self.base_url}/api/v1/sop/documents/{sop_id}/status"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    url,
                    json=payload,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error updating SOP status: {e}")
            traceback.print_exc()
            raise

    async def delete_sop_document(
        self,
        sop_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """
        Permanently delete an SOP document and all associated data.

        Args:
            sop_id: The SOP document identifier
            company_id: Optional company ID
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/sop/documents/{sop_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    url,
                    headers=self._get_headers(company_id),
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error deleting SOP document: {e}")
            traceback.print_exc()
            raise

    # ============================================================================
    # Coaching & Progression APIs
    # ============================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_agent_progression(
        self,
        rep_id: str,
        company_id: str,
        metrics: str = "compliance_score,booking_rate",
        weeks: int = 8,
    ) -> Dict[str, Any]:
        """
        Get agent progression tracking data.

        Args:
            rep_id: Representative/agent ID
            company_id: Company UUID
            metrics: Comma-separated metric names
            weeks: Number of weeks to analyze (default 8)

        Returns:
            Agent progression data with weekly metrics, trends, and anomalies
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/insights/agents/{rep_id}/progression"
        params = {
            "company_id": company_id,
            "metrics": metrics,
            "weeks": weeks,
        }
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting agent progression: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_agent_peer_comparison(
        self,
        rep_id: str,
        company_id: str,
        metric: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get on-demand peer comparison for a specific metric.

        Args:
            rep_id: Representative/agent ID
            company_id: Company UUID
            metric: Metric name to compare
            days: Analysis period in days

        Returns:
            Peer comparison data with rank, percentile, averages
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/insights/agents/{rep_id}/peer-comparison"
        params = {
            "company_id": company_id,
            "metric": metric,
            "days": days,
        }
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
                timeout=_PEER_COMPARISON_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting agent peer comparison: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_agents_summary(
        self,
        company_id: str,
        weeks: int = 4,
    ) -> Dict[str, Any]:
        """
        Get manager dashboard summary of all agents.

        Args:
            company_id: Company UUID
            weeks: Analysis period in weeks

        Returns:
            Summary data for all agents in the company
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/insights/agents/summary"
        params = {
            "company_id": company_id,
            "weeks": weeks,
        }
        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting agents summary: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call_summaries(
        self,
        company_id: str,
        rep_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """
        List call summaries from Shunya with filters.

        Args:
            company_id: Company UUID
            rep_id: Optional rep ID filter
            from_date: Optional start date filter (ISO format)
            to_date: Optional end date filter (ISO format)
            limit: Results per page
            offset: Pagination offset
            sort_by: Sort field
            sort_order: Sort direction

        Returns:
            Paginated list of call summaries
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/call-processing/summaries"
        params = {
            "company_id": company_id,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if rep_id:
            params["rep_id"] = rep_id
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        logger.info(f"Calling Shunya API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(company_id),
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Shunya API: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call summaries: {e}")
            traceback.print_exc()
            raise

    async def _get_call_conversation_phases_once(
        self,
        call_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Single GET for conversation phases (no retries).

        GET /api/v1/call-processing/calls/{call_id}/phases
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/call-processing/calls/{call_id}/phases"
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                timeout=60.0,  # Phases API can take ~15s; use extended timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting call conversation phases: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting call conversation phases: {e}")
            traceback.print_exc()
            raise

    async def get_call_conversation_phases_no_retry(
        self,
        call_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Same as get_call_conversation_phases but without Tenacity retries (e.g. pipeline-detail fan-out)."""
        return await self._get_call_conversation_phases_once(call_id, company_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call_conversation_phases(
        self,
        call_id: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detected conversation phases for a call.

        GET /api/v1/call-processing/calls/{call_id}/phases
        """
        return await self._get_call_conversation_phases_once(call_id, company_id)

    # ============================================================================
    # Shunya Coaching Session APIs (Section 7)
    # ============================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_shunya_coaching_session(
        self,
        company_id: str,
        rep_id: str,
        rep_name: str,
        coach_id: str,
        coach_name: str,
        focus_areas: list,
        targets: dict = None,
        triggering_call_ids: list = None,
        follow_up_days: int = 7,
        notes: str = None,
    ) -> Dict[str, Any]:
        """
        Create a coaching session on Shunya.

        POST /api/v1/coaching/sessions
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/sessions"
        payload = {
            "company_id": company_id,
            "rep_id": rep_id,
            "rep_name": rep_name,
            "coach_id": coach_id,
            "coach_name": coach_name,
            "focus_areas": focus_areas,
            "follow_up_days": follow_up_days,
        }
        if targets:
            payload["targets"] = targets
        if triggering_call_ids:
            payload["triggering_call_ids"] = triggering_call_ids
        if notes:
            payload["notes"] = notes

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.post(
                url,
                headers=self._get_headers(company_id),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error creating Shunya coaching session: {e.response.status_code} {e.response.reason_phrase}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error creating Shunya coaching session: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_shunya_coaching_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get coaching session details from Shunya.

        GET /api/v1/coaching/sessions/{session_id}
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/sessions/{session_id}"
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting Shunya coaching session: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting Shunya coaching session: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_shunya_coaching_impact(self, session_id: str) -> Dict[str, Any]:
        """
        Get impact report from Shunya for a coaching session.

        GET /api/v1/coaching/sessions/{session_id}/impact
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/sessions/{session_id}/impact"
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting Shunya coaching impact: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting Shunya coaching impact: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def update_shunya_coaching_session_status(
        self,
        session_id: str,
        status: str,
        measure_impact: bool = True,
        extension_days: int = None,
        notes: str = None,
    ) -> Dict[str, Any]:
        """
        Update coaching session status on Shunya.

        PATCH /api/v1/coaching/sessions/{session_id}/status
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/sessions/{session_id}/status"
        payload = {"status": status, "measure_impact": measure_impact}
        if extension_days is not None:
            payload["extension_days"] = extension_days
        if notes:
            payload["notes"] = notes

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.patch(
                url,
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error updating Shunya coaching session status: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error updating Shunya coaching session status: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_shunya_coach_effectiveness(
        self,
        coach_id: str,
        company_id: str,
        timeframe_days: int = 90,
        use_cached: bool = False,
    ) -> Dict[str, Any]:
        """
        Get coach effectiveness metrics from Shunya.

        GET /api/v1/coaching/coaches/{coach_id}/effectiveness
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/coaches/{coach_id}/effectiveness"
        params = {"company_id": company_id, "timeframe_days": timeframe_days}
        if use_cached:
            params["use_cached"] = "true"

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting coach effectiveness: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting coach effectiveness: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_shunya_coaching_roi(
        self,
        company_id: str,
        timeframe_days: int = 90,
    ) -> Dict[str, Any]:
        """
        Get company-wide coaching ROI from Shunya.

        GET /api/v1/coaching/roi
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/roi"
        params = {"company_id": company_id, "timeframe_days": timeframe_days}

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting coaching ROI: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting coaching ROI: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def list_shunya_coaching_sessions(
        self,
        company_id: str,
        rep_id: str = None,
        coach_id: str = None,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List coaching sessions from Shunya.

        GET /api/v1/coaching/sessions
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/sessions"
        params = {"company_id": company_id, "limit": limit, "offset": offset}
        if rep_id:
            params["rep_id"] = rep_id
        if coach_id:
            params["coach_id"] = coach_id
        if status:
            params["status"] = status

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error listing Shunya coaching sessions: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error listing Shunya coaching sessions: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def list_coaching_reps(self, company_id: str) -> Dict[str, Any]:
        """
        List reps (agents) with calls for a company (Shunya aggregated coaching).

        GET /api/v1/coaching/reps
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        url = f"{self.base_url}/api/v1/coaching/reps"
        params = {"company_id": company_id}
        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error listing coaching reps: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error listing coaching reps: {e}")
            traceback.print_exc()
            raise

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=4, max=20),
    )
    async def get_rep_coaching_profile(
        self,
        company_id: str,
        rep_id: str,
        force_refresh: bool = False,
        window_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Full rep coaching profile (15 canonical categories, Shunya).

        GET /api/v1/coaching/reps/{rep_id}/profile

        First request with force_refresh may take 30–60s; uses extended HTTP timeout.
        """
        if not self.is_available():
            raise RuntimeError("Shoonya not configured")

        from urllib.parse import quote

        safe_rep = quote(rep_id, safe="")
        url = f"{self.base_url}/api/v1/coaching/reps/{safe_rep}/profile"
        params: Dict[str, Any] = {
            "company_id": company_id,
            "window_days": window_days,
        }
        if force_refresh:
            params["force_refresh"] = "false"

        logger.info(f"Calling Shunya API: {url}")

        try:
            response = await self._http_client.get(
                url,
                headers=self._get_headers(company_id),
                params=params,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting rep coaching profile: {e.response.status_code}",
                url=url,
                response_text=e.response.text[:500] if e.response.text else None,
            )
            traceback.print_exc()
            raise
        except Exception as e:
            logger.error(f"Error getting rep coaching profile: {e}")
            traceback.print_exc()
            raise


# Global client instance
_shoonya_client: Optional[ShoonyaClient] = None


def get_shoonya_client() -> ShoonyaClient:
    """Get Shoonya client instance."""
    global _shoonya_client
    if _shoonya_client is None:
        _shoonya_client = ShoonyaClient()
    return _shoonya_client

