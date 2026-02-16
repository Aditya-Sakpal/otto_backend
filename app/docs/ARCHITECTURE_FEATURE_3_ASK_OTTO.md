# Feature 3: Ask Otto Chat Enhancement API

**Version:** 4.0  
**Date:** February 4, 2026  
**Service:** Independent Microservice Architecture  
**Implementation:** FastAPI + Sequential Pipeline + Local Embeddings

> **Last Updated:** February 2026 - Uses simplified sequential orchestration (not full LangGraph), enhanced SOP integration, dual-write caching pattern.

---

## Overview

Ask Otto is an enhanced conversational AI system that provides intelligent Q&A capabilities with:
- **Multi-turn conversation history** stored in MongoDB with Redis caching
- **RAG integration** with Milvus Zilliz Cloud for semantic search
- **Customer context** retrieval from MongoDB by phone number or name
- **Sequential pipeline orchestration** for tool routing (not full LangGraph)
- **Multi-source data fusion** from calls, summaries, chunks, SOP documents, and customer records
- **Local HuggingFace embeddings** for fast, cost-effective semantic search

**Implementation Status**: ✅ **Fully Implemented** - Uses GROQ for LLM (llama-3.3-70b-versatile) and local Sentence Transformers for embeddings.

### Key Enhancements (v4.0)

| Enhancement | Description |
|-------------|-------------|
| **Simplified Orchestration** | Sequential pipeline (not LangGraph) for reliability |
| **SOP Integration** | Automatic SOP query detection and corpus search |
| **Dual-Write Caching** | MongoDB + Redis for high availability |
| **Customer Context** | Recent calls summary, qualification tracking |
| **Response Metadata** | Tracks response_time_ms, rag_results_count |
| **Follow-up Suggestions** | Rule-based context-aware suggestions |

### Architecture Note

The implementation uses a **simplified sequential pipeline** rather than the LangGraph library:

```
Query Classification → SOP Detection → RAG Search → 
Customer Context → Response Synthesis → Source Extraction
```

This provides better reliability and easier debugging while maintaining the same capabilities.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ASK OTTO CHAT ENHANCEMENT - API FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CLIENT (Dashboard / Otto Backend)                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │    POST /api/v1/ask-otto/conversations                               │   │
│  │                                                                      │   │
│  │    Request: Create New Conversation                                  │   │
│  │    {                                                                 │   │
│  │      "company_id": "acme_roofing",                                   │   │
│  │      "user_id": "user_123",                                          │   │
│  │      "metadata": {                                                   │   │
│  │        "source": "dashboard",                                        │   │
│  │        "user_name": "Manager John"                                   │   │
│  │      }                                                               │   │
│  │    }                                                                 │   │
│  │                                                                      │   │
│  │    Response (201 Created):                                           │   │
│  │    {                                                                 │   │
│  │      "conversation_id": "conv_abc123",                               │   │
│  │      "company_id": "acme_roofing",                                   │   │
│  │      "user_id": "user_123",                                          │   │
│  │      "created_at": "2026-01-08T10:30:00Z",                           │   │
│  │      "message_count": 0                                              │   │
│  │    }                                                                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │    POST /api/v1/ask-otto/conversations/{id}/messages                 │   │
│  │                                                                      │   │
│  │    Request: Send Message                                             │   │
│  │    {                                                                 │   │
│  │      "message": "What did Kevin from Arizona say about roof leak?",  │   │
│  │      "context": {                                                    │   │
│  │        "include_customer_context": true,                             │   │
│  │        "max_rag_results": 5                                          │   │
│  │      }                                                               │   │
│  │    }                                                                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              STEP 1: LOAD CONVERSATION CONTEXT                       │   │
│  │                                                                      │   │
│  │  Redis Cache Check:                                                  │   │
│  │  Key: conversation:{conv_id}:context                                 │   │
│  │                                                                      │   │
│  │  Cache Miss → MongoDB Query:                                         │   │
│  │  db.ask_otto_messages.find({                                         │   │
│  │    conversation_id: "conv_abc123"                                    │   │
│  │  }).sort({ created_at: -1 }).limit(10)                               │   │
│  │                                                                      │   │
│  │  Result: Last 5 Q&A pairs (sliding window)                           │   │
│  │  [                                                                   │   │
│  │    {role: "user", content: "Previous question 1"},                   │   │
│  │    {role: "assistant", content: "Previous answer 1"},                │   │
│  │    ...                                                               │   │
│  │  ]                                                                   │   │
│  │                                                                      │   │
│  │  Cache in Redis (TTL: 30 minutes)                                    │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │            STEP 2: LANGGRAPH AGENT ORCHESTRATION                     │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │  NODE 1: CLASSIFY & EXTRACT                                     │  │   │
│  │  │                                                                 │  │   │
│  │  │  LLM analyzes query and extracts:                               │  │   │
│  │  │  • Intent: "query_customer_call"                                │  │   │
│  │  │  • Entities:                                                    │  │   │
│  │  │    - customer_name: "Kevin"                                     │  │   │
│  │  │    - location: "Arizona"                                        │  │   │
│  │  │    - topic: "roof leak"                                         │  │   │
│  │  │    - phone_number: null (not detected)                          │  │   │
│  │  │  • Requires:                                                    │  │   │
│  │  │    - Customer context: YES                                      │  │   │
│  │  │    - RAG search: YES                                            │  │   │
│  │  │    - Analytics: NO                                              │  │   │
│  │  │    - CRM: NO                                                    │  │   │
│  │  └─────────────────────────────┬───────────────────────────────────┘  │   │
│  │                                │                                      │   │
│  │                                ▼                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │  NODE 2: ROUTER                                                 │  │   │
│  │  │                                                                 │  │   │
│  │  │  Based on classification, route to tools:                       │  │   │
│  │  │  → customer_context_tool (for Kevin + Arizona)                  │  │   │
│  │  │  → rag_search_tool (for "roof leak")                            │  │   │
│  │  └─────────────────────────────┬───────────────────────────────────┘  │   │
│  └────────────────────────────────┼──────────────────────────────────────┘   │
│                                   │                                         │
│                 ┌─────────────────┴─────────────────┐                       │
│                 │ PARALLEL TOOL EXECUTION            │                       │
│                 │                                    │                       │
│                 ▼                                    ▼                       │
│  ┌──────────────────────────┐         ┌──────────────────────────┐          │
│  │  TOOL 1:                 │         │  TOOL 2:                 │          │
│  │  CUSTOMER CONTEXT        │         │  RAG MULTI-SOURCE        │          │
│  │                          │         │  SEARCH                  │          │
│  │  1. Fuzzy name match     │         │                          │          │
│  │     "Kevin" + "Arizona"  │         │  1. Generate embedding   │          │
│  │                          │         │     for query            │          │
│  │  MongoDB Query:          │         │                          │          │
│  │  db.customers.find({     │         │  2. Milvus search:       │          │
│  │    company_id: "...",    │         │     Filter:              │          │
│  │    $text: {              │         │     • tenant_id          │          │
│  │      $search: "Kevin"    │         │     • corpus_type IN     │          │
│  │    },                    │         │       ["call_summary",   │          │
│  │    $or: [                │         │        "chunk_summary"]  │          │
│  │      {phone: ~/^.*AZ/},  │         │     Top K: 5             │          │
│  │      {address: ~/Arizona/}]       │         │                          │          │
│  │  })                      │         │  3. Retrieve:            │          │
│  │                          │         │     • Summary JSON       │          │
│  │  Result:                 │         │     • Call metadata      │          │
│  │  {                       │         │     • Customer phone     │          │
│  │    customer_id: "...",   │         │                          │          │
│  │    name: "Kevin",        │         │  Result:                 │          │
│  │    phone: "+14805551234",│         │  [                       │          │
│  │    address: "Arizona",   │         │    {                     │          │
│  │    total_calls: 5,       │         │      call_id: "5002",    │          │
│  │    last_call: "...",     │         │      score: 0.92,        │          │
│  │    status: "warm"        │         │      summary: {...},     │          │
│  │  }                       │         │      phone: "+1480..."   │          │
│  │                          │         │    },                    │          │
│  │  2. Fetch call history:  │         │    ...                   │          │
│  │  db.calls.find({         │         │  ]                       │          │
│  │    customer_id: "...",   │         │                          │          │
│  │    company_id: "..."     │         │  4. Load full summaries  │          │
│  │  }).sort({               │         │     from MongoDB:        │          │
│  │    call_date: -1         │         │     db.call_summaries    │          │
│  │  }).limit(5)             │         │     .find({              │          │
│  │                          │         │       call_id: {$in: []} │          │
│  │  3. Cache result:        │         │     })                   │          │
│  │  Redis TTL: 5 min        │         │                          │          │
│  └─────────┬────────────────┘         └─────────┬────────────────┘          │
│            │                                    │                            │
│            └────────────────┬───────────────────┘                            │
│                             │                                                │
│                             ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                  NODE 3: CONTEXT MERGER                              │   │
│  │                                                                      │   │
│  │  Merge all retrieved data into unified context:                     │   │
│  │                                                                      │   │
│  │  Context Object:                                                     │   │
│  │  {                                                                   │   │
│  │    "customer_profile": {                                             │   │
│  │      "name": "Kevin",                                                │   │
│  │      "phone": "+14805551234",                                        │   │
│  │      "location": "Arizona",                                          │   │
│  │      "status": "warm",                                               │   │
│  │      "total_calls": 5,                                               │   │
│  │      "last_call_date": "2026-01-08"                                  │   │
│  │    },                                                                │   │
│  │    "call_summaries": [                                               │   │
│  │      {                                                               │   │
│  │        "call_id": "5002",                                            │   │
│  │        "date": "2026-01-08",                                         │   │
│  │        "summary": "Kevin called about leaking flat roof...",         │   │
│  │        "key_points": [...],                                          │   │
│  │        "objections": [                                               │   │
│  │          {                                                           │   │
│  │            "category": "Timing",                                     │   │
│  │            "text": "7 to 9 weeks is too long"                        │   │
│  │          }                                                           │   │
│  │        ],                                                            │   │
│  │        "qualification": {...}                                        │   │
│  │      }                                                               │   │
│  │    ],                                                                │   │
│  │    "conversation_history": [                                         │   │
│  │      {role: "user", content: "Previous Q"},                          │   │
│  │      {role: "assistant", content: "Previous A"}                      │   │
│  │    ]                                                                 │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              NODE 4: RESPONSE SYNTHESIZER                            │   │
│  │                                                                      │   │
│  │  LLM generates response with:                                        │   │
│  │  • Full context from merger                                          │   │
│  │  • Conversation history                                              │   │
│  │  • Instructions to cite sources                                      │   │
│  │  • Instructions for follow-up suggestions                            │   │
│  │                                                                      │   │
│  │  Prompt Template:                                                    │   │
│  │  """                                                                 │   │
│  │  You are Otto, an AI sales assistant.                                │   │
│  │                                                                      │   │
│  │  Conversation History:                                               │   │
│  │  {conversation_history}                                              │   │
│  │                                                                      │   │
│  │  Retrieved Context:                                                  │   │
│  │  {merged_context}                                                    │   │
│  │                                                                      │   │
│  │  User Question:                                                      │   │
│  │  {user_message}                                                      │   │
│  │                                                                      │   │
│  │  Instructions:                                                       │   │
│  │  1. Answer based ONLY on retrieved context                           │   │
│  │  2. Cite specific call IDs as sources                                │   │
│  │  3. If info not found, say "I don't have that information"           │   │
│  │  4. Suggest 2-3 relevant follow-up questions                         │   │
│  │  """                                                                 │   │
│  │                                                                      │   │
│  │  LLM Response:                                                       │   │
│  │  "Kevin from Arizona called about a leaking flat roof over his       │   │
│  │  patio (Call #5002). The roof was built in 2006. He was concerned    │   │
│  │  about the 7-9 week timeline for repairs. Travis suggested he        │   │
│  │  consider hiring a local roofing handyman for faster service."       │   │
│  │                                                                      │   │
│  │  Extract Sources:                                                    │   │
│  │  - Call #5002 mentioned in response → Add to sources                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   STEP 3: STORE & RESPOND                            │   │
│  │                                                                      │   │
│  │  1. Store user message in MongoDB:                                   │   │
│  │     db.ask_otto_messages.insertOne({                                 │   │
│  │       conversation_id: "conv_abc123",                                │   │
│  │       role: "user",                                                  │   │
│  │       content: "What did Kevin...",                                  │   │
│  │       created_at: ISODate(...)                                       │   │
│  │     })                                                               │   │
│  │                                                                      │   │
│  │  2. Store assistant response in MongoDB:                             │   │
│  │     db.ask_otto_messages.insertOne({                                 │   │
│  │       conversation_id: "conv_abc123",                                │   │
│  │       role: "assistant",                                             │   │
│  │       content: "Kevin from Arizona...",                              │   │
│  │       sources: [                                                     │   │
│  │         {type: "call_summary", call_id: "5002", confidence: 0.95}    │   │
│  │       ],                                                             │   │
│  │       metadata: {                                                    │   │
│  │         customer_id: "cust_123",                                     │   │
│  │         tokens_used: 850                                             │   │
│  │       },                                                             │   │
│  │       created_at: ISODate(...)                                       │   │
│  │     })                                                               │   │
│  │                                                                      │   │
│  │  3. Update conversation context in Redis (sliding window)            │   │
│  │                                                                      │   │
│  │  4. Return API response                                              │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        API RESPONSE                                  │   │
│  │                                                                      │   │
│  │  Response (200 OK):                                                  │   │
│  │  {                                                                   │   │
│  │    "conversation_id": "conv_abc123",                                 │   │
│  │    "message_id": "msg_xyz789",                                       │   │
│  │    "answer": "Kevin from Arizona called about a leaking flat roof...",│  │
│  │    "sources": [                                                      │   │
│  │      {                                                               │   │
│  │        "type": "call_summary",                                       │   │
│  │        "call_id": "5002",                                            │   │
│  │        "date": "2026-01-08",                                         │   │
│  │        "confidence": 0.95,                                           │   │
│  │        "url": "/api/v1/call-processing/summary/5002"                 │   │
│  │      }                                                               │   │
│  │    ],                                                                │   │
│  │    "customer_context": {                                             │   │
│  │      "customer_id": "cust_123",                                      │   │
│  │      "name": "Kevin",                                                │   │
│  │      "phone": "+14805551234"                                         │   │
│  │    },                                                                │   │
│  │    "suggested_follow_ups": [                                         │   │
│  │      "What objections did Kevin raise?",                             │   │
│  │      "Did Kevin book an appointment?",                               │   │
│  │      "What was Kevin's qualification status?"                        │   │
│  │    ],                                                                │   │
│  │    "created_at": "2026-01-08T10:30:25Z",                             │   │
│  │    "tokens_used": 850                                                │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Create Conversation

**Endpoint:** `POST /api/v1/ask-otto/conversations`

**Description:** Create a new conversation session.

**Request Headers:**
```http
X-API-Key: {api_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "company_id": "acme_roofing",
  "user_id": "user_123",
  "metadata": {
    "source": "dashboard",
    "user_name": "Manager John",
    "department": "sales"
  }
}
```

**Response (201 Created):**
```json
{
  "conversation_id": "conv_abc123def456",
  "company_id": "acme_roofing",
  "user_id": "user_123",
  "created_at": "2026-01-08T10:30:00Z",
  "message_count": 0,
  "expires_at": "2026-01-09T10:30:00Z"
}
```

---

### 2. Send Message

**Endpoint:** `POST /api/v1/ask-otto/conversations/{conversation_id}/messages`

**Description:** Send a message to Ask Otto and receive an AI-generated response.

**Request Headers:**
```http
X-API-Key: {api_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "message": "What did Kevin from Arizona say about the roof leak timeline?",
  "context": {
    "include_customer_context": true,
    "include_call_history": true,
    "max_rag_results": 5,
    "search_filters": {
      "date_range": {
        "start": "2026-01-01",
        "end": "2026-01-08"
      },
      "qualification_status": ["warm", "hot"]
    }
  },
  "options": {
    "stream": false,
    "include_sources": true,
    "suggest_follow_ups": true
  }
}
```

**Response (200 OK):**
```json
{
  "conversation_id": "conv_abc123def456",
  "message_id": "msg_xyz789abc123",
  "answer": "Kevin from Arizona called about a leaking flat roof over his patio (Call #5002). The roof was built in 2006 and had solar panels installed, but the leak is not related to the solar installation. Kevin was concerned about the 7-9 week timeline for repairs. Travis, the customer rep, informed him that this was the soonest they could complete the repair due to high volume. Travis suggested Kevin consider hiring a local roofing handyman if he needed the issue resolved sooner.",
  "sources": [
    {
      "type": "call_summary",
      "call_id": "5002",
      "date": "2026-01-08T10:15:00Z",
      "confidence": 0.95,
      "excerpt": "Kevin called about leaking flat roof...",
      "url": "/api/v1/call-processing/summary/5002"
    },
    {
      "type": "chunk_summary",
      "chunk_id": "c_5002_2",
      "call_id": "5002",
      "confidence": 0.88,
      "excerpt": "7-9 week timeline discussion...",
      "url": "/api/v1/call-processing/chunks/5002"
    }
  ],
  "customer_context": {
    "customer_id": "cust_123",
    "name": "Kevin",
    "phone": "+14805551234",
    "location": "Arizona",
    "qualification_status": "warm",
    "total_calls": 5,
    "last_call_date": "2026-01-08"
  },
  "suggested_follow_ups": [
    "What objections did Kevin raise?",
    "Did Kevin book an appointment?",
    "What was Kevin's qualification status?",
    "Has Travis followed up with Kevin?"
  ],
  "metadata": {
    "tokens_used": 850,
    "response_time_ms": 1250,
    "rag_results_count": 2,
    "customer_context_found": true
  },
  "created_at": "2026-01-08T10:30:25Z"
}
```

---

### 3. Get Conversation History

**Endpoint:** `GET /api/v1/ask-otto/conversations/{conversation_id}/messages`

**Description:** Retrieve conversation message history.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Query Parameters:**
- `limit` (optional): Maximum messages to return (default 50, max 200)
- `before` (optional): Return messages before this message_id (pagination)

**Response (200 OK):**
```json
{
  "conversation_id": "conv_abc123def456",
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "content": "What calls did we have this week?",
      "created_at": "2026-01-08T10:25:00Z"
    },
    {
      "message_id": "msg_002",
      "role": "assistant",
      "content": "This week, you had 145 total calls...",
      "sources": [...],
      "created_at": "2026-01-08T10:25:15Z"
    },
    {
      "message_id": "msg_003",
      "role": "user",
      "content": "What did Kevin from Arizona say about the roof leak timeline?",
      "created_at": "2026-01-08T10:30:20Z"
    },
    {
      "message_id": "msg_004",
      "role": "assistant",
      "content": "Kevin from Arizona called about a leaking flat roof...",
      "sources": [...],
      "created_at": "2026-01-08T10:30:25Z"
    }
  ],
  "total_messages": 4,
  "has_more": false
}
```

---

### 4. Delete Conversation

**Endpoint:** `DELETE /api/v1/ask-otto/conversations/{conversation_id}`

**Description:** Delete a conversation and all its messages.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (204 No Content)**

---

### 5. Get Conversation Details

**Endpoint:** `GET /api/v1/ask-otto/conversations/{conversation_id}`

**Description:** Get conversation metadata without messages.

**Response (200 OK):**
```json
{
  "conversation_id": "conv_abc123def456",
  "company_id": "acme_roofing",
  "user_id": "user_123",
  "created_at": "2026-01-08T10:30:00Z",
  "updated_at": "2026-01-08T10:35:00Z",
  "message_count": 4,
  "expires_at": "2026-01-09T10:30:00Z",
  "metadata": {
    "source": "dashboard",
    "user_name": "Manager John"
  }
}
```

---

## MongoDB Collections

### Collection: `ask_otto_conversations`

```javascript
{
  _id: ObjectId("..."),
  conversation_id: "conv_abc123def456",
  company_id: "acme_roofing",
  user_id: "user_123",
  created_at: ISODate("2026-01-08T10:30:00Z"),
  updated_at: ISODate("2026-01-08T10:35:00Z"),
  expires_at: ISODate("2026-01-09T10:30:00Z"),
  message_count: 4,
  metadata: {
    source: "dashboard",
    user_name: "Manager John",
    department: "sales"
  }
}
```

**Indexes:**
- `conversation_id` (unique)
- `{company_id: 1, user_id: 1, created_at: -1}`
- `expires_at` (TTL index, auto-delete after expiry)

---

### Collection: `ask_otto_messages`

```javascript
{
  _id: ObjectId("..."),
  message_id: "msg_xyz789abc123",
  conversation_id: "conv_abc123def456",
  role: "assistant",  // "user" | "assistant"
  content: "Kevin from Arizona called about a leaking flat roof...",
  sources: [
    {
      type: "call_summary",
      call_id: "5002",
      confidence: 0.95,
      url: "/api/v1/call-processing/summary/5002"
    }
  ],
  customer_context: {
    customer_id: "cust_123",
    name: "Kevin",
    phone: "+14805551234"
  },
  metadata: {
    tokens_used: 850,
    response_time_ms: 1250,
    rag_results_count: 2
  },
  created_at: ISODate("2026-01-08T10:30:25Z")
}
```

**Indexes:**
- `message_id` (unique)
- `{conversation_id: 1, created_at: 1}`
- `{conversation_id: 1, role: 1}`

---

## Redis Cache Structure

### Dual-Write Caching Pattern

The implementation uses a **dual-write pattern** for high availability:

```
┌─────────────┐      ┌─────────────┐
│  Write      │ ───► │  MongoDB    │ (Source of truth)
│  Operation  │      └─────────────┘
│             │      ┌─────────────┐
│             │ ───► │   Redis     │ (Cache)
└─────────────┘      └─────────────┘

┌─────────────┐      ┌─────────────┐
│  Read       │ ───► │   Redis     │ (Cache hit)
│  Operation  │      └──────┬──────┘
│             │             │ miss
│             │      ┌──────▼──────┐
│             │      │  MongoDB    │ ──► Repopulate cache
└─────────────┘      └─────────────┘
```

### Conversation Cache

```
Key: ask_otto:conversation:{conversation_id}
Value: {
  "conversation_id": "conv_abc123",
  "company_id": "acme_roofing",
  "user_id": "user_123",
  "created_at": "2026-01-08T10:30:00Z",
  "message_count": 4
}
TTL: 3600 seconds (1 hour)
```

### Conversation History Cache

```
Key: ask_otto:history:{conversation_id}
Value: [
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."},
  ...  // Last 10 messages (sliding window)
]
TTL: 300 seconds (5 minutes)
```

### Embedding Cache

```
Key: embedding:{model_name}:{md5_hash}
Value: [0.123, 0.456, ...]  // 384-dimension vector
TTL: 3600 seconds (1 hour)
```

### Cache Invalidation

- **Conversation cache**: Invalidated on message add (deleted, rebuilt on next read)
- **History cache**: Appended on new messages, keeps last 10
- **Embedding cache**: No invalidation (content-addressable)

---

## Orchestration Implementation

### Sequential Pipeline (LangGraphService)

The implementation uses a **simplified sequential pipeline** rather than the full LangGraph library for reliability and ease of debugging:

```python
# app/services/ask_otto/langgraph_service.py

class LangGraphService:
    """
    Sequential orchestration pipeline for Ask Otto.
    
    NOT using LangGraph library - uses simplified sequential processing:
    1. Query classification (LLM)
    2. SOP detection (keyword-based)
    3. RAG search (conditional)
    4. SOP metrics lookup (conditional)
    5. Customer context lookup (conditional)
    6. Response synthesis (LLM)
    7. Source extraction
    8. Follow-up generation (rule-based)
    """
    
    async def process_query(
        self,
        conversation_id: str,
        message: str,
        company_id: str,
        conversation_history: List[Dict],
        context_options: Dict
    ) -> Dict:
        """Main orchestration method."""
        
        # Step 1: Classify query and extract entities
        classification = await self._classify_query(message)
        # Returns: customer_name, phone_number, location, topic
        
        # Step 2: Check if SOP-related query
        is_sop_query = self._is_sop_related_query(message)
        
        # Step 3: RAG search (conditional)
        rag_results = []
        if context_options.get("include_call_history") or is_sop_query:
            corpus_types = self._get_corpus_types(is_sop_query)
            rag_results = await self.rag_service.search(
                query=message,
                company_id=company_id,
                corpus_types=corpus_types,
                limit=context_options.get("max_rag_results", 5)
            )
        
        # Step 4: SOP metrics lookup (if evaluation query)
        sop_metrics = None
        if is_sop_query and self._is_evaluation_query(message):
            sop_metrics = await self.sop_service.get_sop_metrics(company_id)
        
        # Step 5: Customer context lookup (conditional)
        customer_context = None
        if classification.get("customer_name") or classification.get("phone_number"):
            customer_context = await self.customer_service.get_context(
                company_id=company_id,
                entities=classification
            )
        
        # Step 6: Synthesize response
        answer = await self._synthesize_response(
            message=message,
            conversation_history=conversation_history,
            rag_results=rag_results,
            customer_context=customer_context,
            sop_metrics=sop_metrics
        )
        
        # Step 7: Extract sources
        sources = self._extract_sources(rag_results)
        
        # Step 8: Generate follow-ups (rule-based)
        follow_ups = self._generate_follow_ups(
            customer_context=customer_context,
            rag_results=rag_results
        )
        
        return {
            "answer": answer,
            "sources": sources,
            "customer_context": customer_context,
            "suggested_follow_ups": follow_ups
        }
```

### Query Classification

```python
async def _classify_query(self, message: str) -> Dict:
    """
    LLM-based entity extraction (not rule-based).
    
    Returns:
        customer_name: Optional[str]
        phone_number: Optional[str]
        location: Optional[str]
        topic: Optional[str]
    """
    prompt = f"""
    Extract entities from this query:
    "{message}"
    
    Return JSON:
    {{
        "customer_name": "name or null",
        "phone_number": "phone or null",
        "location": "location or null",
        "topic": "main topic"
    }}
    """
    
    response = await self.llm_client.chat.completions.create(
        model=self.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)
```

### SOP Query Detection

```python
def _is_sop_related_query(self, message: str) -> bool:
    """
    Keyword-based detection for SOP-related queries.
    """
    sop_keywords = [
        "sop", "procedure", "guideline", "protocol", "process",
        "how should", "what should", "best practice", "standard",
        "metric", "evaluation", "compliance", "performance"
    ]
    
    message_lower = message.lower()
    return any(kw in message_lower for kw in sop_keywords)


def _get_corpus_types(self, is_sop_query: bool) -> List[str]:
    """Get corpus types based on query type."""
    if is_sop_query:
        return ["sop_document", "sop_metric", "sop_criteria", "call_summary"]
    return ["call_summary", "chunk_summary"]
```

---

## RAG Search Strategy

### Multi-Corpus Search

```python
def multi_source_rag_search(query: str, company_id: str, max_results: int = 5):
    """
    Search across multiple corpus types with priority weighting.
    """
    # Generate embedding using local HuggingFace Sentence Transformers
    embedding = embedding_service.get_embedding(query)  # Local model, fast
    
    # Search Milvus with corpus type priority
    results = []
    
    # Priority 1: Call summaries (highest relevance)
    call_summaries = milvus.search(
        collection_name="otto_intelligence_v1",
        data=[embedding],
        filter=f"tenant_id == '{company_id}' && corpus_type == 'call_summary'",
        limit=3,
        output_fields=["doc_id", "text_content", "summary_json", "customer_phone"]
    )
    results.extend([(r, "call_summary", r.score) for r in call_summaries[0]])
    
    # Priority 2: Chunk summaries
    chunk_summaries = milvus.search(
        collection_name="otto_intelligence_v1",
        data=[embedding],
        filter=f"tenant_id == '{company_id}' && corpus_type == 'chunk_summary'",
        limit=2,
        output_fields=["doc_id", "chunk_id", "text_content", "summary_json"]
    )
    results.extend([(r, "chunk_summary", r.score) for r in chunk_summaries[0]])
    
    # Priority 3: FAQ documents
    faq_docs = milvus.search(
        collection_name="otto_intelligence_v1",
        data=[embedding],
        filter=f"tenant_id == '{company_id}' && corpus_type == 'faq'",
        limit=1,
        output_fields=["doc_id", "text_content"]
    )
    results.extend([(r, "faq", r.score) for r in faq_docs[0]])
    
    # Sort by score and return top K
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:max_results]
```

---

## Customer Context Resolution

### Fuzzy Matching Algorithm

```python
def resolve_customer_by_name_and_location(
    name: str,
    location: Optional[str],
    company_id: str
) -> Optional[Dict]:
    """
    Resolve customer using fuzzy name matching + location hints.
    """
    # Check Redis cache first
    cache_key = f"customer_fuzzy:{company_id}:{name}:{location}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # MongoDB query with text search + location filter
    query = {
        "company_id": company_id,
        "$text": {"$search": name}
    }
    
    if location:
        query["$or"] = [
            {"address": {"$regex": location, "$options": "i"}},
            {"state": location},
            {"city": location}
        ]
    
    # Find best match
    customers = db.customers.find(query).limit(5)
    
    if not customers:
        return None
    
    # Rank by text score + location match
    best_match = max(
        customers,
        key=lambda c: fuzzy_score(c["name"], name) +
                     (0.3 if location_matches(c, location) else 0)
    )
    
    # Cache result
    redis.setex(cache_key, 300, json.dumps(best_match))
    
    return best_match
```

---

## Performance Optimizations

### 1. Parallel Tool Execution
- LangGraph executes customer_context, rag_search, analytics, and crm nodes in parallel
- Reduces latency from ~6s sequential to ~2s parallel

### 2. Conversation Context Caching
- Cache last 10 messages in Redis (30-minute TTL)
- Avoid MongoDB query on every request
- Invalidate on new message

### 3. RAG Query Caching
- Cache semantic search results by query hash
- 5-minute TTL (balance freshness vs speed)
- Invalidate on new call processing

### 4. Customer Context Caching
- Cache customer lookups by phone (5-minute TTL)
- Pre-warm cache for active customers
- Background refresh for frequently accessed customers

### 5. Embedding Caching
- Cache embeddings for common queries
- Reuse embeddings across similar queries
- Store in Redis with 1-hour TTL

---

## Success Metrics

| Metric | Target | Monitoring |
|--------|--------|------------|
| Response time (p95) | < 3s | HTTP middleware timer |
| RAG search latency | < 300ms | Milvus client timer |
| Customer context resolution | < 200ms | Service-level timer |
| Context cache hit rate | > 70% | Redis cache stats |
| Answer relevance score | > 0.85 | User feedback / LLM eval |
| Source citation accuracy | > 90% | Manual audit sample |

---

## CRM Placeholder Design

### Future Integration Interface

```python
class CRMIntegrationService:
    """
    Placeholder for future CRM integrations.
    
    Supported CRMs (planned):
    - Salesforce
    - HubSpot
    - Pipedrive
    - Custom CRM via webhook
    """
    
    async def get_customer_by_phone(
        self,
        phone: str,
        company_id: str
    ) -> Optional[Dict]:
        """
        Fetch customer from external CRM.
        
        Returns:
            {
                "crm_id": "SF_123456",
                "name": "Kevin",
                "email": "kevin@example.com",
                "status": "warm",
                "owner": "sales_rep_id",
                "last_activity": "2026-01-08",
                "custom_fields": {...}
            }
        """
        raise NotImplementedError("CRM integration not yet implemented")
    
    async def sync_call_summary(
        self,
        call_id: str,
        crm_customer_id: str,
        summary: Dict
    ) -> bool:
        """
        Push call summary to CRM as activity/note.
        """
        raise NotImplementedError("CRM integration not yet implemented")
```

### Configuration

```python
# Environment variables for CRM
CRM_PROVIDER = "none"  # "salesforce" | "hubspot" | "pipedrive" | "webhook" | "none"
CRM_API_KEY = ""
CRM_API_URL = ""
CRM_WEBHOOK_SECRET = ""
```

---

## Summary (v4.0)

### Architecture Highlights

| Component | Implementation |
|-----------|---------------|
| **Orchestration** | Sequential pipeline (not LangGraph) |
| **RAG Search** | Multi-corpus (calls, chunks, SOP documents) |
| **LLM** | GROQ llama-3.3-70b-versatile (multi-provider) |
| **Embeddings** | Local HuggingFace (cached in Redis) |
| **Storage** | MongoDB (truth) + Redis (cache) dual-write |
| **Caching** | Conversation 1h, history 5min, embeddings 1h |

### Key Differences from Original Documentation

1. **Orchestration**: Uses simplified sequential pipeline, not LangGraph library
2. **SOP Integration**: Full SOP document/metric/criteria search
3. **Dual-Write Pattern**: MongoDB + Redis simultaneously
4. **Response Metadata**: Tracks response_time_ms, rag_results_count
5. **Follow-ups**: Rule-based (not LLM-based)
6. **24-hour Expiry**: Conversations auto-expire

### File Structure

```
app/
├── api/v1/
│   └── ask_otto.py                    # API endpoints (5 endpoints)
│
├── services/ask_otto/
│   ├── __init__.py
│   ├── conversation_service.py        # Conversation + message storage
│   ├── customer_context_service.py    # Customer lookup + history
│   ├── langgraph_service.py           # Sequential pipeline orchestration
│   ├── rag_search_service.py          # Multi-corpus RAG wrapper
│   └── graph/
│       └── __init__.py                # (Placeholder, not used)
│
├── models/
│   └── conversation.py                # MongoDB models
│
└── schemas/
    └── ask_otto.py                    # Pydantic request/response
```

---

**Next:** [Feature 4: SOP Document Ingestion](./ARCHITECTURE_FEATURE_4_DOCUMENT_INGESTION.md)