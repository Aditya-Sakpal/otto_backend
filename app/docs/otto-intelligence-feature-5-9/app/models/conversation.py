"""
Conversation Models

MongoDB document models for Ask Otto chat enhancement.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .enums import CorpusType


# ============================================================================
# CONVERSATION MODELS
# ============================================================================

class Conversation(BaseModel):
    """Chat conversation document"""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    company_id: str = Field(..., description="Company/tenant identifier")
    user_id: str = Field(..., description="User who created the conversation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="Auto-delete timestamp")
    message_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# MESSAGE MODELS
# ============================================================================

class MessageSource(BaseModel):
    """Source citation for message"""
    type: CorpusType
    call_id: Optional[str] = None
    chunk_id: Optional[str] = None
    date: Optional[datetime] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    excerpt: Optional[str] = None
    url: Optional[str] = None
    
    class Config:
        use_enum_values = True


class CustomerContext(BaseModel):
    """Customer context in message"""
    customer_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    qualification_status: Optional[str] = None
    total_calls: Optional[int] = None
    last_call_date: Optional[datetime] = None


class MessageMetadata(BaseModel):
    """Message metadata"""
    tokens_used: Optional[int] = None
    response_time_ms: Optional[int] = None
    rag_results_count: Optional[int] = None
    customer_context_found: bool = False


class Message(BaseModel):
    """Chat message document"""
    message_id: str = Field(..., description="Unique message identifier")
    conversation_id: str = Field(..., description="Parent conversation ID")
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text content")
    sources: List[MessageSource] = Field(default_factory=list)
    customer_context: Optional[CustomerContext] = None
    suggested_follow_ups: List[str] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ============================================================================
# LANGGRAPH STATE MODELS
# ============================================================================

class ExtractedEntities(BaseModel):
    """Entities extracted from query"""
    customer_name: Optional[str] = None
    location: Optional[str] = None
    phone_number: Optional[str] = None
    topic: Optional[str] = None
    date_range: Optional[Dict[str, Any]] = None


class RequiresData(BaseModel):
    """What data sources are required"""
    customer_context: bool = False
    rag_search: bool = False
    analytics: bool = False
    crm: bool = False


class ClassificationResult(BaseModel):
    """Classification of user query"""
    intent: str = Field(..., description="Detected intent")
    entities: ExtractedEntities
    requires: RequiresData


class AskOttoState(BaseModel):
    """State object passed between LangGraph nodes"""
    conversation_id: str
    user_message: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    
    # Classification results
    intent: Optional[str] = None
    entities: Optional[ExtractedEntities] = None
    requires: Optional[RequiresData] = None
    
    # Tool results
    customer_context: Optional[Dict[str, Any]] = None
    rag_results: Optional[List[Dict[str, Any]]] = None
    analytics_data: Optional[Dict[str, Any]] = None
    crm_data: Optional[Dict[str, Any]] = None
    
    # Merged context
    merged_context: Optional[Dict[str, Any]] = None
    
    # Final output
    answer: Optional[str] = None
    sources: Optional[List[MessageSource]] = None
    follow_ups: Optional[List[str]] = None
    
    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# RAG SEARCH MODELS
# ============================================================================

class RAGSearchResult(BaseModel):
    """Single RAG search result"""
    id: str
    score: float = Field(..., ge=0.0, le=1.0)
    corpus_type: CorpusType
    doc_id: str  # call_id
    chunk_id: Optional[str] = None
    text_content: str
    summary_json: Optional[Dict[str, Any]] = None
    customer_phone: Optional[str] = None
    call_date: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


class RAGSearchRequest(BaseModel):
    """RAG search request"""
    query: str
    company_id: str
    corpus_types: List[CorpusType] = Field(
        default_factory=lambda: [CorpusType.CALL_SUMMARY, CorpusType.CHUNK_SUMMARY]
    )
    max_results: int = Field(5, ge=1, le=20)
    filters: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# ============================================================================
# CUSTOMER CONTEXT MODELS
# ============================================================================

class CustomerContextRequest(BaseModel):
    """Customer context lookup request"""
    company_id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


class CustomerContextResult(BaseModel):
    """Customer context result"""
    customer_id: str
    name: Optional[str] = None
    phone: str
    address: Optional[str] = None
    location: Optional[str] = None
    total_calls: int
    last_call_date: Optional[datetime] = None
    qualification_status: Optional[str] = None
    recent_calls: List[Dict[str, Any]] = Field(default_factory=list)

