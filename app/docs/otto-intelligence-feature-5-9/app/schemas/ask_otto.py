"""
Ask Otto API Schemas

Pydantic schemas for Ask Otto chat API request/response validation.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from ..models.conversation import MessageSource, CustomerContext, MessageMetadata
from ..models.enums import CorpusType
from ..utils.uuid_validator import validate_uuid


# ============================================================================
# CONVERSATION REQUEST/RESPONSE SCHEMAS
# ============================================================================

class CreateConversationRequest(BaseModel):
    """Request to create new conversation"""
    company_id: str = Field(..., description="Company/tenant identifier (UUID format required)")
    user_id: str = Field(..., description="User creating the conversation (string or UUID)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('company_id')
    @classmethod
    def validate_company_id(cls, v):
        return validate_uuid(v, "company_id")


class CreateConversationResponse(BaseModel):
    """Response after creating conversation"""
    conversation_id: str
    company_id: str
    user_id: str
    created_at: datetime
    message_count: int
    expires_at: datetime


class GetConversationResponse(BaseModel):
    """Get conversation details"""
    conversation_id: str
    company_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    expires_at: datetime
    metadata: Dict[str, Any]


# ============================================================================
# MESSAGE REQUEST/RESPONSE SCHEMAS
# ============================================================================

class MessageContextOptions(BaseModel):
    """Context options for message"""
    include_customer_context: bool = True
    include_call_history: bool = True
    max_rag_results: int = Field(5, ge=1, le=20)
    search_filters: Dict[str, Any] = Field(default_factory=dict)


class MessageOptions(BaseModel):
    """Message processing options"""
    stream: bool = False
    include_sources: bool = True
    suggest_follow_ups: bool = True


class SendMessageRequest(BaseModel):
    """Request to send message"""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    context: MessageContextOptions = Field(default_factory=MessageContextOptions)
    options: MessageOptions = Field(default_factory=MessageOptions)


class SendMessageResponse(BaseModel):
    """Response after sending message"""
    conversation_id: str
    message_id: str
    answer: str
    sources: List[MessageSource] = Field(default_factory=list)
    customer_context: Optional[CustomerContext] = None
    suggested_follow_ups: List[str] = Field(default_factory=list)
    metadata: MessageMetadata
    created_at: datetime


# ============================================================================
# MESSAGE HISTORY SCHEMAS
# ============================================================================

class MessageHistoryItem(BaseModel):
    """Single message in history"""
    message_id: str
    role: str
    content: str
    sources: List[MessageSource] = Field(default_factory=list)
    created_at: datetime


class GetMessagesResponse(BaseModel):
    """Response for message history"""
    conversation_id: str
    messages: List[MessageHistoryItem]
    total_messages: int
    has_more: bool


class GetMessagesQueryParams(BaseModel):
    """Query params for getting messages"""
    limit: int = Field(50, ge=1, le=200)
    before: Optional[str] = Field(None, description="Message ID for pagination")


# ============================================================================
# RAG SEARCH SCHEMAS (Internal)
# ============================================================================

class RAGSearchFilters(BaseModel):
    """Filters for RAG search"""
    date_range: Optional[Dict[str, str]] = None
    qualification_status: Optional[List[str]] = None
    corpus_types: List[CorpusType] = Field(
        default_factory=lambda: [CorpusType.CALL_SUMMARY, CorpusType.CHUNK_SUMMARY]
    )
    
    class Config:
        use_enum_values = True


class RAGResultItem(BaseModel):
    """Single RAG search result"""
    call_id: str
    chunk_id: Optional[str] = None
    score: float = Field(..., ge=0.0, le=1.0)
    corpus_type: CorpusType
    excerpt: str
    date: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# ============================================================================
# CUSTOMER CONTEXT SCHEMAS (Internal)
# ============================================================================

class CustomerContextLookupRequest(BaseModel):
    """Request to lookup customer context"""
    company_id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


class CustomerContextResult(BaseModel):
    """Customer context result"""
    customer_id: str
    name: Optional[str] = None
    phone: str
    location: Optional[str] = None
    qualification_status: Optional[str] = None
    total_calls: int
    last_call_date: Optional[datetime] = None
    recent_calls_summary: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# LANGGRAPH STATE SCHEMAS (Internal)
# ============================================================================

class ClassificationRequest(BaseModel):
    """Request for query classification"""
    query: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class EntityExtractionResult(BaseModel):
    """Extracted entities from query"""
    customer_name: Optional[str] = None
    location: Optional[str] = None
    phone_number: Optional[str] = None
    topic: Optional[str] = None
    date_range: Optional[Dict[str, Any]] = None


class RequiresAnalysis(BaseModel):
    """What data sources are required"""
    customer_context: bool = False
    rag_search: bool = False
    analytics: bool = False
    crm: bool = False


class QueryClassificationResult(BaseModel):
    """Result of query classification"""
    intent: str
    entities: EntityExtractionResult
    requires: RequiresAnalysis
    confidence: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# SYNTHESIS SCHEMAS (Internal)
# ============================================================================

class SynthesisRequest(BaseModel):
    """Request for response synthesis"""
    user_message: str
    conversation_history: List[Dict[str, str]]
    merged_context: Dict[str, Any]
    classification: QueryClassificationResult


class SynthesisResponse(BaseModel):
    """Synthesized response"""
    answer: str
    sources: List[MessageSource]
    suggested_follow_ups: List[str]
    confidence: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# ERROR SCHEMAS
# ============================================================================

class AskOttoErrorResponse(BaseModel):
    """Error response"""
    error: str
    message: str
    conversation_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

