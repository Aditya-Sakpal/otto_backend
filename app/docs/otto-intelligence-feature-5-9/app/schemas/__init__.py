"""
API Schemas Package

Centralized Pydantic schemas for API request/response validation.
"""

from .call import (
    ProcessingOptions,
    ProcessCallRequest,
    ProcessCallResponse,
    ProgressInfo,
    ProcessingResults,
    ProcessingMetadata,
    ErrorInfo,
    JobStatusResponse,
    CallSummaryResponse,
    ChunkInfo,
    ChunksResponse,
    RetryJobRequest,
    RetryJobResponse,
    TranscriptSegment,
    TranscriptResponse,
)

from .phase import (
    PhaseResponse,
    CallPhasesResponse,
    PhaseSearchResponse,
    CompanyPhaseAnalyticsResponse,
)

from .insight import (
    GenerateInsightsRequest,
    GenerateInsightsResponse,
    InsightJobStatusResponse,
    CompanyInsightResponse,
    CustomerInsightResponse,
    CustomersInsightsResponse,
    CustomerInsightListItem,
    ObjectionInsightResponse,
    InsightGenerationProgress,
    InsightGenerationResults,
)

from .sop import (
    SOPUploadRequest,
    SOPUploadResponse,
    SOPStatusResponse,
    SOPMetricsResponse,
    SOPDocumentResponse,
    SOPListResponse,
    SOPStatusUpdateRequest,
)

from .ask_otto import (
    CreateConversationRequest,
    CreateConversationResponse,
    SendMessageRequest,
    SendMessageResponse,
    MessageHistoryItem,
    GetMessagesResponse,
    GetConversationResponse,
)

__all__ = [
    # Call schemas
    "ProcessingOptions",
    "ProcessCallRequest",
    "ProcessCallResponse",
    "ProgressInfo",
    "ProcessingResults",
    "ProcessingMetadata",
    "ErrorInfo",
    "JobStatusResponse",
    "CallSummaryResponse",
    "ChunkInfo",
    "ChunksResponse",
    "RetryJobRequest",
    "RetryJobResponse",
    "TranscriptSegment",
    "TranscriptResponse",
    # Phase schemas
    "PhaseResponse",
    "CallPhasesResponse",
    "PhaseSearchResponse",
    "CompanyPhaseAnalyticsResponse",
    # Insight schemas
    "GenerateInsightsRequest",
    "GenerateInsightsResponse",
    "InsightJobStatusResponse",
    "CompanyInsightResponse",
    "CustomerInsightResponse",
    "CustomersInsightsResponse",
    "CustomerInsightListItem",
    "ObjectionInsightResponse",
    "InsightGenerationProgress",
    "InsightGenerationResults",
    # SOP schemas
    "SOPUploadRequest",
    "SOPUploadResponse",
    "SOPStatusResponse",
    "SOPMetricsResponse",
    "SOPDocumentResponse",
    "SOPListResponse",
    "SOPStatusUpdateRequest",
    # Ask Otto schemas
    "CreateConversationRequest",
    "CreateConversationResponse",
    "SendMessageRequest",
    "SendMessageResponse",
    "MessageHistoryItem",
    "GetMessagesResponse",
    "GetConversationResponse",
]
