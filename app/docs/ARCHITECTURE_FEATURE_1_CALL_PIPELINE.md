# Feature 1: Enhanced Call Processing Pipeline API

**Version:** 4.0  
**Date:** February 4, 2026  
**Service:** Independent Microservice Architecture  
**Implementation:** FastAPI BackgroundTasks (No Celery)

> **Last Updated:** February 2026 - Major enhancements including parallel extraction architecture, multi-stage objection validation, hybrid diarization with timestamp alignment, and tenant configuration integration.

---

## Overview

The Call Processing Pipeline transforms incoming call audio into structured intelligence through a streaming API-driven workflow. This feature provides REST APIs for audio submission, processing status tracking, and retrieval of structured summaries.

**Key Implementation Note**: This feature uses **FastAPI BackgroundTasks** for async processing instead of Celery workers, simplifying deployment to a single process architecture with APScheduler for scheduled jobs.

### Key Enhancements (v4.0)

| Enhancement | Description |
|-------------|-------------|
| **Parallel Extraction** | 4 specialized extractors (Summary, Compliance, Objection, Qualification) run in parallel per chunk |
| **Multi-Stage Objection Detection** | 7-stage pipeline with programmatic validation to prevent hallucinations |
| **Hybrid Diarization** | Combines LLM speaker accuracy with API timestamp precision |
| **Tenant Configuration** | Per-company customization of qualification rules and processing options |
| **Customer Intelligence** | Detects existing customers, call types, and enriches with history |
| **Property Details Extraction** | Extracts home services context (roof type, HOA, solar, etc.) |
| **Phase Detection v1.2** | Hybrid alignment algorithm for accurate phase timestamps |
| **Lead Scoring Integration** | BANT-based scoring calculated during post-processing |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CALL PROCESSING PIPELINE - v4.0 ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │    POST /api/v1/call-processing/process (202 Accepted)                   │   │
│  │    • Validates metadata.agent.id/name (or legacy rep_id/rep_name)       │   │
│  │    • Duplicate prevention: rejects if call_id exists (allow_reprocess)  │   │
│  │    • Stores initial status in Redis (24h TTL)                           │   │
│  └────────────────────────────────┬────────────────────────────────────────┘   │
│                                   │                                             │
│                                   ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    FASTAPI BACKGROUND TASK                               │   │
│  │                    (No Celery - single process)                          │   │
│  └────────────────────────────────┬────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 1: INITIALIZE (5%)        │                                         │   │
│  │ • Load tenant configuration    │                                         │   │
│  │ • Validate company settings    │                                         │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 2: DOWNLOAD AUDIO (10%)   │                                         │   │
│  │ • S3/HTTP/Local file support   │                                         │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 3: TRANSCRIBE (20%)       ▼                                         │   │
│  │ ┌─────────────────────────────────────────────────────────────────────┐ │   │
│  │ │              HYBRID DIARIZATION (New v4.0)                          │ │   │
│  │ │                                                                      │ │   │
│  │ │  Provider: Shunya API (primary) / AssemblyAI (fallback)            │ │   │
│  │ │                                                                      │ │   │
│  │ │  DIARIZATION_PRIORITY options:                                      │ │   │
│  │ │  • "llm": Get timestamps from API → Apply LLM diarization          │ │   │
│  │ │  • "api": Use API diarization → Verify/enhance with LLM            │ │   │
│  │ │                                                                      │ │   │
│  │ │  Speaker Labeling: SPEAKER_00/01 → customer_rep/home_owner         │ │   │
│  │ │  Segment Splitting: Splits clubbed API segments aggressively       │ │   │
│  │ │                                                                      │ │   │
│  │ │  Output: segments (labeled) + segments_with_timestamps (API)       │ │   │
│  │ └─────────────────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────┬────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 4: CHUNK (40%)            ▼                                         │   │
│  │ • Semantic speaker-aware chunking (preferred)                           │   │
│  │ • Max: 120K tokens, Overlap: 200 tokens                                 │   │
│  │ • Groups segments by speaker turns when diarization available          │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 5: CUSTOMER CONTEXT (45%) │                                         │   │
│  │ • Get customer history from MongoDB                                     │   │
│  │ • Detect call type (fresh_sales, follow_up, confirmation, etc.)        │   │
│  │ • Track sentiment across calls                                          │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 6: PARALLEL EXTRACTION (50%)                                        │   │
│  │                                ▼                                         │   │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │   │
│  │  │              4 SPECIALIZED EXTRACTORS (IN PARALLEL)                │ │   │
│  │  │                                                                     │ │   │
│  │  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌─────────┐│ │   │
│  │  │  │ SUMMARY       │ │ COMPLIANCE    │ │ OBJECTION     │ │QUALIFIC-││ │   │
│  │  │  │ EXTRACTOR     │ │ EXTRACTOR     │ │ EXTRACTOR     │ │ATION    ││ │   │
│  │  │  │               │ │               │ │               │ │         ││ │   │
│  │  │  │ • Narrative   │ │ • SOP eval    │ │ • 7-STAGE     │ │• 4 LLM  ││ │   │
│  │  │  │ • Key points  │ │ • Stage check │ │   PIPELINE    │ │  calls  ││ │   │
│  │  │  │ • Actions     │ │ • Specificity │ │   (prevents   │ │• BANT   ││ │   │
│  │  │  │ • Sentiment   │ │ • Call-type   │ │   hallucin.)  │ │• Appt   ││ │   │
│  │  │  │ • Pending     │ │   aware       │ │               │ │• Address││ │   │
│  │  │  └───────────────┘ └───────────────┘ └───────────────┘ └─────────┘│ │   │
│  │  │                                                                     │ │   │
│  │  │  Objection 7-Stage Pipeline:                                       │ │   │
│  │  │  1. Extract candidates  2. Classify  3. Validate transcript        │ │   │
│  │  │  4. Calculate confidence (programmatic) 5. Business filters        │ │   │
│  │  │  6. Speaker validation (LLM) 7. Semantic cross-validation          │ │   │
│  │  │                                                                     │ │   │
│  │  │  Qualification 4-Call Structure:                                   │ │   │
│  │  │  Call 1: Core (BANT, status, booking)                              │ │   │
│  │  │  Call 2: Appointment details                                       │ │   │
│  │  │  Call 3: Customer intelligence (address, DMs, is_existing)         │ │   │
│  │  │  Call 4: Property details (roof, HOA, solar, pets)                 │ │   │
│  │  └────────────────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────┬────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 7: POST-PROCESS (55%)     │                                         │   │
│  │ • Apply tenant-specific qualification rules                             │   │
│  │ • Merge customer history data                                           │   │
│  │ • BANT score adjustment from extracted signals                          │   │
│  │ • Customer name validation (prevents rep/customer confusion)            │   │
│  │ • Follow-up reason validation                                           │   │
│  │ • Action item validation (removes hallucinated actions)                 │   │
│  │ • Calculate LEAD SCORE (BANT-based with breakdown)                      │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 8: RAG INDEX (70%)        │                                         │   │
│  │ • Embeddings: HuggingFace all-MiniLM-L6-v2 (384 dim)                    │   │
│  │ • Index call + chunk summaries in Milvus                                │   │
│  │ • Metadata: sentiment, qualification_status, booking_status             │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 9: STORE DATABASE (90%)   │                                         │   │
│  │ • calls: transcript, segments, segments_with_timestamps, metadata       │   │
│  │ • call_summaries: summary, compliance, objections, qualification        │   │
│  │ • chunk_summaries: LLM-generated summaries (not raw text)               │   │
│  └────────────────────────────────┼────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 10: PHASE DETECTION (95%) │   NON-CRITICAL                         │   │
│  │                                ▼                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│   │
│  │  │              PHASE DETECTION v1.2 (Hybrid Alignment)                ││   │
│  │  │                                                                      ││   │
│  │  │  6 Core Phases:                                                     ││   │
│  │  │  greeting → problem_discovery → qualification →                     ││   │
│  │  │  objection_handling → closing → post_close                          ││   │
│  │  │                                                                      ││   │
│  │  │  Timestamp Estimation:                                              ││   │
│  │  │  • Hybrid: Align LLM segments (accurate speakers) with              ││   │
│  │  │    API segments (accurate timestamps)                               ││   │
│  │  │  • Fallback: Word-count estimation (400ms per word)                 ││   │
│  │  │                                                                      ││   │
│  │  │  Output: Phases with quality scores, flow score, missing phases     ││   │
│  │  └─────────────────────────────────────────────────────────────────────┘│   │
│  └────────────────────────────────┬────────────────────────────────────────┘   │
│                                   │                                             │
│  ┌────────────────────────────────┼────────────────────────────────────────┐   │
│  │ STEP 11: COMPLETE (100%)       │                                         │   │
│  │ • Update job status in Redis                                            │   │
│  │ • Send webhook notification (if provided)                               │   │
│  └────────────────────────────────┴────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Submit Call for Processing

**Endpoint:** `POST /api/v1/call-processing/process`

**Description:** Submit a call audio file for processing. Returns immediately with a job ID for status tracking.

**Request Headers:**
```http
X-API-Key: {api_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "call_id": "5002",
  "company_id": "acme_roofing",
  "audio_url": "s3://otto-audio/acme_roofing/call_5002.wav",
  "phone_number": "+14805551234",
  "duration": 360,
  "call_date": "2026-01-08T10:30:00Z",
  "metadata": {
    "rep_name": "Travis",
    "customer_name": "Kevin",
    "call_type": "inbound"
  },
  "webhook_url": "https://otto-backend.com/webhooks/call-processed",
  "options": {
    "skip_rag_indexing": false,
    "skip_summary_generation": false,
    "priority": "normal"
  }
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "queued",
  "message": "Call processing initiated successfully",
  "estimated_completion_time": "2026-01-08T10:32:00Z",
  "status_url": "/api/v1/call-processing/status/job_abc123def456",
  "created_at": "2026-01-08T10:30:15Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid request body or missing required fields
- `401 Unauthorized` - Invalid or missing API key
- `409 Conflict` - Call ID already being processed
- `500 Internal Server Error` - Server error

---

### 2. Check Processing Status

**Endpoint:** `GET /api/v1/call-processing/status/{job_id}`

**Description:** Poll the processing status of a submitted call.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (200 OK) - Processing:**
```json
{
  "job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "processing",
  "progress": {
    "percent": 65,
    "current_step": "summarizing",
    "steps_completed": ["downloading", "transcribing", "chunking", "rag_indexing"],
    "steps_remaining": ["summarizing", "validation", "storage"]
  },
  "started_at": "2026-01-08T10:30:20Z",
  "updated_at": "2026-01-08T10:31:45Z",
  "estimated_completion": "2026-01-08T10:32:10Z"
}
```

**Response (200 OK) - Completed:**
```json
{
  "job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "completed",
  "progress": {
    "percent": 100,
    "current_step": "completed",
    "steps_completed": ["downloading", "transcribing", "chunking", "rag_indexing", "summarizing", "validation", "storage"]
  },
  "started_at": "2026-01-08T10:30:20Z",
  "completed_at": "2026-01-08T10:32:05Z",
  "duration_seconds": 105,
  "results": {
    "summary_url": "/api/v1/call-processing/summary/5002",
    "chunks_url": "/api/v1/call-processing/chunks/5002",
    "transcript_url": "/api/v1/call-processing/transcript/5002"
  },
  "metadata": {
    "chunks_generated": 3,
    "summaries_generated": 3,
    "vectors_indexed": 4,
    "transcript_words": 1245,
    "transcript_duration": 360
  }
}
```

**Response (200 OK) - Failed:**
```json
{
  "job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "failed",
  "progress": {
    "percent": 45,
    "current_step": "transcribing",
    "steps_completed": ["downloading"],
    "steps_failed": ["transcribing"]
  },
  "started_at": "2026-01-08T10:30:20Z",
  "failed_at": "2026-01-08T10:31:10Z",
  "error": {
    "code": "TRANSCRIPTION_FAILED",
    "message": "Failed to transcribe audio: Audio file is corrupted",
    "details": {
      "transcription_service": "shunya",
      "error_type": "InvalidAudioFormat"
    }
  },
  "retry_available": true,
  "retry_url": "/api/v1/call-processing/retry/job_abc123def456"
}
```

**Error Responses:**
- `404 Not Found` - Job ID not found
- `401 Unauthorized` - Invalid or missing API key

---

### 3. Get Call Summary

**Endpoint:** `GET /api/v1/call-processing/summary/{call_id}`

**Description:** Retrieve the structured JSON summary for a processed call.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Query Parameters:**
- `include_chunks` (boolean, default: false) - Include chunk-level summaries
- `format` (string, default: "json") - Response format: "json" | "simplified"

**Response (200 OK):**
```json
{
  "call_id": "5002",
  "company_id": "acme_roofing",
  "status": "completed",
  "processed_at": "2026-01-08T10:32:05Z",
  "summary": {
    "summary": "The customer, Kevin, called Arizona Roofers to address a leaking flat roof...",
    "key_points": [
      "Leaking flat roof over patio",
      "Built in 2006",
      "Solar panels installed, but not the cause of the leak",
      "Repair timeline: 7 to 9 weeks",
      "Alternative: hiring a local roofing handyman"
    ],
    "action_items": [
      "Schedule a repair",
      "Consider hiring a local roofing handyman"
    ],
    "next_steps": [
      "Kevin to decide on next course of action",
      "Travis to follow up if Kevin decides to proceed with Arizona Roofers"
    ],
    "pending_actions": [
      {
        "type": "follow_up_call",
        "owner": "customer_rep",
        "due_at": null,
        "raw_text": "Travis said to call back if Kevin can't find anybody and needs to get booked",
        "confidence": 0.7,
        "contact_method": "phone"
      }
    ],
    "sentiment_score": 0.6,
    "confidence_score": 0.8
  },
  "compliance": {
    "call_id": "5002",
    "target_role": "customer_rep",
    "evaluation_mode": "sop_only",
    "sop_compliance": {
      "score": 1.0,
      "compliance_rate": 1.0,
      "stages": {
        "total": 2,
        "followed": ["Intake", "Qualify"],
        "missed": []
      },
      "issues": [],
      "positive_behaviors": [
        "REP was honest and transparent about timeline constraints",
        "REP suggested helpful alternatives when unable to schedule"
      ],
      "confidence": 0.8
    },
    "timestamps": {
      "sop_evaluated_at": "2026-01-08T10:32:00Z"
    }
  },
  "objections": {
    "objections": [
      {
        "id": 548,
        "category_id": 2,
        "category_text": "Timing",
        "objection_text": "7 to 9 weeks is a long time",
        "overcome": false,
        "speaker_id": "home_owner",
        "timestamp": null,
        "confidence_score": 0.9,
        "severity": "medium",
        "response_suggestions": [],
        "created_at": "2026-01-08T10:32:01Z"
      }
    ],
    "total_count": 1
  },
  "qualification": {
    "bant_scores": {
      "need": 1.0,
      "budget": 0.0,
      "timeline": 0.9,
      "authority": 1.0
    },
    "overall_score": 0.75,
    "qualification_status": "warm",
    "booking_status": "not_booked",
    "call_outcome_category": "qualified_but_unbooked",
    "appointment_confirmed": false,
    "appointment_date": null,
    "appointment_type": null,
    "service_requested": "Flat roof repair",
    "customer_name": "Kevin",
    "customer_name_confidence": 0.9
  }
}
```

**Error Responses:**
- `404 Not Found` - Call not found or not yet processed
- `401 Unauthorized` - Invalid or missing API key

---

### 4. Get Chunk Summaries

**Endpoint:** `GET /api/v1/call-processing/chunks/{call_id}`

**Description:** Retrieve chunk-level summaries for a processed call.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (200 OK):**
```json
{
  "call_id": "5002",
  "total_chunks": 3,
  "chunks": [
    {
      "chunk_id": "c_5002_1",
      "chunk_index": 1,
      "summary": {
        "summary": "Kevin called about a leaking patio roof built in 2006...",
        "key_points": ["Initial problem description", "Roof age mentioned"],
        "objections": [],
        "sentiment_score": 0.7
      },
      "milvus_id": "vec_5002_chunk_1",
      "created_at": "2026-01-08T10:31:30Z"
    },
    {
      "chunk_id": "c_5002_2",
      "chunk_index": 2,
      "summary": {
        "summary": "Travis explained the 7-9 week timeline...",
        "key_points": ["Timeline discussion", "Alternative suggestions"],
        "objections": [
          {
            "category_text": "Timing",
            "objection_text": "7 to 9 weeks is a long time",
            "overcome": false
          }
        ],
        "sentiment_score": 0.5
      },
      "milvus_id": "vec_5002_chunk_2",
      "created_at": "2026-01-08T10:31:45Z"
    },
    {
      "chunk_id": "c_5002_3",
      "chunk_index": 3,
      "summary": {
        "summary": "Call concluded with Kevin considering options...",
        "key_points": ["Next steps discussed", "Follow-up agreement"],
        "objections": [],
        "sentiment_score": 0.6
      },
      "milvus_id": "vec_5002_chunk_3",
      "created_at": "2026-01-08T10:32:00Z"
    }
  ]
}
```

---

### 5. Retry Failed Job

**Endpoint:** `POST /api/v1/call-processing/retry/{job_id}`

**Description:** Retry a failed processing job.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_xyz789abc123",
  "original_job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "queued",
  "message": "Retry initiated successfully",
  "retry_attempt": 2,
  "status_url": "/api/v1/call-processing/status/job_xyz789abc123"
}
```

---

### 6. Get Call Phases

**Endpoint:** `GET /api/v1/call-processing/calls/{call_id}/phases`

**Description:** Retrieve conversation phase detection results for a specific call.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (200 OK):**
```json
{
  "call_id": "5002",
  "company_id": "acme_roofing",
  "phases": [
    {
      "phase": "greeting",
      "detected": true,
      "start_time": 0.0,
      "end_time": 15.5,
      "duration": 15.5,
      "quality_score": 0.85,
      "key_moments": ["Rep introduced themselves", "Asked how they can help"]
    },
    {
      "phase": "problem_discovery",
      "detected": true,
      "start_time": 15.5,
      "end_time": 120.0,
      "duration": 104.5,
      "quality_score": 0.78,
      "key_moments": ["Customer described roof damage", "Rep asked clarifying questions"]
    }
  ],
  "missing_phases": ["post_close"],
  "flow_score": 0.82,
  "dominant_phase": "problem_discovery",
  "total_duration": 325.0,
  "algorithm_version": "1.2",
  "detected_at": "2026-01-08T10:32:00Z"
}
```

---

### 7. Search Calls by Phase

**Endpoint:** `GET /api/v1/call-processing/phases/search`

**Description:** Search for calls based on phase patterns (e.g., missing phases, low quality scores).

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `missing_phase` | string | No | Filter by missing phase |
| `min_flow_score` | float | No | Minimum flow score (0-1) |
| `max_flow_score` | float | No | Maximum flow score (0-1) |
| `from_date` | datetime | No | Filter from this date |
| `to_date` | datetime | No | Filter to this date |
| `limit` | int | No | Results per page (default: 50) |
| `offset` | int | No | Pagination offset |

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "total": 23,
  "limit": 50,
  "offset": 0,
  "calls": [
    {
      "call_id": "5002",
      "flow_score": 0.65,
      "missing_phases": ["closing", "post_close"],
      "call_date": "2026-01-08T10:30:00Z"
    }
  ]
}
```

---

### 8. Get Phase Analytics

**Endpoint:** `GET /api/v1/call-processing/phases/analytics`

**Description:** Get company-wide phase detection analytics and trends.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `from_date` | datetime | No | Analysis start date |
| `to_date` | datetime | No | Analysis end date |
| `rep_id` | string | No | Filter by rep ID |

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "period": {
    "from": "2026-01-01",
    "to": "2026-01-08"
  },
  "total_calls_analyzed": 156,
  "average_flow_score": 0.78,
  "phase_distribution": {
    "greeting": {"detected_rate": 0.98, "avg_quality": 0.85},
    "problem_discovery": {"detected_rate": 0.95, "avg_quality": 0.72},
    "qualification": {"detected_rate": 0.88, "avg_quality": 0.68},
    "objection_handling": {"detected_rate": 0.45, "avg_quality": 0.62},
    "closing": {"detected_rate": 0.72, "avg_quality": 0.58},
    "post_close": {"detected_rate": 0.35, "avg_quality": 0.45}
  },
  "most_missed_phases": ["post_close", "objection_handling"],
  "trend": "improving"
}
```

---

### 9. List Call Summaries

**Endpoint:** `GET /api/v1/call-processing/summaries`

**Description:** List call summaries for a company with pagination and filters. Returns structured summaries including compliance, qualification, objections, and lead scores.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `rep_id` | string | No | Filter by rep ID |
| `status` | string | No | Filter by call status |
| `from_date` | datetime | No | Filter calls from this date |
| `to_date` | datetime | No | Filter calls until this date |
| `min_compliance_score` | float | No | Minimum compliance score (0-1) |
| `max_compliance_score` | float | No | Maximum compliance score (0-1) |
| `limit` | int | No | Results per page (default: 50, max: 200) |
| `offset` | int | No | Pagination offset |
| `sort_by` | string | No | Sort field: `created_at`, `compliance_score` |
| `sort_order` | string | No | Sort order: `asc`, `desc` |

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "total": 156,
  "limit": 50,
  "offset": 0,
  "summaries": [
    {
      "call_id": "5002",
      "summary": {
        "brief_summary": "Customer called about roof leak...",
        "sentiment_score": 0.75
      },
      "compliance": {
        "sop_compliance": {"score": 0.85, "compliance_rate": 0.85}
      },
      "qualification": {
        "overall_score": 0.72,
        "bant_scores": {"budget": 0.8, "authority": 0.9, "need": 0.7, "timeline": 0.5}
      },
      "objections": {"total_count": 2, "overcome_rate": 0.5},
      "lead_score": {"total_score": 72, "lead_band": "warm", "confidence": "high"},
      "created_at": "2026-02-03T10:30:00Z"
    }
  ]
}
```

---

### 10. List Calls

**Endpoint:** `GET /api/v1/call-processing/calls`

**Description:** List calls for a company with pagination and comprehensive filters. Returns call metadata including status, duration, rep info, and timestamps.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `call_ids` | string | No | Comma-separated list of specific call IDs |
| `rep_id` | string | No | Filter by rep ID |
| `rep_name` | string | No | Filter by rep name (partial match) |
| `status` | string | No | Filter by status: `queued`, `processing`, `completed`, `failed` |
| `phone_number` | string | No | Filter by phone number (partial match) |
| `from_date` | datetime | No | Filter calls from this date |
| `to_date` | datetime | No | Filter calls until this date |
| `min_duration` | int | No | Minimum call duration in seconds |
| `max_duration` | int | No | Maximum call duration in seconds |
| `limit` | int | No | Results per page (default: 50, max: 200) |
| `offset` | int | No | Pagination offset |
| `sort_by` | string | No | Sort field: `call_date`, `created_at`, `duration` |
| `sort_order` | string | No | Sort order: `asc`, `desc` |

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "total": 245,
  "limit": 50,
  "offset": 0,
  "calls": [
    {
      "call_id": "5002",
      "company_id": "acme_roofing",
      "status": "completed",
      "audio_url": "https://storage.example.com/calls/5002.mp3",
      "phone_number": "+14805551234",
      "rep_role": "customer_rep",
      "duration": 325,
      "call_date": "2026-02-03T10:30:00Z",
      "metadata": {
        "rep_id": "USR123",
        "rep_name": "Travis"
      }
    }
  ]
}
```

---

### 11. Get Call Detail

**Endpoint:** `GET /api/v1/call-processing/calls/{call_id}/detail`

**Description:** Get full details for a specific call including transcript and diarized segments.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_transcript` | boolean | No | Include full transcript (default: true) |
| `include_segments` | boolean | No | Include diarized segments (default: false) |

**Response (200 OK):**
```json
{
  "call_id": "5002",
  "company_id": "acme_roofing",
  "status": "completed",
  "audio_url": "https://storage.example.com/calls/5002.mp3",
  "phone_number": "+14805551234",
  "rep_role": "customer_rep",
  "duration": 325,
  "call_date": "2026-02-03T10:30:00Z",
  "transcript": "Rep: Thank you for calling...",
  "segments": [
    {
      "speaker": "Rep",
      "text": "Thank you for calling...",
      "start": 0.0,
      "end": 5.2
    }
  ],
  "metadata": {
    "rep_id": "USR123",
    "rep_name": "Travis",
    "customer_name": "Kevin"
  }
}
```

---

## MongoDB Collections

### Collection: `calls`

```javascript
{
  _id: ObjectId("..."),
  call_id: "5002",
  company_id: "acme_roofing",
  customer_id: ObjectId("..."),  // Reference to customers collection
  phone_number: "+14805551234",
  audio_url: "s3://otto-audio/acme_roofing/call_5002.wav",
  duration: 360,
  call_date: ISODate("2026-01-08T10:30:00Z"),
  status: "completed",  // "processing", "completed", "failed"
  transcript: "...",  // Full transcript text
  created_at: ISODate("2026-01-08T10:30:15Z"),
  processed_at: ISODate("2026-01-08T10:32:05Z"),
  metadata: {
    rep_name: "Travis",
    customer_name: "Kevin",
    call_type: "inbound"
  }
}
```

**Indexes:**
- `call_id` (unique)
- `company_id`
- `phone_number`
- `status`
- `created_at`

---

### Collection: `call_summaries`

```javascript
{
  _id: ObjectId("..."),
  call_id: "5002",
  company_id: "acme_roofing",
  summary: {
    summary: "...",
    key_points: [...],
    action_items: [...],
    next_steps: [...],
    pending_actions: [...],
    sentiment_score: 0.6,
    confidence_score: 0.8
  },
  compliance: {
    call_id: "5002",
    target_role: "customer_rep",
    evaluation_mode: "sop_only",
    sop_compliance: {...}
  },
  objections: {
    objections: [...],
    total_count: 1
  },
  qualification: {
    bant_scores: {...},
    qualification_status: "warm",
    booking_status: "not_booked",
    ...
  },
  milvus_id: "vec_5002_summary",  // Link to Milvus vector
  created_at: ISODate("2026-01-08T10:32:05Z")
}
```

**Indexes:**
- `call_id` (unique)
- `company_id`
- `qualification.qualification_status`
- `qualification.booking_status`
- `created_at`

---

### Collection: `chunk_summaries`

```javascript
{
  _id: ObjectId("..."),
  chunk_id: "c_5002_1",
  call_id: "5002",
  company_id: "acme_roofing",
  chunk_index: 1,
  text: "...",  // Chunk text
  summary: {
    summary: "...",
    key_points: [...],
    objections: [...],
    sentiment_score: 0.7
  },
  milvus_id: "vec_5002_chunk_1",  // Link to Milvus chunk vector
  created_at: ISODate("2026-01-08T10:31:30Z")
}
```

**Indexes:**
- `chunk_id` (unique)
- `call_id`
- `company_id`
- `chunk_index`

---

## Redis Cache Structure

### Job Status Cache

```
Key: job:{job_id}:status
Value: {
  "job_id": "job_abc123def456",
  "call_id": "5002",
  "status": "processing",
  "progress": {
    "percent": 65,
    "current_step": "summarizing",
    "steps_completed": ["downloading", "transcribing", "chunking"],
    "steps_remaining": ["summarizing", "validation"]
  },
  "started_at": "2026-01-08T10:30:20Z",
  "updated_at": "2026-01-08T10:31:45Z"
}
TTL: 86400 (24 hours)
```

### Processing Lock

```
Key: processing_lock:{call_id}
Value: "job_abc123def456"
TTL: 3600 (1 hour, prevents duplicate processing)
```

---

## LLM Models & Configuration

### Supported Providers

| Provider | Default Model | Use Cases |
|----------|---------------|-----------|
| **GROQ** (default) | `llama-3.3-70b-versatile` | All extraction, diarization, summarization |
| **OpenAI** | `gpt-4-turbo-preview` or `gpt-5.2` | Alternative provider |
| **Anthropic** | `claude-3-5-sonnet-20240620` or `claude-sonnet-4-5-20250929` | Alternative provider |

### Model Selection

```python
# Configured via environment variable
LLM_PROVIDER = "groq"  # "groq" | "openai" | "anthropic"

# Unified interface
from app.core.llm import get_llm_client, get_active_model
client = get_llm_client()
model = get_active_model()

# Anthropic adapter converts to OpenAI-compatible interface
# Token limits: max_completion_tokens for newer OpenAI, max_tokens for others
```

### Embedding Model

| Setting | Value |
|---------|-------|
| **Model** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Dimension** | 384 |
| **Device** | CUDA if available, else CPU |
| **Caching** | Redis with 1-hour TTL |
| **Batch Processing** | batch_size=32 |

```python
# Embedding cache key pattern
Key: embedding:{model_name}:{md5_hash}
TTL: 3600 seconds (1 hour)
```

---

## Milvus Zilliz Cloud Schema

### Collection: `otto_intelligence_v1`

#### Fields:
- `id` (VARCHAR 64, Primary Key): Unique vector ID
- `tenant_id` (VARCHAR 64): company_id for partitioning
- `company_id` (VARCHAR 64): Also included for filtering
- `corpus_type` (VARCHAR 32): "call_summary" | "chunk_summary"
- `doc_id` (VARCHAR 128): call_id
- `chunk_id` (VARCHAR 128): chunk identifier (if applicable)
- `text_content` (VARCHAR 65535): Original text for retrieval
- `summary_json` (JSON): Full summary JSON
- `created_at` (INT64): Unix timestamp
- `embedding` (FLOAT_VECTOR 384): HuggingFace Sentence Transformer embedding (all-MiniLM-L6-v2)

#### Dynamic Fields (Metadata):
- `customer_phone` (VARCHAR 32)
- `call_date` (VARCHAR 32)
- `sentiment` (FLOAT)
- `qualification_status` (VARCHAR 32)
- `booking_status` (VARCHAR 32)

#### Indexing Strategy:
- **Call Summaries**: Indexed with full summary JSON
- **Chunk Summaries**: Indexed with LLM-generated chunk summaries (not raw text)
- **Search**: Cosine similarity with tenant filtering

#### Partition Strategy:
- Partition by `tenant_id` (company_id)
- Each company gets isolated partition for data security

#### Index Configuration:
```python
index_params = {
    "index_type": "HNSW",
    "metric_type": "COSINE",
    "params": {
        "M": 64,
        "efConstruction": 256
    }
}

search_params = {
    "metric_type": "COSINE",
    "nprobe": 10
}
```

---

## Dynamic Chunking Algorithm

### Pseudocode:

```python
def dynamic_chunking(transcript: str, max_tokens: int = 120000):
    """
    Dynamically chunk transcript based on context window constraints.
    
    Args:
        transcript: Full call transcript
        max_tokens: Maximum tokens per chunk (default 120K for Qwen2.5)
    
    Returns:
        List of chunk objects with text and metadata
    """
    chunks = []
    overlap_tokens = 200
    reserved_summary_tokens = 4000
    reserved_output_tokens = 4000
    
    # Effective chunk size
    effective_chunk_size = max_tokens - reserved_summary_tokens - reserved_output_tokens
    
    # Tokenize transcript
    tokens = tokenize(transcript)
    
    start_idx = 0
    chunk_index = 1
    
    while start_idx < len(tokens):
        # Extract chunk with overlap
        end_idx = start_idx + effective_chunk_size
        
        if end_idx > len(tokens):
            end_idx = len(tokens)
        
        chunk_tokens = tokens[start_idx:end_idx]
        chunk_text = detokenize(chunk_tokens)
        
        # Create chunk object
        chunk = {
            "chunk_id": f"c_{call_id}_{chunk_index}",
            "chunk_index": chunk_index,
            "text": chunk_text,
            "token_count": len(chunk_tokens),
            "start_token": start_idx,
            "end_token": end_idx
        }
        
        chunks.append(chunk)
        
        # Move to next chunk with overlap
        start_idx = end_idx - overlap_tokens
        chunk_index += 1
    
    return chunks
```

---

## Rolling Summary Algorithm

The rolling summarization uses **parallel extraction with rolling context**. Each chunk is processed by 4 specialized extractors running in parallel, with each extractor receiving the previous chunk's results for context continuity.

### Architecture:

```
Chunk 1 ─────────────────────────────────────────────────────────────►
         │                                                            │
         ├─► Summary Extractor    (previous: None)     ──► summary_1  │
         ├─► Compliance Extractor (previous: None)     ──► compliance_1
         ├─► Objection Extractor  (previous: None)     ──► objections_1
         └─► Qualification Extractor (previous: None)  ──► qualification_1
                                                                      │
                                         ┌────────────────────────────┘
                                         ▼
Chunk 2 ─────────────────────────────────────────────────────────────►
         │                                                            │
         ├─► Summary Extractor    (previous: summary_1)    ──► summary_2
         ├─► Compliance Extractor (previous: compliance_1) ──► compliance_2
         ├─► Objection Extractor  (previous: objections_1) ──► objections_2
         └─► Qualification Extractor (previous: qual_1)    ──► qualification_2
                                                                      │
                                         ┌────────────────────────────┘
                                         ▼
                                    (continues for N chunks)
                                         │
                                         ▼
                              Final Summary = Last Chunk's Results
                              (contains accumulated context from all chunks)
```

### Implementation:

```python
async def generate_summary(self, chunks: List[dict], call_context: Dict) -> Tuple[Dict, List]:
    """
    Generate summary using parallel extraction and rolling summarization.
    """
    # Track previous sections for rolling context
    previous_sections = {
        "summary": None,
        "compliance": None,
        "objections": None,
        "qualification": None
    }
    
    chunk_summaries = []
    
    for i, chunk in enumerate(chunks):
        # Extract all 4 sections in PARALLEL with rolling context
        chunk_summary = await self._extract_chunk_parallel(
            chunk["text"],
            call_context,
            customer_history,
            previous_sections,
            is_first_chunk=(i == 0),
            is_last_chunk=(i == len(chunks) - 1)
        )
        
        chunk_summaries.append({
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "summary": chunk_summary
        })
        
        # Update previous sections for next iteration (rolling context)
        previous_sections = {
            "summary": chunk_summary.get("summary"),
            "compliance": chunk_summary.get("compliance"),
            "objections": chunk_summary.get("objections"),
            "qualification": chunk_summary.get("qualification")
        }
    
    # Final summary is the last chunk (contains merged info from all chunks)
    final_summary = chunk_summaries[-1]["summary"]
    
    return final_summary, chunk_summaries


async def _extract_chunk_parallel(
    self,
    chunk_text: str,
    call_context: Dict,
    customer_history: Optional[Dict],
    previous_sections: Dict,
    is_first_chunk: bool,
    is_last_chunk: bool
) -> Dict:
    """
    Extract all sections in parallel using specialized extractors.
    Each extractor receives its previous section for context continuity.
    """
    # Create extraction tasks - all run in parallel
    tasks = {
        "summary": self._extract_with_retry(
            self.summary_extractor.extract,
            chunk_text,
            call_context,
            previous_sections.get("summary")  # Rolling context
        ),
        "compliance": self._extract_with_retry(
            self.compliance_extractor.extract,
            chunk_text,
            call_context,  # Includes SOP metrics
            previous_sections.get("compliance")  # Rolling context
        ),
        "objections": self._extract_with_retry(
            self.objection_extractor.extract,
            chunk_text,
            call_context,
            previous_sections.get("objections")  # Rolling context
        ),
        "qualification": self._extract_with_retry(
            self.qualification_extractor.extract,
            chunk_text,
            call_context,
            customer_history,
            previous_sections.get("qualification")  # Rolling context
        )
    }
    
    # Execute all in parallel
    results = await asyncio.gather(
        tasks["summary"],
        tasks["compliance"],
        tasks["objections"],
        tasks["qualification"],
        return_exceptions=True
    )
    
    # Merge results into single chunk summary
    return {
        "summary": results[0],
        "compliance": results[1],
        "objections": results[2],
        "qualification": results[3]
    }
```

### Key Benefits:

| Benefit | Description |
|---------|-------------|
| **Parallelism** | 4 extractors run simultaneously per chunk (~4x faster) |
| **Context Continuity** | Each extractor sees previous chunk's results for that section |
| **Specialization** | Each extractor optimized for its domain (objections, compliance, etc.) |
| **Incremental Merging** | Information accumulates naturally through chunks |
| **Error Isolation** | One extractor failing doesn't stop others |

---

## Validation & Error Handling

### JSON Schema Validation

```python
def validate_summary_json(summary: dict) -> Tuple[bool, List[str]]:
    """
    Validate summary JSON against expected schema.
    
    Returns:
        (is_valid, errors)
    """
    errors = []
    
    # Required top-level fields
    required_fields = ["call_id", "status", "summary", "compliance", "objections", "qualification"]
    for field in required_fields:
        if field not in summary:
            errors.append(f"Missing required field: {field}")
    
    # Validate summary section
    if "summary" in summary:
        summary_fields = ["summary", "key_points", "action_items", "sentiment_score"]
        for field in summary_fields:
            if field not in summary["summary"]:
                errors.append(f"Missing summary.{field}")
    
    # Validate enums
    if "qualification" in summary:
        valid_statuses = ["hot", "warm", "cold", "unqualified"]
        if summary["qualification"].get("qualification_status") not in valid_statuses:
            errors.append(f"Invalid qualification_status")
        
        valid_booking = ["booked", "not_booked", "service_not_offered"]
        if summary["qualification"].get("booking_status") not in valid_booking:
            errors.append(f"Invalid booking_status")
    
    # Validate objection categories
    if "objections" in summary:
        valid_categories = range(1, 11)  # 1-10
        for obj in summary["objections"].get("objections", []):
            if obj.get("category_id") not in valid_categories:
                errors.append(f"Invalid objection category_id: {obj.get('category_id')}")
    
    return len(errors) == 0, errors
```

### Retry Logic

```python
def process_call_with_retry(call_id: str, max_retries: int = 3):
    """
    Process call with exponential backoff retry.
    """
    retry_delays = [1, 2, 4]  # seconds
    
    for attempt in range(max_retries):
        try:
            # Attempt processing
            result = process_call(call_id)
            
            # Validate result
            is_valid, errors = validate_summary_json(result)
            
            if is_valid:
                return result
            else:
                logger.warning(f"Validation failed (attempt {attempt + 1}): {errors}")
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                else:
                    raise ValidationError(f"Failed validation after {max_retries} attempts: {errors}")
        
        except Exception as e:
            logger.error(f"Processing error (attempt {attempt + 1}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
            else:
                raise
```

---

## Performance Optimizations

### 1. Parallel RAG Indexing
- Embed chunks in parallel (batch size 10)
- Insert to Milvus in batches
- Don't wait for RAG indexing to complete summarization

### 2. Caching Strategy
- Cache LLM embeddings for duplicate text
- Cache enum validation rules in Redis
- Cache customer lookups (5 minute TTL)

### 3. Resource Management
- Limit concurrent transcriptions (max 5)
- Use smaller embedding model for chunks (text-embedding-3-small)
- Stream LLM responses for large outputs

### 4. Queue Prioritization
- Priority queue for API calls vs batch processing
- Separate queue for retry jobs (lower priority)

---

## Success Metrics

| Metric | Target | Monitoring |
|--------|--------|------------|
| End-to-end latency | < 120s | Prometheus timer |
| API response time | < 200ms | HTTP middleware |
| JSON validation pass rate | > 95% | Counter metric |
| Job success rate | > 98% | Job status aggregation |
| Chunk processing time | < 10s/chunk | LLM API timer |
| Vector insertion time | < 500ms/batch | Milvus client timer |

---

## Extended Features (v4.0)

The Call Processing Pipeline includes the following integrated capabilities:

### Feature 5: BANT Lead Scoring
Integrated into Step 7 (Post-Processing). See **[Features 5-9](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md)** for details.

- **Algorithm Version**: 1.0
- **Base Scoring**: 25 points each (Budget, Authority, Need, Timeline) = 100 total
- **Proportional Weighting**: Incomplete BANT data scaled proportionally (not penalized)
- **Objection Penalties**: Severity × Type multipliers (price: 1.5x, trust: 1.3x, etc.)
- **Bonus Points**: Urgency (+10), Referral (+10), Inbound (+5), Explicit Need (+5), Multiple DMs (+5)
- **Band Thresholds**: Hot (75-100), Warm (50-74), Cold (0-49)
- **Full Breakdown**: Each component tracked with evidence for explainability
- **Confidence Levels**: high (4/4 BANT), medium (3/4), low (≤2/4)

### Feature 9: Conversation Phase Detection
Added as Step 10 in the pipeline. See **[Features 5-9](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md)** for details.

- **Algorithm Version**: 1.2 (hybrid alignment)
- **6 Core Phases**: greeting, problem_discovery, qualification, objection_handling, closing, post_close
- **Hybrid Timestamp Estimation**:
  - Primary: Aligns LLM segments (accurate speakers) with API segments (accurate timestamps)
  - Fallback: Word-count estimation (400ms per word)
- **Quality Metrics**: Per-phase quality scores, overall flow score, missing phases detection
- **Analytics**: Time distribution per phase, dominant phase identification
- **Non-Blocking**: Failures don't stop the main pipeline

### Additional Capabilities

#### Tenant Configuration Integration
- Per-company qualification rules
- Custom call processing options
- Role-specific SOP selection

#### Customer Intelligence
- `is_existing_customer`: LLM-extracted from transcript (not DB check)
- Call type detection: fresh_sales, follow_up, confirmation, service_call, quote_only
- Sentiment tracking across customer's call history
- Customer history enrichment in summaries

#### Property Details Extraction (Home Services)
New extractor for home services context:
- Roof type and age
- HOA status
- Pets on property
- Solar panel installation
- Access notes

#### Enhanced Validation
- Customer name validation (prevents rep/customer confusion)
- Follow-up reason validation (prevents hallucination)
- Action item validation (removes hallucinated actions)
- JSON schema validation with retry logic

---

## File Structure

```
app/
├── api/v1/
│   └── call_processing.py        # API endpoints (7 endpoints)
│
├── tasks/
│   └── call_tasks.py             # Background task (process_call_background)
│
├── services/call_processing/
│   ├── audio_service.py          # Audio download
│   ├── transcription_service.py  # Shunya/AssemblyAI transcription
│   ├── diarization_service.py    # Hybrid LLM/API diarization
│   ├── chunking_service.py       # Semantic speaker-aware chunking
│   ├── summary_service.py        # Parallel extraction orchestration
│   ├── embedding_service.py      # HuggingFace embeddings with caching
│   ├── rag_service.py            # Milvus vector operations
│   ├── validation_service.py     # Schema and enum validation
│   ├── role_detector.py          # (Removed from pipeline - trusts rep_role)
│   ├── call_type_detector.py     # LLM-based call type detection
│   ├── customer_history_service.py # Customer context and history
│   └── phase_detection_service.py # v1.2 hybrid phase detection
│   │
│   └── extractors/
│       ├── summary_extractor.py      # Narrative, key points, actions
│       ├── compliance_extractor.py   # SOP compliance (call-type aware)
│       ├── objection_extractor.py    # 7-stage anti-hallucination pipeline
│       ├── qualification_extractor.py # 4-call structure for BANT/details
│       ├── lead_scoring.py           # BANT scoring with breakdown
│       └── home_services_context.py  # Property details extraction
│
├── models/
│   ├── call.py                   # MongoDB models
│   └── phase.py                  # Phase detection models
│
├── schemas/
│   ├── call.py                   # Pydantic request/response
│   └── phase.py                  # Phase response schemas
│
└── prompts/
    ├── summary_prompts.py
    ├── compliance_prompts.py
    ├── objection_prompts.py
    ├── qualification_prompts.py
    └── diarization_prompts.py
```

---

**Next:** [Feature 2: Weekly Insights Engine](./ARCHITECTURE_FEATURE_2_INSIGHTS_ENGINE.md)

