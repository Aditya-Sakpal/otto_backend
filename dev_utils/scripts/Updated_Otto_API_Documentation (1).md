# Otto Intelligence Service - Complete API Documentation

**Base URL:** `https://ottoai.shunyalabs.ai`

**Authentication:** All endpoints (except `/health` and `/`) require an API key in the request header:
```
X-API-Key: your_api_key_here
```

**UUID Format Requirement:** The following ID fields **must be valid UUIDs** in the format:
```
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```
Example: `550e8400-e29b-41d4-a716-446655440000`

**Required UUID Fields:**
- `company_id` - Must always be a valid UUID
- `job_id` - System generated UUID (for call processing, SOP, and insights jobs)
- `conversation_id` - System generated UUID (for Ask Otto conversations)

**Flexible ID Fields (UUID or String):**
- `call_id` - Can be UUID or any string
- `sop_id` - Can be UUID or any string
- `user_id` - Can be UUID or any string

Requests with non-UUID `company_id`, `job_id`, or `conversation_id` will be rejected with a `400 Bad Request` error.

---

## Table of Contents

1. [Health & Status APIs](#1-health--status-apis)
2. [Call Processing APIs](#2-call-processing-apis)
   - 2.1-2.5: Core Call Processing
   - 2.6: [Conversation Phase Detection](#26-get-call-conversation-phases) (NEW)
   - 2.7-2.8: [Phase Analytics](#27-search-calls-by-phase) (NEW)
   - 2.9: [List Call Summaries](#29-list-call-summaries) (NEW)
   - 2.10: [List Calls](#210-list-calls) (NEW)
   - 2.11: [Get Call Detail](#211-get-call-detail) (NEW)
3. [Insights APIs](#3-insights-apis)
   - 3.1-3.5: Core Insights
   - 3.6-3.8: [BANT Lead Scoring](#36-list-leads-with-filters) (NEW)
   - 3.9-3.11: [Agent Progression Tracking](#39-get-agent-progression) (NEW)
4. [Ask Otto (Conversational AI) APIs](#4-ask-otto-conversational-ai-apis)
5. [SOP Document Ingestion APIs](#5-sop-document-ingestion-apis)
   - 5.1-5.7: Core SOP Management
   - 5.8-5.12: [SOP Version Control](#58-upload-new-sop-version) (NEW)
6. [Tenant Configuration APIs](#6-tenant-configuration-apis)
   - 6.1-6.6: Core Configuration Management
   - 6.7-6.8: [Qualification Rules & Services](#67-add-qualification-rule) (NEW)
7. [Coaching Impact APIs](#7-coaching-impact-apis) (NEW)
   - 7.1-7.7: Core Coaching (Sessions, Impact, Effectiveness, ROI)
   - 7.8: [List Reps](#78-list-reps) (NEW)
   - 7.9: [Rep Coaching Profile](#79-get-rep-coaching-profile) (NEW)
   - 7.10: [Rep Top-3](#710-get-rep-top-3) (NEW)

---

## 1. Health & Status APIs

### 1.1 Health Check

**Endpoint:** `GET /health`

**Description:** Check if the service is healthy and running.

**Authentication:** Not required

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "otto-intelligence",
  "version": "1.0.0",
  "environment": "production"
}
```

---

### 1.2 Root Information

**Endpoint:** `GET /`

**Description:** Get basic service information and links.

**Authentication:** Not required

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/
```

**Response (200 OK):**
```json
{
  "service": "Otto Intelligence Service",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### 1.3 API Status

**Endpoint:** `GET /api/v1/status`

**Description:** Get API version and feature status.

**Authentication:** Required

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/status \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "api_version": "v1",
  "features": {
    "call_processing": "active",
    "insights_engine": "active",
    "ask_otto": "active",
    "sop_ingestion": "active",
    "coaching": "active"
  },
  "database": {
    "mongodb": "connected",
    "redis": "connected",
    "milvus": "connected",
    "postgresql": "connected"
  }
}
```

---

### 1.4 Scheduler Status

**Endpoint:** `GET /api/v1/scheduler/status`

**Description:** Get the status of background scheduler and scheduled jobs.

**Authentication:** Required

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/scheduler/status \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "scheduler_running": true,
  "jobs": [
    {
      "id": "weekly_insights_generation",
      "name": "Weekly Insights Generation",
      "trigger": "cron",
      "next_run": "2026-01-13T00:00:00Z"
    }
  ]
}
```

---

## 2. Call Processing APIs

### 2.1 Submit Call for Processing

**Endpoint:** `POST /api/v1/call-processing/process`

**Description:** Submit a call for async processing. Returns a job ID for tracking.

**Authentication:** Required

**Request Body:**
```json
{
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "audio_url": "https://s3.amazonaws.com/bucket/call_abc123.mp3",
  "phone_number": "+14155551234",
  "rep_role": "customer_rep",
  "timezone": "America/Phoenix",
  "duration": 320,
  "call_date": "2026-01-12T10:30:00Z",
  "metadata": {
    "agent": {
      "id": "USR3C843ED7AB9B471104E5442C4FF87F90",
      "name": "John Smith",
      "email": "john.smith@company.com",
      "pic_url": "/api/v1/accounts/541914/users/USR3C843ED7AB9B471104E5442C4FF87F90/pic_url"
    },
    "team": "outbound_sales",
    "campaign": "winter_2026"
  },
  "webhook_url": "https://your-app.com/webhooks/call-complete",
  "options": {
    "skip_rag_indexing": false,
    "skip_summary_generation": false,
    "priority": "normal"
  },
  "allow_reprocess": false
}
```

**Required Fields:**
- `call_id` (string): Unique call identifier (UUID or any string format)
- `company_id` (string, UUID): Company/tenant identifier in UUID format (required)
- `audio_url` (string): S3 URL to the audio file
- `phone_number` (string): Customer phone number
- `metadata.agent.id` (string, **REQUIRED**): Unique identifier for the sales representative (e.g., "USR3C843ED7AB9B471104E5442C4FF87F90")
- `metadata.agent.name` (string, **REQUIRED**): Display name of the representative (e.g., "John Smith")

**IMPORTANT - Rep Identification:**
The `metadata.agent.id` and `metadata.agent.name` fields are **REQUIRED** for:
- Agent Progression Tracking (Feature 8)
- Coaching Impact Measurement (Feature 7)
- Per-rep analytics and insights
- Weekly insights generation (top performers, needs coaching)

Calls submitted without `agent.id` and `agent.name` will receive a `400 Bad Request` error.

**Note on Backward Compatibility:**
The API also accepts the legacy flat structure (`metadata.rep_id` and `metadata.rep_name`), but the nested `agent` structure is preferred and will be normalized internally.

**Optional Fields:**
- `rep_role` (string): Representative role - either `"customer_rep"` (for CSR phone calls) or `"sales_rep"` (for in-person sales meetings). Defaults to `"customer_rep"` if not specified.
- `timezone` (string): Timezone for call_date (e.g., "America/Phoenix", "America/New_York"). Defaults to "UTC".
- `allow_reprocess` (boolean): Allow reprocessing if call_id already exists. Defaults to `false`. See "Duplicate Call Prevention" below.
- `metadata.agent.email` (string): Representative's email address
- `metadata.agent.pic_url` (string): URL to representative's profile picture
- `metadata.team` (string): Team name for grouping analytics
- `metadata.campaign` (string): Campaign or source identifier

**Duplicate Call Prevention:**

By default, the system prevents duplicate processing of the same call_id:
- If a `call_id` is already being processed or exists in the system, the request will be rejected with a `409 Conflict` error.
- Set `"allow_reprocess": true` in the request body to force reprocessing of an existing call.
- This protects against accidental duplicate processing and associated costs.

**Important:** The `company_id` must match the `company_id` used when uploading SOPs and creating tenant configurations. This is how the system knows which SOPs and business rules to apply.

**cURL:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/call-processing/process \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "550e8400-e29b-41d4-a716-446655440000",
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "audio_url": "https://s3.amazonaws.com/bucket/call_abc123.mp3",
    "phone_number": "+14155551234",
    "rep_role": "customer_rep",
    "timezone": "America/Phoenix",
    "duration": 320,
    "call_date": "2026-01-12T10:30:00Z",
    "metadata": {
      "agent": {
        "id": "USR3C843ED7AB9B471104E5442C4FF87F90",
        "name": "John Smith",
        "email": "john.smith@company.com"
      },
      "team": "outbound_sales"
    },
    "options": {
      "priority": "normal"
    }
  }'
```

**cURL - CSR Phone Call:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/call-processing/process \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "550e8400-e29b-41d4-a716-446655440001",
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "audio_url": "https://s3.amazonaws.com/bucket/call_csr_001.mp3",
    "phone_number": "+14805551234",
    "rep_role": "customer_rep",
    "metadata": {
      "agent": {
        "id": "USR3C843ED7AB9B471104E5442C4FF87F90",
        "name": "Sarah Jones",
        "email": "sarah.jones@company.com"
      }
    }
  }'
```

**cURL - Sales Rep In-Person Meeting:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/call-processing/process \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "550e8400-e29b-41d4-a716-446655440002",
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "audio_url": "https://s3.amazonaws.com/bucket/call_sales_001.mp3",
    "phone_number": "+14805551234",
    "rep_role": "sales_rep",
    "metadata": {
      "agent": {
        "id": "USR3C843ED7AB9B471104E5442C4FF87F91",
        "name": "Mike Chen",
        "email": "mike.chen@company.com"
      },
      "team": "field_sales"
    }
  }'
```

**cURL - Force Reprocess Existing Call:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/call-processing/process \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "550e8400-e29b-41d4-a716-446655440000",
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "audio_url": "https://s3.amazonaws.com/bucket/call_abc123.mp3",
    "phone_number": "+14155551234",
    "allow_reprocess": true
  }'
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Call processing initiated successfully",
  "estimated_completion_time": null,
  "status_url": "/api/v1/call-processing/status/550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-01-12T15:00:00Z"
}
```

**Error Response (400 Bad Request - Invalid UUID):**
```json
{
  "detail": "company_id must be a valid UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
}
```

**Error Response (409 Conflict - Duplicate Call):**
```json
{
  "detail": "Call 550e8400-e29b-41d4-a716-446655440000 already exists with status 'completed'. Set allow_reprocess=true to force reprocessing."
}
```

**Error Response (409 Conflict - Call Being Processed):**
```json
{
  "detail": "Call 550e8400-e29b-41d4-a716-446655440000 is already being processed. Set allow_reprocess=true to force reprocessing."
}
```

**Error Response (400 Bad Request - Missing Rep Metadata):**
```json
{
  "detail": "metadata.agent.id is required. This field is needed for Agent Progression Tracking and Coaching features."
}
```

```json
{
  "detail": "metadata.agent.name is required. This field is needed for Agent Progression Tracking and Coaching features."
}
```

**Note:** The API also accepts legacy format (`metadata.rep_id` and `metadata.rep_name`) for backward compatibility.

---

### 2.2 Get Job Status

**Endpoint:** `GET /api/v1/call-processing/status/{job_id}`

**Description:** Check the processing status and progress of a submitted job.

**Authentication:** Required

**Path Parameters:**
- `job_id` (string, required): The job ID returned from the process call endpoint

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/call-processing/status/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your_api_key_here"
```

**Response - Processing (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "call_id": "call_abc123",
  "status": "processing",
  "progress": {
    "percent": 45,
    "current_step": "summarizing",
    "steps_completed": ["downloading", "transcribing", "chunking"],
    "steps_remaining": ["validation", "storage"],
    "steps_failed": []
  },
  "started_at": "2026-01-12T15:00:05Z",
  "updated_at": "2026-01-12T15:02:30Z",
  "completed_at": null,
  "failed_at": null,
  "duration_seconds": null,
  "estimated_completion": null,
  "results": null,
  "metadata": null,
  "error": null,
  "retry_available": false,
  "retry_url": null
}
```

**Response - Completed (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "call_id": "call_abc123",
  "status": "completed",
  "progress": {
    "percent": 100,
    "current_step": "completed",
    "steps_completed": ["downloading", "transcribing", "chunking", "summarizing", "validation", "storage"],
    "steps_remaining": [],
    "steps_failed": []
  },
  "started_at": "2026-01-12T15:00:05Z",
  "updated_at": "2026-01-12T15:05:00Z",
  "completed_at": "2026-01-12T15:05:00Z",
  "failed_at": null,
  "duration_seconds": 295,
  "estimated_completion": null,
  "results": {
    "summary_url": "/api/v1/call-processing/summary/call_abc123",
    "chunks_url": "/api/v1/call-processing/chunks/call_abc123",
    "transcript_url": "/api/v1/call-processing/transcript/call_abc123"
  },
  "metadata": null,
  "error": null,
  "retry_available": false,
  "retry_url": null
}
```

**Response - Failed (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "call_id": "call_abc123",
  "status": "failed",
  "progress": {
    "percent": 20,
    "current_step": "transcribing",
    "steps_completed": ["downloading"],
    "steps_remaining": ["chunking", "summarizing", "validation", "storage"],
    "steps_failed": ["transcribing"]
  },
  "started_at": "2026-01-12T15:00:05Z",
  "updated_at": "2026-01-12T15:01:30Z",
  "completed_at": null,
  "failed_at": "2026-01-12T15:01:30Z",
  "duration_seconds": null,
  "estimated_completion": null,
  "results": null,
  "metadata": null,
  "error": {
    "code": "TRANSCRIPTION_FAILED",
    "message": "Audio file format not supported",
    "details": {
      "format": "unknown",
      "suggestion": "Use MP3, WAV, or M4A format"
    }
  },
  "retry_available": true,
  "retry_url": "/api/v1/call-processing/retry/550e8400-e29b-41d4-a716-446655440000"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Job 550e8400-e29b-41d4-a716-446655440000 not found"
}
```

---

### 2.3 Get Call Summary

**Endpoint:** `GET /api/v1/call-processing/summary/{call_id}`

**Description:** Retrieve the complete summary for a processed call.

**Authentication:** Required

**Path Parameters:**
- `call_id` (string, required): The call identifier

**Query Parameters:**
- `include_chunks` (boolean, optional): Include chunk summaries (default: false)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/summary/call_abc123" \
  -H "X-API-Key: your_api_key_here"
```

**cURL with chunks:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/summary/call_abc123?include_chunks=true" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "call_id": "call_abc123",
  "company_id": "company_xyz789",
  "status": "completed",
  "processed_at": "2026-01-12T15:05:00Z",
  "summary": {
    "summary": "Homeowner inquired about roof repair for a tile roof with leaks. Has a 2000 sq ft single-story home. Budget available, timeline urgent due to monsoon season.",
    "key_points": [
      "Customer owns home (not renting)",
      "Roof is leaking in multiple areas",
      "14-year-old tile roof, single story",
      "Has HOA approval already",
      "Indoor cat - sales rep should be comfortable with pets"
    ],
    "action_items": [
      "Send detailed estimate by tomorrow",
      "Schedule in-person inspection"
    ],
    "next_steps": [
      "Follow-up call scheduled for 2026-01-15"
    ],
    "pending_actions": [
      {
        "type": "send_estimate",
        "action_item": "Send detailed roof repair estimate to customer",
        "owner": "customer_rep",
        "due_at": "2026-01-14T17:00:00Z",
        "raw_text": "I'll send you a detailed estimate by tomorrow",
        "confidence": 0.95,
        "contact_method": "email",
        "category": "quote_proposal"
      }
    ],
    "sentiment_score": 0.75,
    "confidence_score": 0.88
  },
  "compliance": {
    "call_id": "call_abc123",
    "target_role": "customer_rep",
    "evaluation_mode": "sop_only",
    "sop_compliance": {
      "score": 0.92,
      "compliance_rate": 0.92,
      "stages": {
        "total": 5,
        "followed": [
          "Greeting & Introduction",
          "Needs Assessment",
          "Property Details Collection",
          "Appointment Scheduling",
          "Confirmation & Next Steps"
        ],
        "missed": []
      },
      "issues": [],
      "positive_behaviors": [
        "Captured all property details (roof type, age, HOA, solar, pets)",
        "Set clear expectations for appointment",
        "Confirmed availability with specific time window"
      ],
      "coaching_issues": [],
      "coaching_strengths": [
        {
          "behavior": "Thorough property detail collection per SOP requirements",
          "why_effective": "Complete property details enable accurate estimates and reduce site visit surprises",
          "transcript_evidence": "Rep: 'What type of roof do you have? How old is it? Any solar panels?'",
          "related_sop_metric": "property_details_collection"
        }
      ],
      "confidence": 0.85,
      "sop_version": "2.0",
      "sop_version_history_id": "vh_002"
    },
    "timestamps": {
      "sop_evaluated_at": "2026-01-12T15:05:00Z"
    }
  },
  "objections": {
    "total_count": 2,
    "objections": [
      {
        "id": 1,
        "category_id": 5,
        "category_text": "Service Fee Concerns",
        "sub_objection": null,
        "objection_text": "That seems really expensive",
        "overcome": true,
        "speaker_id": "home_owner",
        "timestamp": null,
        "confidence_score": 0.92,
        "severity": "medium",
        "response_suggestions": [
          "Emphasize long-term savings",
          "Discuss financing options"
        ],
        "created_at": "2026-01-12T15:05:00Z"
      },
      {
        "id": 2,
        "category_id": 4,
        "category_text": "Scheduling Conflicts",
        "sub_objection": null,
        "objection_text": "I'm not sure I can be available for the inspection",
        "overcome": false,
        "speaker_id": "home_owner",
        "timestamp": null,
        "confidence_score": 0.85,
        "severity": "low",
        "response_suggestions": [
          "Offer flexible scheduling options",
          "Suggest weekend or evening availability"
        ],
        "created_at": "2026-01-12T15:05:00Z"
      }
    ]
  },
  "qualification": {
    "scope_classification": "IN_SCOPE",
    "scope_reason": "Customer calling about roof repair estimate",
    "scope_confidence": 0.95,
    "scope_signals": ["requesting service estimate", "new customer inquiry"],
    "bant_scores": {
      "need": 0.85,
      "budget": 0.70,
      "timeline": 0.75,
      "authority": 0.90
    },
    "overall_score": 0.80,
    "qualification_status": "hot",
    "booking_status": "booked",
    "call_outcome_category": "qualified_and_booked",
    "appointment_type": "in-person",
    "appointment_date": "2026-01-15T14:00:00Z",
    "appointment_confirmed": true,
    "appointment_timezone": "America/Phoenix",
    "appointment_time_confidence": 1.0,
    "preferred_time_window": "afternoon",
    "appointment_intent": "new",
    "original_appointment_datetime": null,
    "new_requested_time": null,
    "service_requested": "Roof repair",
    "service_not_offered_reason": null,
    "deferred_reason": null,
    "detected_call_type": "new_inquiry",
    "is_existing_customer": false,
    "follow_up_required": false,
    "follow_up_reason": null,
    "property_details": {
      "roof_type": "tile",
      "roof_age_years": 14,
      "stories": "single",
      "hoa_status": "yes",
      "gated_community": false,
      "has_solar": true,
      "pets": "indoor cat",
      "property_access_notes": "Sales rep should be comfortable with cats",
      "roof_condition": "leaking in multiple areas",
      "special_features": []
    },
    "customer_name": "John Smith",
    "customer_name_confidence": 1.0,
    "customer_phone": "+14155551234",
    "customer_email": "john.smith@example.com",
    "decision_makers": ["John Smith"],
    "service_address_raw": "123 Main St, Phoenix, AZ 85001",
    "service_address_structured": {
      "line1": "123 Main St",
      "city": "Phoenix",
      "state": "AZ",
      "postal_code": "85001",
      "country": "US"
    },
    "address_confidence": 1.0,
    "urgency_signals": [
      "Roof is actively leaking",
      "Monsoon season approaching"
    ],
    "budget_indicators": [
      "Budget available for repair",
      "Interested in financing options"
    ],
    "confidence_score": 0.88
  },
  "lead_score": {
    "total_score": 82,
    "lead_band": "hot",
    "breakdown": [
      {"component": "budget", "points_possible": 25, "points_earned": 20, "reason": "Budget confirmed for repair"},
      {"component": "authority", "points_possible": 25, "points_earned": 22, "reason": "Decision maker identified"},
      {"component": "need", "points_possible": 25, "points_earned": 23, "reason": "Strong need - active leak"},
      {"component": "timeline", "points_possible": 25, "points_earned": 17, "reason": "Timeline: before monsoon season"}
    ],
    "algorithm_version": "1.0",
    "calculated_at": "2026-01-12T15:05:00Z",
    "confidence": "high"
  },
  "created_at": "2026-01-12T15:05:00Z"
}
```

**Response Structure Reference:**

**Top-Level Fields:**
- `call_id`, `company_id`, `status`, `processed_at`, `created_at`
- `summary`: Call summary, key points, action items, pending actions, sentiment
- `compliance`: SOP compliance evaluation with structured coaching feedback
- `objections`: Detected objections with category, severity, overcome status
- `qualification`: BANT scores, booking status, customer intelligence, property details
- `lead_score`: BANT-based 0-100 score with component breakdown (null if insufficient data)

**Summary Section:**
- `summary.summary`: Brief paragraph summary of the call
- `summary.key_points`: Array of key facts extracted from transcript
- `summary.action_items`: Array of action item strings (max 2, filtered by revenue-impact criteria)
- `summary.next_steps`: Array of next step strings
- `summary.pending_actions`: Array of structured pending action objects (see below)
- `summary.sentiment_score`: Float 0.0-1.0 (0=very negative, 1=very positive)
- `summary.confidence_score`: Float 0.0-1.0 confidence in summary accuracy

**Compliance Section:**
- `compliance.target_role`: The role evaluated (`customer_rep` or `sales_rep`)
- `compliance.evaluation_mode`: Evaluation mode (`sop_only`, `legacy`, `hybrid`)
- `compliance.sop_compliance.score`: Overall compliance score (0.0-1.0)
- `compliance.sop_compliance.stages`: Object with `total`, `followed[]`, `missed[]`
- `compliance.sop_compliance.issues`: Array of plain-text issue summaries
- `compliance.sop_compliance.positive_behaviors`: Array of plain-text strengths
- `compliance.sop_compliance.coaching_issues`: Array of structured issue objects (see below)
- `compliance.sop_compliance.coaching_strengths`: Array of structured strength objects (see below)
- `compliance.sop_compliance.confidence`: Float 0.0-1.0
- `compliance.sop_compliance.sop_version`: SOP version used for evaluation
- `compliance.timestamps.sop_evaluated_at`: When evaluation was performed

**Qualification Section:**
- `qualification.scope_classification`: Enum: `IN_SCOPE`, `OUT_OF_SCOPE` — 2-step gate (CTM metadata + LLM) that runs before BANT extraction. OUT_OF_SCOPE calls get zeroed BANT/unqualified defaults.
- `qualification.scope_reason`: Why call was classified as in/out of scope
- `qualification.scope_confidence`: Float 0.0-1.0 — confidence in scope classification (OUT_OF_SCOPE with < 0.7 defaults to IN_SCOPE)
- `qualification.scope_signals`: Array of signals used for scope classification
- `qualification.bant_scores`: Object with `need`, `budget`, `timeline`, `authority` (each 0.0-1.0)
- `qualification.overall_score`: Average of BANT scores (0.0-1.0)
- `qualification.qualification_status`: Enum: `hot`, `warm`, `cold`, `unqualified`
- `qualification.booking_status`: Enum: `booked`, `not_booked`, `service_not_offered`
- `qualification.call_outcome_category`: Computed outcome (see Call Outcome Categories below)
- `qualification.detected_call_type`: Type of call (`new_inquiry`, `follow_up`, `service_call`, `confirmation`, `quote_only`)
- `qualification.is_existing_customer`: Boolean (nullable)
- `qualification.appointment_type`: Enum: `in-person`, `virtual`, `phone` (null if not booked)
- `qualification.appointment_date`: ISO datetime (null if not booked)
- `qualification.appointment_confirmed`: Boolean
- `qualification.appointment_timezone`: Timezone string (e.g., "America/Phoenix")
- `qualification.appointment_time_confidence`: Float 0.0-1.0 (1.0=exact time, 0.3=vague)
- `qualification.preferred_time_window`: `morning`, `afternoon`, `evening`, `any` (null if N/A)
- `qualification.appointment_intent`: `new`, `reschedule`, `cancel`, `confirm` (null if N/A)
- `qualification.service_requested`: Service the customer needs (null if unclear)
- `qualification.service_not_offered_reason`: Why the company doesn't offer the requested service (null if they do)
- `qualification.deferred_reason`: Why the company deferred/referred the caller due to capacity/backlog (null if not deferred). Distinct from `service_not_offered_reason`.
- `qualification.follow_up_required`: Boolean (nullable)
- `qualification.follow_up_reason`: Brief sales briefing for next call (null if not needed)
- `qualification.property_details`: Home-services-specific property information object
- `qualification.customer_name`: Customer name extracted from call
- `qualification.customer_name_confidence`: Float 0.0-1.0
- `qualification.customer_phone`: Customer phone number
- `qualification.customer_email`: Customer email address
- `qualification.decision_makers`: Array of people with decision authority
- `qualification.service_address_raw`: Full address as mentioned in call
- `qualification.service_address_structured`: Parsed address components object
- `qualification.address_confidence`: Float 0.0-1.0
- `qualification.urgency_signals`: Array of actual phrases from transcript indicating urgency
- `qualification.budget_indicators`: Array of actual phrases from transcript indicating budget
- `qualification.confidence_score`: Overall confidence in qualification data (0.0-1.0)

**Lead Score Section (null if insufficient data):**
- `lead_score.total_score`: Integer 0-100
- `lead_score.lead_band`: `hot` (75-100), `warm` (50-74), `cold` (0-49)
- `lead_score.breakdown`: Array of component scores (budget, authority, need, timeline)
- `lead_score.algorithm_version`: Version string
- `lead_score.confidence`: `high`, `medium`, or `low`

**Call Outcome Categories:**
- `qualified_and_booked`: Customer qualified and appointment booked
- `qualified_but_unbooked`: Customer qualified but no appointment yet
- `qualified_but_deprioritized`: Customer qualifies but company deferred due to capacity/backlog (has `deferred_reason`)
- `qualified_service_not_offered`: Customer qualifies but service not offered in their area
- `follow_up_inquiry`: Existing customer following up on their job
- `existing_customer_service`: Service-related call from existing customer
- `unqualified`: OUT_OF_SCOPE calls, or cold/unqualified leads without booked appointment

**Pending Action Object Structure:**

Each object in `summary.pending_actions` contains:
- `type` (string, enum): Action type from 30 ActionType values (e.g., `call_back`, `send_quote`, `schedule_appointment`, `send_estimate`, `site_visit`, `custom`, etc.)
- `action_item` (string): Clear, imperative description of what needs to happen
- `owner` (string): Who is responsible (`customer_rep`, `customer`, customer name, `manager`, `company`)
- `due_at` (datetime, nullable): When action is due (ISO 8601)
- `raw_text` (string): Exact transcript text where action was mentioned
- `confidence` (float): 0.0-1.0 confidence this is a real action
- `contact_method` (string, enum, nullable): `phone`, `email`, `sms`, `in_person`, `any`
- `category` (string, enum): Intent category: `customer_callback`, `quote_proposal`, `rep_commitment`, `document_request`, `appointment_followup`, `decision_maker_followup`, `objection_followup`, `custom`

**Coaching Issue Object Structure:**

Each object in `compliance.sop_compliance.coaching_issues` contains:
- `issue` (string): Specific moment in call with SOP metric reference
- `why_it_matters` (string): Business impact explanation
- `how_to_fix` (string): Actionable fix with example language
- `example_language` (string, nullable): Exact words the rep could use next time
- `transcript_evidence` (string, nullable): Exact quote from transcript showing issue
- `related_sop_metric` (string, nullable): SOP metric ID reference
- `severity` (string): `high` (deal-breaker), `medium` (significant), `low` (minor)

**Coaching Strength Object Structure:**

Each object in `compliance.sop_compliance.coaching_strengths` contains:
- `behavior` (string): What the rep did well, referencing SOP metric
- `why_effective` (string): Why this behavior works for business outcomes
- `transcript_evidence` (string, nullable): Exact quote showing the behavior
- `related_sop_metric` (string, nullable): SOP metric ID reference

**Important - Objections Data Format:**

The `objections.objections` field contains an **array of rich objects** (not strings). The wrapper object also contains `objections.total_count` (integer). Each objection object includes:

- `id`: Objection identifier (nullable)
- `category_id`: Category number (1-10). See Objection Categories table below.
- `category_text`: Human-readable category name
- `sub_objection`: Sub-category from `OtherSubObjection` enum for category 9 "Other" only (null for categories 1-8, 10). Fixed to 16 values: `Financing Concerns`, `Insurance Related`, `HOA Restrictions`, `Not the Decision Maker`, `Prior Bad Experience`, `Trust/Credibility Concerns`, `Competitor Comparison`, `Contract/Terms Concerns`, `Project Scope Disagreement`, `Property Ownership Issue`, `Seasonal/Timing Preference`, `Permit/Regulatory Issue`, `Referral to Another Company`, `Existing Commitment with Competitor`, `Lack of Urgency`, `General Other`
- `objection_text`: The actual objection statement quoted from transcript
- `overcome`: Boolean indicating if the objection was resolved
- `speaker_id`: Who raised the objection (e.g., `home_owner`, `customer_rep`)
- `timestamp`: Time in call when objection was raised (nullable)
- `confidence_score`: AI confidence in objection detection (0.0-1.0)
- `severity`: Impact level (`low`, `medium`, `high`)
- `response_suggestions`: Array of recommended responses (sourced from SOP when available)
- `created_at`: Timestamp when objection was processed (nullable)

**Example:**
```json
{
  "id": 1,
  "category_id": 5,
  "category_text": "Service Fee Concerns",
  "sub_objection": null,
  "objection_text": "That seems really expensive",
  "overcome": true,
  "speaker_id": "home_owner",
  "timestamp": null,
  "confidence_score": 0.92,
  "severity": "medium",
  "response_suggestions": ["Emphasize long-term savings", "Discuss financing options"],
  "created_at": "2026-01-12T15:05:00Z"
}
```

**Objection Categories (category_id → category_text):**

| ID | Category Text |
|----|---------------|
| 1 | Immediate Service Unavailability |
| 2 | Phone Connection Issues |
| 3 | Customer Needs Time to Decide |
| 4 | Scheduling Conflicts |
| 5 | Service Fee Concerns |
| 6 | In-Person Estimates Only |
| 7 | Inefficient Agent Communication |
| 8 | Customer Data Privacy Concerns |
| 9 | Other (requires `sub_objection` from `OtherSubObjection` enum — 16 fixed values) |
| 10 | Service Not Catered |

**Common Integration Issue:**
If your model expects `objections: List[str]`, you'll get a validation error. Update your model to accept the full object structure or transform the data by extracting only the `objection_text` field.

**Error Response (404 Not Found):**
```json
{
  "detail": "Summary for call call_abc123 not found"
}
```

---

### 2.4 Get Call Chunks

**Endpoint:** `GET /api/v1/call-processing/chunks/{call_id}`

**Description:** Get all chunk summaries for a call (used for semantic search).

**Authentication:** Required

**Path Parameters:**
- `call_id` (string, required): The call identifier

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/call-processing/chunks/call_abc123 \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "call_id": "call_abc123",
  "total_chunks": 5,
  "chunks": [
    {
      "chunk_id": "chunk_001",
      "chunk_index": 0,
      "summary": {
        "text": "Agent introduces company and asks permission to continue",
        "topics": ["greeting", "introduction"],
        "sentiment": 0.8
      },
      "milvus_id": "450123789456",
      "created_at": "2026-01-12T15:04:00Z"
    },
    {
      "chunk_id": "chunk_002",
      "chunk_index": 1,
      "summary": {
        "text": "Customer expresses interest in solar panels, mentions high electricity bills",
        "topics": ["need_identification", "pain_points"],
        "sentiment": 0.65
      },
      "milvus_id": "450123789457",
      "created_at": "2026-01-12T15:04:05Z"
    },
    {
      "chunk_id": "chunk_003",
      "chunk_index": 2,
      "summary": {
        "text": "Discussion of budget and financing options",
        "topics": ["budget", "financing"],
        "sentiment": 0.7
      },
      "milvus_id": "450123789458",
      "created_at": "2026-01-12T15:04:10Z"
    },
    {
      "chunk_id": "chunk_004",
      "chunk_index": 3,
      "summary": {
        "text": "Addressing timeline and installation concerns",
        "topics": ["timeline", "objections"],
        "sentiment": 0.75
      },
      "milvus_id": "450123789459",
      "created_at": "2026-01-12T15:04:15Z"
    },
    {
      "chunk_id": "chunk_005",
      "chunk_index": 4,
      "summary": {
        "text": "Booking appointment and confirming next steps",
        "topics": ["booking", "closing"],
        "sentiment": 0.85
      },
      "milvus_id": "450123789460",
      "created_at": "2026-01-12T15:04:20Z"
    }
  ]
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Chunks for call call_abc123 not found"
}
```

---

### 2.5 Retry Failed Job

**Endpoint:** `POST /api/v1/call-processing/retry/{job_id}`

**Description:** Retry a failed processing job.

**Authentication:** Required

**Path Parameters:**
- `job_id` (string, required): The job ID that failed

**cURL:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/call-processing/retry/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your_api_key_here"
```

**Response (202 Accepted):**
```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "original_job_id": "550e8400-e29b-41d4-a716-446655440000",
  "call_id": "call_abc123",
  "status": "queued",
  "message": "Job retry initiated",
  "retry_attempt": 2,
  "status_url": "/api/v1/call-processing/status/job_x9y8z7w6v5u4"
}
```

**Error Response (400 Bad Request):**
```json
{
  "detail": "Job 550e8400-e29b-41d4-a716-446655440000 cannot be retried (status: completed)"
}
```

**Error Response (501 Not Implemented):**
```json
{
  "detail": "Retry not yet implemented - original request data not stored"
}
```

---

### 2.6 Get Call Conversation Phases

**Endpoint:** `GET /api/v1/call-processing/calls/{call_id}/phases`

**Description:** Get detected conversation phases for a processed call. Phase detection identifies 6 core phases: Greeting, Problem Discovery, Qualification, Objection Handling, Closing, and Post-Close.

**Authentication:** Required

**Path Parameters:**
- `call_id` (string, required): The call identifier

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/calls/call_abc123/phases" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "call_id": "call_abc123",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "phases": {
    "greeting": {
      "phase": "greeting",
      "detected": true,
      "confidence": 0.95,
      "timestamps": {
        "start_ms": 0,
        "end_ms": 15000,
        "duration_ms": 15000,
        "estimation_method": "segment_mapped"
      },
      "key_phrases": ["thank you for calling", "how can I help you today"],
      "quality_score": 0.9,
      "quality_notes": "Professional greeting with proper introduction"
    },
    "problem_discovery": {
      "phase": "problem_discovery",
      "detected": true,
      "confidence": 0.88,
      "timestamps": {
        "start_ms": 15000,
        "end_ms": 120000,
        "duration_ms": 105000,
        "estimation_method": "segment_mapped"
      },
      "key_phrases": ["tell me about", "what's the issue"],
      "quality_score": 0.85,
      "quality_notes": "Good discovery questions asked"
    },
    "qualification": {
      "phase": "qualification",
      "detected": true,
      "confidence": 0.82,
      "timestamps": {
        "start_ms": 120000,
        "end_ms": 200000,
        "duration_ms": 80000,
        "estimation_method": "segment_mapped"
      },
      "key_phrases": ["budget", "timeline", "decision maker"],
      "quality_score": 0.78,
      "quality_notes": "BANT criteria covered but could probe deeper"
    },
    "objection_handling": {
      "phase": "objection_handling",
      "detected": false,
      "confidence": 0.0,
      "timestamps": null,
      "key_phrases": [],
      "quality_score": null,
      "quality_notes": null
    },
    "closing": {
      "phase": "closing",
      "detected": true,
      "confidence": 0.9,
      "timestamps": {
        "start_ms": 200000,
        "end_ms": 280000,
        "duration_ms": 80000,
        "estimation_method": "segment_mapped"
      },
      "key_phrases": ["schedule", "availability"],
      "quality_score": 0.92,
      "quality_notes": "Strong close with clear next steps"
    },
    "post_close": {
      "phase": "post_close",
      "detected": true,
      "confidence": 0.85,
      "timestamps": {
        "start_ms": 280000,
        "end_ms": 320000,
        "duration_ms": 40000,
        "estimation_method": "segment_mapped"
      },
      "key_phrases": ["confirmation", "thank you"],
      "quality_score": 0.88,
      "quality_notes": "Good confirmation of details"
    }
  },
  "analytics": {
    "total_duration_ms": 320000,
    "time_distribution": {
      "greeting": 15000,
      "problem_discovery": 105000,
      "qualification": 80000,
      "closing": 80000,
      "post_close": 40000
    },
    "percentage_distribution": {
      "greeting": 4.7,
      "problem_discovery": 32.8,
      "qualification": 25.0,
      "closing": 25.0,
      "post_close": 12.5
    },
    "phases_detected": 5,
    "phases_missing": ["objection_handling"],
    "dominant_phase": "problem_discovery",
    "phase_sequence": ["greeting", "problem_discovery", "qualification", "closing", "post_close"],
    "insights": [
      "Call followed standard flow but skipped objection handling",
      "Problem discovery was thorough",
      "Strong closing technique"
    ]
  },
  "overall_flow_score": 0.85,
  "has_missing_phases": true,
  "missing_phases": ["objection_handling"],
  "processed_at": "2026-01-28T10:30:00Z",
  "algorithm_version": "1.1"
}
```

**Phase Definitions:**

| Phase | Description | Key Indicators |
|-------|-------------|----------------|
| `greeting` | Opening of the call | Name exchange, company intro, rapport building |
| `problem_discovery` | Understanding customer need | Asking about situation/problem |
| `qualification` | Assessing fit and ability to buy | Budget, timeline, decision-maker questions |
| `objection_handling` | Addressing concerns | Responding to pushback, overcoming hesitations |
| `closing` | Asking for business | Proposing next steps, booking appointment |
| `post_close` | After commitment | Confirming details, setting expectations |

**Error Response (404 Not Found):**
```json
{
  "detail": "Phases for call call_abc123 not found"
}
```

---

### 2.7 Search Calls by Phase

**Endpoint:** `GET /api/v1/call-processing/phases/search`

**Description:** Search for calls that have or are missing specific phases.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `phase` (string, optional): Filter by phase presence (e.g., `qualification`)
- `detected` (boolean, optional): Whether phase was detected (default: true)
- `missing_phase` (string, optional): Filter calls missing a specific phase
- `min_flow_score` (float, optional): Minimum overall flow score
- `days` (int, optional): Lookback days (default: 30)
- `limit` (int, optional): Results limit (default: 50)
- `offset` (int, optional): Pagination offset

**cURL - Find calls with qualification phase:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/phases/search?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&phase=qualification&detected=true" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Find calls missing closing phase:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/phases/search?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&missing_phase=closing" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "filters": {
    "missing_phase": "closing",
    "days": 30
  },
  "total": 12,
  "calls": [
    {
      "call_id": "call_001",
      "call_date": "2026-01-25T14:30:00Z",
      "rep_id": "john_smith",
      "rep_name": "John Smith",
      "phases_detected": 4,
      "missing_phases": ["closing", "post_close"],
      "overall_flow_score": 0.65,
      "detection_method": "llm"
    },
    {
      "call_id": "call_002",
      "call_date": "2026-01-24T10:15:00Z",
      "rep_id": "sarah_jones",
      "rep_name": "Sarah Jones",
      "phases_detected": 5,
      "missing_phases": ["closing"],
      "overall_flow_score": 0.72,
      "detection_method": "llm"
    }
  ]
}
```

---

### 2.8 Get Phase Analytics

**Endpoint:** `GET /api/v1/call-processing/phases/analytics`

**Description:** Get aggregated phase analytics across all calls for a company.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `days` (int, optional): Analysis period in days (default: 30)
- `rep_id` (string, optional): Filter by specific rep

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/phases/analytics?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&days=30" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "period_start": "2025-12-29T00:00:00Z",
  "period_end": "2026-01-28T00:00:00Z",
  "total_calls_analyzed": 150,
  "avg_time_per_phase_ms": {
    "greeting": 12500,
    "problem_discovery": 95000,
    "qualification": 55000,
    "objection_handling": 45000,
    "closing": 70000,
    "post_close": 35000
  },
  "detection_rates": {
    "greeting": 0.98,
    "problem_discovery": 0.95,
    "qualification": 0.85,
    "objection_handling": 0.45,
    "closing": 0.88,
    "post_close": 0.92
  },
  "avg_quality_scores": {
    "greeting": 0.87,
    "problem_discovery": 0.82,
    "qualification": 0.75,
    "objection_handling": 0.68,
    "closing": 0.80,
    "post_close": 0.85
  },
  "commonly_missing_phases": [
    {"phase": "objection_handling", "missing_rate": 0.55},
    {"phase": "qualification", "missing_rate": 0.15}
  ],
  "avg_flow_score": 0.78,
  "recommendations": [
    "55% of calls lack objection handling - consider training on objection techniques",
    "Qualification phase could be improved - average quality score 0.75"
  ]
}
```

---

### 2.9 List Call Summaries

**Endpoint:** `GET /api/v1/call-processing/summaries`

**Description:** List call summaries for a company with pagination and filters. Returns structured summaries including compliance, qualification, objections, and lead scores.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `rep_id` | string | No | Filter by rep ID (from metadata.rep_id) |
| `status` | string | No | Filter by call status |
| `from_date` | datetime | No | Filter calls from this date (ISO format) |
| `to_date` | datetime | No | Filter calls until this date (ISO format) |
| `min_compliance_score` | float | No | Minimum compliance score (0-1) |
| `max_compliance_score` | float | No | Maximum compliance score (0-1) |
| `limit` | int | No | Results per page (default: 50, max: 200) |
| `offset` | int | No | Pagination offset (default: 0) |
| `sort_by` | string | No | Sort field: `created_at`, `compliance_score` (default: created_at) |
| `sort_order` | string | No | Sort order: `asc`, `desc` (default: desc) |

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/summaries?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&limit=20&sort_by=compliance_score&sort_order=asc" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "total": 156,
  "limit": 20,
  "offset": 0,
  "summaries": [
    {
      "call_id": "abc123-def456",
      "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "summary": {
        "summary": "Customer called about roof leak...",
        "key_points": ["..."],
        "action_items": ["..."],
        "next_steps": ["..."],
        "pending_actions": [],
        "sentiment_score": 0.75,
        "confidence_score": 0.88
      },
      "compliance": {
        "call_id": "abc123-def456",
        "target_role": "customer_rep",
        "evaluation_mode": "sop_only",
        "sop_compliance": {
          "score": 0.85,
          "compliance_rate": 0.85,
          "stages": {"total": 7, "followed": ["..."], "missed": ["..."]},
          "issues": ["..."],
          "positive_behaviors": ["..."],
          "coaching_issues": [],
          "coaching_strengths": [],
          "confidence": 0.85
        }
      },
      "qualification": {
        "overall_score": 0.72,
        "qualification_status": "warm",
        "booking_status": "booked",
        "bant_scores": {"budget": 0.8, "authority": 0.9, "need": 0.7, "timeline": 0.5}
      },
      "objections": {
        "total_count": 2,
        "objections": ["..."]
      },
      "lead_score": {
        "total_score": 72,
        "lead_band": "warm",
        "breakdown": ["..."],
        "confidence": "high"
      },
      "created_at": "2026-02-03T10:30:00Z"
    }
  ]
}
```

---

### 2.10 List Calls

**Endpoint:** `GET /api/v1/call-processing/calls`

**Description:** List calls for a company with pagination and comprehensive filters. Returns call metadata including status, duration, rep info, and timestamps.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `call_ids` | string | No | Comma-separated list of specific call IDs |
| `rep_id` | string | No | Filter by rep ID (from metadata.rep_id) |
| `rep_name` | string | No | Filter by rep name (partial match, case-insensitive) |
| `status` | string | No | Filter by status: `queued`, `processing`, `completed`, `failed` |
| `phone_number` | string | No | Filter by phone number (partial match) |
| `from_date` | datetime | No | Filter calls from this date (ISO format) |
| `to_date` | datetime | No | Filter calls until this date (ISO format) |
| `min_duration` | int | No | Minimum call duration in seconds |
| `max_duration` | int | No | Maximum call duration in seconds |
| `limit` | int | No | Results per page (default: 50, max: 200) |
| `offset` | int | No | Pagination offset (default: 0) |
| `sort_by` | string | No | Sort field: `call_date`, `created_at`, `duration` (default: call_date) |
| `sort_order` | string | No | Sort order: `asc`, `desc` (default: desc) |

**cURL - List all calls:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/calls?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&limit=50" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Filter by rep and date range:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/calls?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&rep_id=USR123&from_date=2026-02-01T00:00:00Z&to_date=2026-02-03T23:59:59Z" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Get specific calls by IDs:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/calls?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&call_ids=call-001,call-002,call-003" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "total": 245,
  "limit": 50,
  "offset": 0,
  "calls": [
    {
      "call_id": "abc123-def456",
      "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "status": "completed",
      "audio_url": "https://storage.example.com/calls/abc123.mp3",
      "phone_number": "6029999070",
      "rep_role": "customer_rep",
      "duration": 325,
      "duration_ms": 325000,
      "call_date": "2026-02-03T10:30:00Z",
      "processed_at": "2026-02-03T10:35:00Z",
      "created_at": "2026-02-03T10:30:00Z",
      "metadata": {
        "rep_id": "USR3C843ED7AB9B471161CFE46CA61534DB",
        "rep_name": "Diva Shahpur",
        "rep_email": "diva@example.com",
        "agent": {
          "id": "USR3C843ED7AB9B471161CFE46CA61534DB",
          "name": "Diva Shahpur"
        }
      }
    }
  ]
}
```

---

### 2.11 Get Call Detail

**Endpoint:** `GET /api/v1/call-processing/calls/{call_id}/detail`

**Description:** Get full details for a specific call including transcript and diarized segments.

**Authentication:** Required

**Path Parameters:**
- `call_id` (string, required): The call ID

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_transcript` | boolean | No | Include full transcript (default: true) |
| `include_segments` | boolean | No | Include diarized segments (default: false) |

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/call-processing/calls/abc123-def456/detail?include_transcript=true&include_segments=true" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "call_id": "abc123-def456",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "completed",
  "audio_url": "https://storage.example.com/calls/abc123.mp3",
  "phone_number": "6029999070",
  "rep_role": "customer_rep",
  "duration": 325,
  "duration_ms": 325000,
  "call_date": "2026-02-03T10:30:00Z",
  "processed_at": "2026-02-03T10:35:00Z",
  "created_at": "2026-02-03T10:30:00Z",
  "metadata": {
    "rep_id": "USR3C843ED7AB9B471161CFE46CA61534DB",
    "rep_name": "Diva Shahpur"
  },
  "transcript": "Thank you for calling Arizona Roofers. My name is Diva. How can I help you? ...",
  "segments": [
    {
      "speaker": "customer_rep",
      "text": "Thank you for calling Arizona Roofers. My name is Diva. How can I help you?",
      "start_time": 0.0,
      "end_time": 3.5
    },
    {
      "speaker": "customer",
      "text": "Hi, I'm calling about a leak in my roof...",
      "start_time": 3.5,
      "end_time": 8.2
    }
  ]
}
```

---

## 3. Insights APIs

### 3.1 Generate Weekly Insights

**Endpoint:** `POST /api/v1/insights/generate`

**Description:** Trigger weekly insights generation for companies. This is designed to be called by external cron jobs.

**Authentication:** Required

**Request Body:**
```json
{
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "company_ids": ["company_xyz789", "company_abc123"],
  "insight_types": ["company", "customer", "objection"],
  "webhook_url": "https://your-app.com/webhooks/insights-complete",
  "options": {
    "force_regenerate": false,
    "include_inactive_customers": false
  }
}
```

**cURL - Default (Last Week):**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/insights/generate \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "insight_types": ["company", "customer", "objection"]
  }'
```

**cURL - Specific Week:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/insights/generate \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "week_start": "2026-01-06",
    "week_end": "2026-01-12",
    "company_ids": ["company_xyz789"],
    "insight_types": ["company", "customer", "objection"],
    "webhook_url": "https://your-app.com/webhooks/insights-complete",
    "options": {
      "force_regenerate": false
    }
  }'
```

**Response (202 Accepted):**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "queued",
  "message": "Insight generation initiated for week 2026-01-06 to 2026-01-12",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "company_count": 2,
  "insight_types": ["company", "customer", "objection"],
  "estimated_completion_time": null,
  "estimated_duration": "5-10 minutes",
  "status_url": "/api/v1/insights/status/insight_job_abc123def456",
  "created_at": "2026-01-13T00:00:00Z",
  "queued_at": "2026-01-13T00:00:00Z"
}
```

**Error Response (409 Conflict):**
```json
{
  "detail": "Insights for week 2026-01-06 already exist or are being generated"
}
```

---

### 3.2 Get Insight Generation Status

**Endpoint:** `GET /api/v1/insights/status/{job_id}`

**Description:** Check the status of insight generation job.

**Authentication:** Required

**Path Parameters:**
- `job_id` (string, required): The insight job ID

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/insights/status/insight_job_abc123def456 \
  -H "X-API-Key: your_api_key_here"
```

**Response - Processing (200 OK):**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "processing",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "progress": {
    "percent": 60,
    "current_step": "generating_customer_insights",
    "companies_processed": 3,
    "companies_total": 5,
    "insights_generated": {
      "company": 3,
      "customer": 45,
      "objection": 3
    }
  },
  "started_at": "2026-01-13T00:00:05Z",
  "updated_at": "2026-01-13T00:03:30Z",
  "completed_at": null,
  "failed_at": null,
  "duration_seconds": null,
  "estimated_completion": null,
  "results": null,
  "error": null,
  "retry_available": false,
  "retry_url": null
}
```

**Response - Completed (200 OK):**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "completed",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "progress": {
    "percent": 100,
    "current_step": "completed",
    "companies_processed": 5,
    "companies_total": 5,
    "insights_generated": {
      "company": 5,
      "customer": 87,
      "objection": 5
    }
  },
  "started_at": "2026-01-13T00:00:05Z",
  "updated_at": "2026-01-13T00:06:45Z",
  "completed_at": "2026-01-13T00:06:45Z",
  "failed_at": null,
  "duration_seconds": 400,
  "estimated_completion": null,
  "results": {
    "company_insights_url": "/api/v1/insights/company/current",
    "customer_insights_url": "/api/v1/insights/customers",
    "objection_insights_url": "/api/v1/insights/objections"
  },
  "error": null,
  "retry_available": false,
  "retry_url": null
}
```

---

### 3.3 Get Current Company Insight

**Endpoint:** `GET /api/v1/insights/company/{company_id}/current`

**Description:** Get the most recent weekly insight for a company.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): The company identifier

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/insights/company/company_xyz789/current \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "company_xyz789",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "data": {
    "total_calls": 145,
    "total_booked": 32,
    "booking_rate": 0.22,
    "avg_call_duration": 425.5,
    "avg_compliance_score": 0.87,
    "avg_sentiment_score": 0.74,
    "avg_qualification_score": 0.68,
    "top_performers": [
      {
        "rep_id": "rep_001",
        "rep_name": "Sarah Johnson",
        "calls": 28,
        "booked": 12,
        "booking_rate": 0.43,
        "avg_compliance": 0.94
      },
      {
        "rep_id": "rep_002",
        "rep_name": "Mike Chen",
        "calls": 25,
        "booked": 9,
        "booking_rate": 0.36,
        "avg_compliance": 0.91
      }
    ],
    "needs_coaching": [
      {
        "rep_id": "rep_005",
        "rep_name": "Tom Wilson",
        "calls": 18,
        "booked": 2,
        "booking_rate": 0.11,
        "issues": [
          "Low compliance score (0.65)",
          "Not handling objections effectively",
          "Missing qualification steps"
        ]
      }
    ],
    "insight_heading": "Strong Performance Week",
    "insight": "Team achieved 22% booking rate, up 3% from last week. Top performers are consistently following SOP and handling objections effectively. Sarah Johnson led with 43% booking rate across 28 calls.",
    "recommendation_heading": "Focus on Coaching",
    "recommendation": "Schedule coaching sessions for reps below 15% booking rate. Focus on objection handling techniques and SOP compliance. Consider peer shadowing with top performers.",
    "trends": {
      "booking_rate": "up",
      "calls": "up",
      "compliance": "stable",
      "sentiment": "up"
    },
    "week_over_week": {
      "booking_rate_change": 0.03,
      "calls_change": 12,
      "compliance_change": 0.01,
      "sentiment_change": 0.05
    }
  },
  "generated_at": "2026-01-13T00:06:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "No insights found for company company_xyz789"
}
```

---

### 3.4 Get Customer Insights List

**Endpoint:** `GET /api/v1/insights/customers`

**Description:** Get paginated list of customer insights with filtering options.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `week_start` (date, optional): Filter by week (format: YYYY-MM-DD)
- `status` (string, optional): Filter by customer status
- `priority` (string, optional): Filter by priority level (high, medium, low)
- `page` (integer, optional): Page number (default: 1)
- `limit` (integer, optional): Results per page (default: 50, max: 200)

**cURL - Basic:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/customers?company_id=company_xyz789" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - With Filters:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/customers?company_id=company_xyz789&priority=high&page=1&limit=20" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Specific Week:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/customers?company_id=company_xyz789&week_start=2026-01-06&status=qualified" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "company_xyz789",
  "week_start": "2026-01-06",
  "total_customers": 87,
  "page": 1,
  "limit": 50,
  "customers": [
    {
      "customer_id": "cust_001",
      "phone_number": "+14155551234",
      "customer_name": "John Smith",
      "data": {
        "calls_this_week": 3,
        "total_calls": 8,
        "current_status": "qualified",
        "status_changed": true,
        "sentiment_trend": "improving",
        "engagement_score": 0.85,
        "pending_actions": 2,
        "overdue_actions": 0,
        "last_call_date": "2026-01-12T14:30:00Z",
        "insight_heading": "Ready to Close",
        "insight": "Customer has progressed through qualification stages quickly. All BANT criteria met. Strong buying signals in last 2 calls.",
        "recommendation_heading": "Send Proposal ASAP",
        "recommendation": "Priority customer. Send detailed proposal today. Schedule in-home consultation within 48 hours. High conversion probability.",
        "priority": "high"
      }
    },
    {
      "customer_id": "cust_002",
      "phone_number": "+14155559876",
      "customer_name": "Maria Garcia",
      "data": {
        "calls_this_week": 1,
        "total_calls": 4,
        "current_status": "nurturing",
        "status_changed": false,
        "sentiment_trend": "stable",
        "engagement_score": 0.62,
        "pending_actions": 1,
        "overdue_actions": 1,
        "last_call_date": "2026-01-10T11:15:00Z",
        "insight_heading": "Needs Follow-up",
        "insight": "Customer interested but has timeline concerns. Mentioned waiting until Q2 2026. One overdue follow-up action.",
        "recommendation_heading": "Long-term Nurture",
        "recommendation": "Complete overdue follow-up. Set reminder for March 2026. Send educational content about financing options.",
        "priority": "medium"
      }
    }
  ]
}
```

---

### 3.5 Get Objection Insights

**Endpoint:** `GET /api/v1/insights/objections/{company_id}`

**Description:** Get objection insights for a company showing common objections and handling effectiveness.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**Query Parameters:**
- `week_start` (date, optional): Filter by week (format: YYYY-MM-DD)
- `category_id` (integer, optional): Filter by objection category (1-10)

**cURL - All Objections:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/insights/objections/company_xyz789 \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Specific Week:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/objections/company_xyz789?week_start=2026-01-06" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Specific Category:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/objections/company_xyz789?category_id=3" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "company_xyz789",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "total_categories": 5,
  "objections": [
    {
      "category_id": 5,
      "category_name": "Service Fee Concerns",
      "total_occurrences": 42,
      "overcome_rate": 0.64,
      "avg_severity": 2.3,
      "trend": "stable",
      "example_objections": [
        "That's too expensive",
        "I can't afford that right now",
        "Your competitors are cheaper"
      ],
      "top_responses": [
        "Emphasize long-term ROI and savings",
        "Discuss flexible financing options",
        "Highlight unique value propositions"
      ],
      "insight_heading": "Service Fee Concerns Remain Top Objection",
      "insight": "Service fee concerns appeared in 29% of calls. 64% overcome rate shows room for improvement. Top performers consistently address value before price.",
      "recommendation": "Update price objection handling script. Add financing calculator to proposal. Train reps on value-based selling techniques."
    },
    {
      "category_id": 4,
      "category_name": "Scheduling Conflicts",
      "total_occurrences": 28,
      "overcome_rate": 0.82,
      "avg_severity": 1.8,
      "trend": "improving",
      "example_objections": [
        "I can't make that time work",
        "I need it done by summer",
        "Can you come on a weekend?"
      ],
      "top_responses": [
        "Offer flexible scheduling windows",
        "Provide weekend or evening availability",
        "Suggest alternative time slots"
      ],
      "insight_heading": "Scheduling Conflicts Well-Handled",
      "insight": "82% overcome rate on scheduling objections. Customers respond well to flexible scheduling options.",
      "recommendation": "Continue current approach. Consider expanding weekend availability to reduce scheduling friction."
    },
    {
      "category_id": 1,
      "category_name": "Immediate Service Unavailability",
      "total_occurrences": 21,
      "overcome_rate": 0.90,
      "avg_severity": 1.5,
      "trend": "down",
      "example_objections": [
        "I need someone out here today",
        "How soon can you get here?",
        "I can't wait that long"
      ],
      "top_responses": [
        "Acknowledge urgency and provide realistic timeline",
        "Offer expedited scheduling when available",
        "Explain the process to set expectations"
      ],
      "insight_heading": "Strong Urgency Handling",
      "insight": "90% overcome rate shows excellent handling of service availability concerns. Objections decreasing week-over-week.",
      "recommendation": "Document best practices from top performers. Use as training material for new reps."
    }
  ],
  "generated_at": "2026-01-13T00:06:15Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "No objection insights found"
}
```

---

### 3.6 List Leads with Filters

**Endpoint:** `GET /api/v1/insights/leads`

**Description:** Get a list of leads with BANT-based scores. Leads are automatically scored during call processing based on Budget, Authority, Need, and Timeline signals.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `band` (string, optional): Filter by lead band (`hot`, `warm`, `cold`)
- `min_score` (int, optional): Minimum lead score (0-100)
- `max_score` (int, optional): Maximum lead score (0-100)
- `days` (int, optional): Lookback period in days (default: 30)
- `page` (int, optional): Page number (default: 1)
- `limit` (int, optional): Results per page (default: 50)

**Lead Band Classification:**
- **Hot** (75-100): High priority, ready to buy
- **Warm** (50-74): Interested, needs nurturing
- **Cold** (0-49): Early stage or unqualified

**cURL - All leads:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/leads?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Hot leads only:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/leads?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&band=hot" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Score range:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/leads?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&min_score=60&max_score=90" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "total": 45,
  "page": 1,
  "limit": 50,
  "filters": {
    "band": null,
    "min_score": null,
    "max_score": null,
    "days": 30
  },
  "leads": [
    {
      "call_id": "call_001",
      "customer_phone": "+14155551234",
      "customer_name": "John Smith",
      "total_score": 82,
      "lead_band": "hot",
      "confidence": "high",
      "calculated_at": "2026-01-28T10:30:00Z",
      "call_date": "2026-01-28T10:00:00Z",
      "breakdown": {
        "budget": {"points_earned": 20, "points_possible": 25, "reason": "Budget confirmed: $5,000-10,000"},
        "authority": {"points_earned": 22, "points_possible": 25, "reason": "Decision maker identified"},
        "need": {"points_earned": 23, "points_possible": 25, "reason": "Strong need established"},
        "timeline": {"points_earned": 17, "points_possible": 25, "reason": "Timeline: 2-3 months"}
      },
      "objection_penalty": -5,
      "bonus_points": 5
    },
    {
      "call_id": "call_002",
      "customer_phone": "+14155559876",
      "customer_name": "Maria Garcia",
      "total_score": 58,
      "lead_band": "warm",
      "confidence": "high",
      "calculated_at": "2026-01-27T15:45:00Z",
      "call_date": "2026-01-27T15:00:00Z"
    }
  ]
}
```

---

### 3.7 Get Lead Distribution

**Endpoint:** `GET /api/v1/insights/leads/distribution`

**Description:** Get statistical distribution of lead scores across bands.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `days` (int, optional): Analysis period in days (default: 30)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/leads/distribution?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "timeframe_days": 30,
  "total_leads": 150,
  "distribution": [
    {"band": "hot", "count": 25, "percentage": 16.7},
    {"band": "warm", "count": 68, "percentage": 45.3},
    {"band": "cold", "count": 57, "percentage": 38.0}
  ],
  "avg_score": 52.3,
  "score_percentiles": {
    "p25": 35,
    "p50": 55,
    "p75": 72,
    "p90": 85
  }
}
```

---

### 3.8 Get Customer Lead History

**Endpoint:** `GET /api/v1/insights/leads/{customer_id}/history`

**Description:** Get lead score history for a specific customer across multiple calls.

**Authentication:** Required

**Path Parameters:**
- `customer_id` (string, required): Customer identifier (phone number or ID)

**Query Parameters:**
- `company_id` (string, required): Company identifier

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/leads/+14155551234/history?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "customer_id": "+14155551234",
  "customer_phone": "+14155551234",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "current_score": 82,
  "current_band": "hot",
  "history": [
    {
      "call_id": "call_003",
      "total_score": 82,
      "lead_band": "hot",
      "calculated_at": "2026-01-28T10:30:00Z",
      "score_change": 10
    },
    {
      "call_id": "call_002",
      "total_score": 72,
      "lead_band": "warm",
      "calculated_at": "2026-01-20T14:00:00Z",
      "score_change": 15
    },
    {
      "call_id": "call_001",
      "total_score": 57,
      "lead_band": "warm",
      "calculated_at": "2026-01-10T09:30:00Z",
      "score_change": null
    }
  ],
  "trend": "improving"
}
```

---

### 3.9 Get Agent Progression

**Endpoint:** `GET /api/v1/insights/agents/{rep_id}/progression`

**Description:** Track agent performance over time with weekly metrics, trend detection, and anomaly identification.

**Authentication:** Required

**Path Parameters:**
- `rep_id` (string, required): Representative identifier (must match `metadata.rep_id` from call processing)

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `metrics` (string, optional): Comma-separated metrics to track (default: all). Options: `compliance_score`, `booking_rate`, `objection_handling`, `lead_score`, `sentiment_score`
- `weeks` (int, optional): Number of weeks to analyze (default: 8, max: 52)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/agents/john_smith/progression?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&metrics=compliance_score,booking_rate&weeks=8" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "timeframe_weeks": 8,
  "period_start": "2025-12-03T00:00:00Z",
  "period_end": "2026-01-28T00:00:00Z",
  "total_calls": 45,
  "weeks_with_data": 7,
  "overall_confidence": "high",
  "metrics": {
    "compliance_score": {
      "metric_name": "compliance_score",
      "data_points": [
        {"week_start": "2025-12-03", "value": 0.72, "calls_analyzed": 6, "confidence": "high"},
        {"week_start": "2025-12-10", "value": 0.75, "calls_analyzed": 7, "confidence": "high"},
        {"week_start": "2025-12-17", "value": 0.78, "calls_analyzed": 5, "confidence": "high"},
        {"week_start": "2025-12-24", "value": 0.76, "calls_analyzed": 4, "confidence": "low"},
        {"week_start": "2025-12-31", "value": 0.80, "calls_analyzed": 6, "confidence": "high"},
        {"week_start": "2026-01-07", "value": 0.82, "calls_analyzed": 8, "confidence": "high"},
        {"week_start": "2026-01-14", "value": 0.85, "calls_analyzed": 9, "confidence": "high"}
      ],
      "trend": {
        "direction": "improving",
        "magnitude": 0.13,
        "start_value": 0.72,
        "end_value": 0.85
      },
      "anomalies": [],
      "current_value": 0.85,
      "period_change_percent": 18.1
    },
    "booking_rate": {
      "metric_name": "booking_rate",
      "data_points": [
        {"week_start": "2025-12-03", "value": 0.55, "calls_analyzed": 6, "confidence": "high"},
        {"week_start": "2025-12-10", "value": 0.57, "calls_analyzed": 7, "confidence": "high"},
        {"week_start": "2025-12-17", "value": 0.60, "calls_analyzed": 5, "confidence": "high"},
        {"week_start": "2025-12-24", "value": 0.45, "calls_analyzed": 4, "confidence": "low"},
        {"week_start": "2025-12-31", "value": 0.58, "calls_analyzed": 6, "confidence": "high"},
        {"week_start": "2026-01-07", "value": 0.55, "calls_analyzed": 8, "confidence": "high"},
        {"week_start": "2026-01-14", "value": 0.56, "calls_analyzed": 9, "confidence": "high"}
      ],
      "trend": {
        "direction": "stable",
        "magnitude": 0.01,
        "start_value": 0.55,
        "end_value": 0.56
      },
      "anomalies": [
        {
          "week_index": 3,
          "week_start": "2025-12-24",
          "change_magnitude": -0.25,
          "direction": "drop",
          "previous_value": 0.60,
          "current_value": 0.45,
          "note": "25% drop detected - review calls from this week"
        }
      ],
      "current_value": 0.56,
      "period_change_percent": 1.8
    }
  },
  "summary": {
    "improving_metrics": ["compliance_score"],
    "declining_metrics": [],
    "stable_metrics": ["booking_rate"],
    "anomalies_detected": 1,
    "alerts": [
      "Booking rate anomaly in week of 2025-12-24"
    ]
  }
}
```

**Trend Detection:**
- **Improving**: ≥5% positive change over the period
- **Declining**: ≥5% negative change over the period
- **Stable**: <5% change in either direction

**Anomaly Detection:**
- Flags week-over-week changes >20%
- Helps identify performance dips or spikes

---

### 3.10 Get Peer Comparison

**Endpoint:** `GET /api/v1/insights/agents/{rep_id}/peer-comparison`

**Description:** Compare an agent's performance against their peers.

**Authentication:** Required

**Path Parameters:**
- `rep_id` (string, required): Representative identifier

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `metric` (string, required): Metric to compare (`compliance_score`, `booking_rate`, etc.)
- `days` (int, optional): Analysis period (default: 30)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/agents/john_smith/peer-comparison?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&metric=compliance_score&days=30" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "metric": "compliance_score",
  "analysis_period_days": 30,
  "rep_score": 0.85,
  "rep_rank": 3,
  "peer_count": 15,
  "peer_average": 0.72,
  "peer_median": 0.71,
  "peer_min": 0.52,
  "peer_max": 0.92,
  "percentile": 80,
  "comparison": "above_average",
  "gap_to_top": 0.07,
  "gap_from_average": 0.13
}
```

---

### 3.11 Get Agents Summary

**Endpoint:** `GET /api/v1/insights/agents/summary`

**Description:** Get a summary view of all agents' performance for managers.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `weeks` (int, optional): Analysis period in weeks (default: 4)
- `sort_by` (string, optional): Sort field (`compliance_score`, `booking_rate`, `total_calls`)
- `sort_order` (string, optional): `asc` or `desc` (default: `desc`)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/insights/agents/summary?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&weeks=4" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "timeframe_weeks": 4,
  "period_start": "2025-12-31T00:00:00Z",
  "period_end": "2026-01-28T00:00:00Z",
  "total_agents": 15,
  "total_calls": 425,
  "agents": [
    {
      "rep_id": "sarah_jones",
      "rep_name": "Sarah Jones",
      "total_calls": 38,
      "avg_compliance_score": 0.92,
      "avg_booking_rate": 0.45,
      "avg_lead_score": 68,
      "trend_direction": "improving",
      "alerts": []
    },
    {
      "rep_id": "john_smith",
      "rep_name": "John Smith",
      "total_calls": 32,
      "avg_compliance_score": 0.85,
      "avg_booking_rate": 0.42,
      "avg_lead_score": 65,
      "trend_direction": "improving",
      "alerts": []
    },
    {
      "rep_id": "tom_wilson",
      "rep_name": "Tom Wilson",
      "total_calls": 25,
      "avg_compliance_score": 0.58,
      "avg_booking_rate": 0.22,
      "avg_lead_score": 48,
      "trend_direction": "declining",
      "alerts": [
        "Low compliance score (below 0.65)",
        "Declining trend detected"
      ]
    }
  ],
  "team_averages": {
    "compliance_score": 0.75,
    "booking_rate": 0.35,
    "lead_score": 58
  },
  "top_performers": ["sarah_jones", "john_smith"],
  "needs_coaching": ["tom_wilson"]
}
```

---

## 4. Ask Otto (Conversational AI) APIs

### 4.1 Create Conversation

**Endpoint:** `POST /api/v1/ask-otto/conversations`

**Description:** Create a new conversation session with Otto AI.

**Authentication:** Required

**Request Body:**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "user_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "metadata": {
    "source": "web_app",
    "user_role": "sales_manager"
  }
}
```

**Required Fields:**
- `company_id` (string, UUID): Company/tenant identifier in UUID format
- `user_id` (string, UUID): User creating the conversation in UUID format

**cURL:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "user_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "metadata": {
      "source": "web_app"
    }
  }'
```

**Response (201 Created):**
```json
{
  "conversation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "user_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "created_at": "2026-01-12T15:30:00Z",
  "message_count": 0,
  "expires_at": "2026-01-19T15:30:00Z"
}
```

**Error Response (400 Bad Request - Invalid UUID):**
```json
{
  "detail": "company_id must be a valid UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
}
```

---

### 4.2 Send Message

**Endpoint:** `POST /api/v1/ask-otto/conversations/{conversation_id}/messages`

**Description:** Send a message to Otto and get an AI-powered response with context from call data.

**Authentication:** Required

**Path Parameters:**
- `conversation_id` (string, required): The conversation ID

**Request Body:**
```json
{
  "message": "What did John Smith say about pricing in his last call?",
  "context": {
    "include_customer_context": true,
    "include_call_history": true,
    "max_rag_results": 5,
    "search_filters": {}
  },
  "options": {
    "stream": false,
    "include_sources": true,
    "suggest_follow_ups": true
  }
}
```

**cURL - Simple Message:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479/messages \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What did John Smith say about pricing in his last call?"
  }'
```

**cURL - With Custom Context:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479/messages \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me all qualified leads from last week",
    "context": {
      "include_customer_context": true,
      "include_call_history": true,
      "max_rag_results": 10,
      "search_filters": {
        "date_range": {
          "start": "2026-01-06",
          "end": "2026-01-12"
        },
        "qualification_status": ["qualified"]
      }
    },
    "options": {
      "include_sources": true,
      "suggest_follow_ups": true
    }
  }'
```

**Response (200 OK):**
```json
{
  "conversation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message_id": "msg_abc123def456",
  "answer": "In John Smith's most recent call on January 12th, he expressed concern about the initial $30,000 price point, saying \"That seems really expensive.\" However, after discussing long-term savings and financing options, he agreed to move forward with an in-home consultation. His primary concern was the upfront cost rather than the total value proposition.",
  "sources": [
    {
      "type": "chunk_summary",
      "call_id": "call_abc123",
      "chunk_id": "chunk_003",
      "date": "2026-01-12T10:30:00Z",
      "confidence": 0.94,
      "excerpt": "Customer: That seems really expensive. Agent: I understand. Let me show you the ROI over 20 years...",
      "url": "/api/v1/call-processing/summary/call_abc123"
    },
    {
      "type": "call_summary",
      "call_id": "call_abc123",
      "chunk_id": null,
      "date": "2026-01-12T10:30:00Z",
      "confidence": 0.88,
      "excerpt": "Price objection was raised but overcome through discussion of financing options and long-term savings.",
      "url": "/api/v1/call-processing/summary/call_abc123"
    }
  ],
  "customer_context": {
    "customer_id": "cust_001",
    "name": "John Smith",
    "phone": "+14155551234",
    "location": "Phoenix, AZ",
    "qualification_status": "hot",
    "total_calls": 8,
    "last_call_date": "2026-01-12T10:30:00Z"
  },
  "suggested_follow_ups": [
    "What other objections did John Smith raise?",
    "Show me John Smith's qualification scores",
    "When is John's appointment scheduled?"
  ],
  "confidence": 0.82,
  "metadata": {
    "tokens_used": null,
    "response_time_ms": 1250,
    "rag_results_count": 2,
    "customer_context_found": true,
    "confidence_score": 0.82,
    "debate_metadata": {
      "perspectives_run": ["data_faithful", "analytical"],
      "grounding_scores": {"data_faithful": 0.85, "analytical": 0.78},
      "agreement_score": 0.72,
      "verification_ran": false,
      "garbage_detected": false,
      "fallback_used": false,
      "total_claims": 6,
      "grounded_claims": 5
    }
  },
  "created_at": "2026-01-12T15:31:00Z"
}
```

**Source Object Fields:**
- `type` (string): Source type from CorpusType enum: `call_summary`, `chunk_summary`, `sop_document`, `sop_metric`, `sop_criteria`
- `call_id` (string, nullable): ID of the source call
- `chunk_id` (string, nullable): ID of the chunk within the call
- `date` (datetime, nullable): When the source was created
- `confidence` (float): RAG similarity score 0.0-1.0
- `excerpt` (string, nullable): First 200 characters of source text
- `url` (string, nullable): Internal API link to the source document

**Customer Context Fields (null if no customer found):**
- `customer_id`, `name`, `phone`, `location` - Customer identification
- `qualification_status` - Current qualification (hot/warm/cold/unqualified)
- `total_calls` - Number of calls from this customer
- `last_call_date` - Most recent call timestamp

**Confidence Field:**
- `confidence` (float, 0.0–1.0): Answer quality score from the multi-agent debate pipeline. Computed from grounding (35%), source coverage (25%), perspective agreement (20%), context richness (10%), and intent match (10%). Answers with confidence < 0.4 include a disclaimer.

**Debate Metadata Fields (in `metadata`):**
- `confidence_score` (float): Same value as top-level `confidence`
- `debate_metadata.perspectives_run` (array): Which perspectives generated answers (e.g., `["data_faithful", "analytical"]`)
- `debate_metadata.grounding_scores` (object): Per-perspective grounding scores
- `debate_metadata.agreement_score` (float): Token overlap between perspectives
- `debate_metadata.verification_ran` (bool): Whether the verification stage was triggered
- `debate_metadata.total_claims` / `grounded_claims` (int): Claim extraction stats

**Note:** Otto uses 13-intent classification to route queries to the appropriate data source (PostgreSQL analytics, MongoDB insights, or Milvus RAG). Sources are only populated from RAG results. Analytics and insights data are synthesized directly into the answer text. All responses pass through a multi-agent debate pipeline for hallucination prevention.

**Error Response (404 Not Found):**
```json
{
  "detail": "Conversation not found"
}
```

---

### 4.3 Get Conversation Messages

**Endpoint:** `GET /api/v1/ask-otto/conversations/{conversation_id}/messages`

**Description:** Retrieve message history for a conversation.

**Authentication:** Required

**Path Parameters:**
- `conversation_id` (string, required): The conversation ID

**Query Parameters:**
- `limit` (integer, optional): Number of messages to return (default: 50, max: 200)
- `before` (string, optional): Message ID for pagination (returns messages before this ID)

**cURL - Recent Messages:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479/messages \
  -H "X-API-Key: your_api_key_here"
```

**cURL - With Pagination:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479/messages?limit=20&before=msg_xyz789" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "conversation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "messages": [
    {
      "message_id": "msg_abc123def456",
      "role": "user",
      "content": "What did John Smith say about pricing in his last call?",
      "sources": [],
      "created_at": "2026-01-12T15:31:00Z"
    },
    {
      "message_id": "msg_abc123def457",
      "role": "assistant",
      "content": "In John Smith's most recent call on January 12th, he expressed concern about the initial $30,000 price point...",
      "sources": [
        {
          "type": "chunk_summary",
          "call_id": "call_abc123",
          "chunk_id": "chunk_003",
          "date": "2026-01-12T10:30:00Z",
          "confidence": 0.94,
          "excerpt": "Customer: That seems really expensive...",
          "url": "/api/v1/call-processing/summary/call_abc123"
        }
      ],
      "created_at": "2026-01-12T15:31:01Z"
    },
    {
      "message_id": "msg_abc123def458",
      "role": "user",
      "content": "What are his next steps?",
      "sources": [],
      "created_at": "2026-01-12T15:31:30Z"
    },
    {
      "message_id": "msg_abc123def459",
      "role": "assistant",
      "content": "John Smith has an in-home consultation scheduled for January 15th at 2:00 PM. There's also a pending action to send him a detailed proposal by January 14th.",
      "sources": [
        {
          "type": "call_summary",
          "call_id": "call_abc123",
          "chunk_id": null,
          "date": "2026-01-12T10:30:00Z",
          "confidence": 0.96,
          "excerpt": "Appointment booked for 2026-01-15 at 14:00. Follow-up proposal needed.",
          "url": "/api/v1/call-processing/summary/call_abc123"
        }
      ],
      "created_at": "2026-01-12T15:31:31Z"
    }
  ],
  "total_messages": 4,
  "has_more": false
}
```

---

### 4.4 Get Conversation Details

**Endpoint:** `GET /api/v1/ask-otto/conversations/{conversation_id}`

**Description:** Get details about a specific conversation.

**Authentication:** Required

**Path Parameters:**
- `conversation_id` (string, required): The conversation ID

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "conversation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "company_id": "company_xyz789",
  "user_id": "user_abc123",
  "created_at": "2026-01-12T15:30:00Z",
  "updated_at": "2026-01-12T15:31:31Z",
  "message_count": 4,
  "expires_at": "2026-01-19T15:30:00Z",
  "metadata": {
    "source": "web_app",
    "user_role": "sales_manager"
  }
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Conversation not found"
}
```

---

### 4.5 Delete Conversation

**Endpoint:** `DELETE /api/v1/ask-otto/conversations/{conversation_id}`

**Description:** Delete a conversation and all its messages.

**Authentication:** Required

**Path Parameters:**
- `conversation_id` (string, required): The conversation ID

**cURL:**
```bash
curl -X DELETE https://ottoai.shunyalabs.ai/api/v1/ask-otto/conversations/f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  -H "X-API-Key: your_api_key_here"
```

**Response (204 No Content):**
```
(Empty response body)
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Conversation not found"
}
```

---

## 5. SOP Document Ingestion APIs

### 5.1 Upload SOP Document

**Endpoint:** `POST /api/v1/sop/documents/upload`

**Description:** Upload a Standard Operating Procedure document (PDF, DOC, DOCX) for processing and metric extraction.

**Supports Two Methods:**
1. **Direct File Upload**: Upload a file directly using the `file` parameter (existing behavior - backward compatible)
2. **URL Download**: Provide a URL string using the `file_url` parameter (new capability)

**Authentication:** Required

**Content Type:** `multipart/form-data`

**Form Fields:**
- `file` (file, optional*): The SOP document file (for direct upload, use `-F 'file=@/path/to/file.pdf'`)
- `file_url` (string, optional*): URL to download document from (use `-F 'file_url=s3://...'` or `-F 'file_url=https://...'`)
- `company_id` (string, UUID, required): Company identifier in UUID format
- `sop_name` (string, required): Name of the SOP
- `target_role` (string, required): Target role - either `"customer_rep"` (for CSR phone call SOPs) or `"sales_rep"` (for in-person sales meeting SOPs)
- `metadata` (string, optional): JSON string with additional metadata
- `webhook_url` (string, optional): Callback URL for completion notification

**\*Note:** Exactly ONE of `file` or `file_url` must be provided, but not both.

**Supported URL Formats (for `file_url`):**
- S3: `s3://bucket-name/path/to/document.pdf` (requires AWS credentials configured on server)
- HTTP/HTTPS: `https://example.com/path/to/document.pdf`
- Local: `file:///absolute/path/document.pdf` or `/absolute/path/document.pdf`

**Important:** The `company_id` specified here must match the `company_id` used during call processing, and the `target_role` must match the `rep_role` specified in call processing requests. This is how the system knows which SOP to use for evaluation.

**cURL - Method 1: Direct File Upload (Existing - No Changes):**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/sales_sop.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=Sales Meeting Standard Operating Procedure" \
  -F "target_role=sales_rep"
```

**cURL - Method 2: S3 URL (New):**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file_url=s3://my-sop-bucket/sales_sop_v2.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=Sales Meeting Standard Operating Procedure" \
  -F "target_role=sales_rep"
```

**cURL - Method 2: HTTP/HTTPS URL (New):**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file_url=https://example.com/documents/sales_sop.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=Sales Meeting Standard Operating Procedure" \
  -F "target_role=sales_rep"
```

**cURL - CSR Phone Call SOP:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/csr_phone_sop.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=CSR Phone Call Standard Operating Procedure" \
  -F "target_role=customer_rep"
```

**cURL - With All Options:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/sales_sop.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=Sales Call Standard Operating Procedure" \
  -F "target_role=sales_rep" \
  -F 'metadata={"version":"2.0","department":"sales","author":"John Doe"}' \
  -F "webhook_url=https://your-app.com/webhooks/sop-complete"
```

**cURL - Company-Wide SOP:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/sop/documents/upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/company_sop.pdf" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "sop_name=Company-Wide Communication Standards"
```

**Response (202 Accepted):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "queued",
  "message": "SOP document processing initiated from file upload",
  "file_name": "sales_sop.pdf",
  "file_size": 2457600,
  "status_url": "/api/v1/sop/documents/status/f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "created_at": "2026-01-12T16:00:00Z"
}
```

**Error Response (400 Bad Request - Missing Both Parameters):**
```json
{
  "detail": "Either 'file' (for file upload) or 'file_url' (for URL download) must be provided"
}
```

**Error Response (400 Bad Request - Both Parameters Provided):**
```json
{
  "detail": "Provide either 'file' OR 'file_url', not both"
}
```

**Error Response (400 Bad Request - Invalid UUID):**
```json
{
  "detail": "company_id must be a valid UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
}
```

**Error Response (400 Bad Request - Invalid File Type):**
```json
{
  "detail": "Unsupported file type: image/png. Allowed: PDF, DOC, DOCX"
}
```

**Error Response (400 Bad Request - URL Download Failed):**
```json
{
  "detail": "Failed to download document from URL: S3 bucket not accessible or file does not exist"
}
```

**Error Response (413 Payload Too Large):**
```json
{
  "detail": "File too large: 52428800 bytes. Maximum: 52428800 bytes (50MB)"
}
```

---

### 5.2 Get SOP Processing Status

**Endpoint:** `GET /api/v1/sop/documents/status/{job_id}`

**Description:** Check the processing status of an uploaded SOP document.

**Authentication:** Required

**Path Parameters:**
- `job_id` (string, required): The job ID from upload response

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/sop/documents/status/f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  -H "X-API-Key: your_api_key_here"
```

**Response - Processing (200 OK):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "processing",
  "progress": {
    "percent": 60,
    "current_step": "extracting_metrics",
    "steps_completed": ["parsing_document", "analyzing_structure"],
    "steps_remaining": ["embedding_chunks", "storage"]
  },
  "started_at": "2026-01-12T16:00:05Z",
  "updated_at": "2026-01-12T16:02:30Z",
  "completed_at": null,
  "failed_at": null,
  "duration_seconds": null,
  "results": null,
  "error": null
}
```

**Response - Completed (200 OK):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "completed",
  "progress": {
    "percent": 100,
    "current_step": "completed",
    "steps_completed": ["parsing_document", "analyzing_structure", "extracting_metrics", "embedding_chunks", "storage"],
    "steps_remaining": []
  },
  "started_at": "2026-01-12T16:00:05Z",
  "updated_at": "2026-01-12T16:04:30Z",
  "completed_at": "2026-01-12T16:04:30Z",
  "failed_at": null,
  "duration_seconds": 265,
  "results": {
    "sop_id": "sop_xyz123abc456",
    "sop_name": "Sales Call Standard Operating Procedure",
    "sop_type": "call_script",
    "is_company_wide": false,
    "target_role": "sales_rep",
    "metrics_extracted": 12,
    "chunks_indexed": 24,
    "page_count": 15,
    "word_count": 3450
  },
  "error": null
}
```

**Response - Failed (200 OK):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "failed",
  "progress": {
    "percent": 30,
    "current_step": "parsing_document",
    "steps_completed": [],
    "steps_remaining": ["analyzing_structure", "extracting_metrics", "embedding_chunks", "storage"]
  },
  "started_at": "2026-01-12T16:00:05Z",
  "updated_at": "2026-01-12T16:00:45Z",
  "completed_at": null,
  "failed_at": "2026-01-12T16:00:45Z",
  "duration_seconds": null,
  "results": null,
  "error": {
    "code": "DOCUMENT_PARSING_ERROR",
    "message": "Unable to extract text from PDF",
    "details": {
      "reason": "Document may be password protected or corrupted"
    }
  }
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Job not found"
}
```

---

### 5.3 Get Company SOP Metrics

**Endpoint:** `GET /api/v1/sop/metrics/{company_id}`

**Description:** Get all active SOP metrics for a company (role-specific and company-wide).

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**Query Parameters:**
- `role` (string, optional): Filter by target role
- `sop_id` (string, optional): Get specific SOP metrics

**cURL - All Company SOPs:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/sop/metrics/company_xyz789 \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Role-Specific:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/metrics/company_xyz789?role=sales_rep" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Specific SOP:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/metrics/company_xyz789?sop_id=sop_xyz123abc456" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "company_xyz789",
  "active_sops": [
    {
      "sop_id": "sop_xyz123abc456",
      "sop_name": "Sales Call Standard Operating Procedure",
      "sop_type": "call_script",
      "target_role": "sales_rep",
      "is_company_wide": false,
      "version": "2.0",
      "total_metrics": 12,
      "metrics": [
        {
          "metric_id": "metric_001",
          "metric_name": "Proper Greeting",
          "description": "Agent provides professional greeting with company name and personal introduction",
          "evaluation_method": "binary",
          "target_value": 1.0,
          "weight": 0.08,
          "applicable_roles": ["sales_rep", "customer_service"],
          "evaluation_criteria": {
            "required_elements": ["company_name", "agent_name", "permission_to_continue"]
          }
        },
        {
          "metric_id": "metric_002",
          "metric_name": "BANT Qualification",
          "description": "Agent qualifies lead using BANT framework (Budget, Authority, Need, Timeline)",
          "evaluation_method": "scoring",
          "target_value": 0.8,
          "weight": 0.15,
          "applicable_roles": ["sales_rep"],
          "evaluation_criteria": {
            "components": ["budget", "authority", "need", "timeline"],
            "minimum_score": 0.8
          }
        },
        {
          "metric_id": "metric_003",
          "metric_name": "Objection Handling",
          "description": "Agent properly addresses customer objections using approved techniques",
          "evaluation_method": "scoring",
          "target_value": 0.75,
          "weight": 0.12,
          "applicable_roles": ["sales_rep"],
          "evaluation_criteria": {
            "acknowledge": true,
            "empathize": true,
            "respond_with_value": true
          }
        }
      ],
      "created_at": "2026-01-12T16:04:30Z",
      "status": "active"
    }
  ],
  "company_wide_sops": [
    {
      "sop_id": "sop_abc789xyz123",
      "sop_name": "Company-Wide Communication Standards",
      "sop_type": "general_sop",
      "target_role": null,
      "is_company_wide": true,
      "version": "1.0",
      "total_metrics": 5,
      "metrics": [
        {
          "metric_id": "metric_101",
          "metric_name": "Professional Tone",
          "description": "Maintain professional and courteous tone throughout interaction",
          "evaluation_method": "scoring",
          "target_value": 0.9,
          "weight": 0.20,
          "applicable_roles": ["all"],
          "evaluation_criteria": {
            "no_slang": true,
            "respectful_language": true,
            "positive_phrasing": true
          }
        }
      ],
      "created_at": "2026-01-10T10:00:00Z",
      "status": "active"
    }
  ]
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "SOP not found"
}
```

---

### 5.4 Get SOP Document Details

**Endpoint:** `GET /api/v1/sop/documents/{sop_id}`

**Description:** Get detailed information about a specific SOP document.

**Authentication:** Required

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123abc456 \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "sop_id": "sop_xyz123abc456",
  "company_id": "company_xyz789",
  "sop_name": "Sales Call Standard Operating Procedure",
  "sop_type": "call_script",
  "target_role": "sales_rep",
  "is_company_wide": false,
  "file_info": {
    "original_filename": "sales_sop.pdf",
    "file_type": "application/pdf",
    "file_size": 2457600,
    "page_count": 15,
    "word_count": 3450
  },
  "sections": [
    {
      "title": "Introduction and Greeting",
      "page_start": 1,
      "page_end": 2
    },
    {
      "title": "Discovery Questions",
      "page_start": 3,
      "page_end": 5
    },
    {
      "title": "BANT Qualification",
      "page_start": 6,
      "page_end": 8
    },
    {
      "title": "Objection Handling",
      "page_start": 9,
      "page_end": 12
    },
    {
      "title": "Closing Techniques",
      "page_start": 13,
      "page_end": 15
    }
  ],
  "metrics_summary": {
    "total_metrics": 12,
    "by_category": {
      "greeting": 2,
      "qualification": 3,
      "objection_handling": 2,
      "closing": 3,
      "compliance": 2
    }
  },
  "status": "active",
  "version": "2.0",
  "created_at": "2026-01-12T16:04:30Z",
  "updated_at": "2026-01-12T16:04:30Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "SOP document not found"
}
```

---

### 5.5 List SOP Documents

**Endpoint:** `GET /api/v1/sop/documents`

**Description:** Get a paginated list of SOP documents for a company.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `status` (string, optional): Filter by status (active, inactive, draft)
- `target_role` (string, optional): Filter by target role
- `page` (integer, optional): Page number (default: 1)
- `limit` (integer, optional): Results per page (default: 20, max: 100)

**cURL - All SOPs:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/documents?company_id=company_xyz789" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Active SOPs Only:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/documents?company_id=company_xyz789&status=active" \
  -H "X-API-Key: your_api_key_here"
```

**cURL - Role-Specific with Pagination:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/documents?company_id=company_xyz789&target_role=sales_rep&page=1&limit=10" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "company_xyz789",
  "total": 8,
  "page": 1,
  "limit": 20,
  "documents": [
    {
      "sop_id": "sop_xyz123abc456",
      "sop_name": "Sales Call Standard Operating Procedure",
      "sop_type": "call_script",
      "target_role": "sales_rep",
      "is_company_wide": false,
      "status": "active",
      "metrics_count": 12,
      "created_at": "2026-01-12T16:04:30Z"
    },
    {
      "sop_id": "sop_abc789xyz123",
      "sop_name": "Company-Wide Communication Standards",
      "sop_type": "general_sop",
      "target_role": null,
      "is_company_wide": true,
      "status": "active",
      "metrics_count": 5,
      "created_at": "2026-01-10T10:00:00Z"
    },
    {
      "sop_id": "sop_def456ghi789",
      "sop_name": "Customer Service Excellence Guide",
      "sop_type": "process_guide",
      "target_role": "customer_service",
      "is_company_wide": false,
      "status": "active",
      "metrics_count": 8,
      "created_at": "2026-01-08T14:30:00Z"
    },
    {
      "sop_id": "sop_ghi789jkl012",
      "sop_name": "Legacy Sales Script (Deprecated)",
      "sop_type": "call_script",
      "target_role": "sales_rep",
      "is_company_wide": false,
      "status": "inactive",
      "metrics_count": 10,
      "created_at": "2025-11-15T09:00:00Z"
    }
  ]
}
```

---

### 5.6 Update SOP Status

**Endpoint:** `PATCH /api/v1/sop/documents/{sop_id}/status`

**Description:** Update the status of an SOP document (activate/deactivate).

**Authentication:** Required

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier

**Request Body:**
```json
{
  "status": "inactive",
  "reason": "Replaced by updated version 3.0"
}
```

**cURL - Deactivate:**
```bash
curl -X PATCH https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123abc456/status \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "inactive",
    "reason": "Replaced by updated version 3.0"
  }'
```

**cURL - Activate:**
```bash
curl -X PATCH https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123abc456/status \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "reason": "Approved by management"
  }'
```

**Response (200 OK):**
```json
{
  "sop_id": "sop_xyz123abc456",
  "previous_status": "active",
  "new_status": "inactive",
  "updated_at": "2026-01-12T17:00:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "SOP document not found"
}
```

---

### 5.7 Delete SOP Document

**Endpoint:** `DELETE /api/v1/sop/documents/{sop_id}`

**Description:** Permanently delete an SOP document and all associated data.

**Authentication:** Required

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier

**cURL:**
```bash
curl -X DELETE https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123abc456 \
  -H "X-API-Key: your_api_key_here"
```

**Response (204 No Content):**
```
(Empty response body)
```

**Error Response (404 Not Found):**
```json
{
  "detail": "SOP document not found"
}
```

---

### 5.8 Upload New SOP Version

**Endpoint:** `POST /api/v1/sop/documents/{sop_id}/versions`

**Description:** Upload a new version of an existing SOP document. The current version is automatically archived and the new version becomes active (or can be scheduled for future activation).

**Authentication:** Required

**Content Type:** `multipart/form-data`

**Path Parameters:**
- `sop_id` (string, required): The existing SOP document identifier

**Form Fields:**
- `file` (file, required): The updated SOP document file
- `activation_date` (datetime, optional): Future activation date (ISO format). If not provided, activates immediately.
- `created_by` (string, optional): User who uploaded the version
- `change_notes` (string, optional): Description of changes in this version

**cURL - Immediate Activation:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123/versions" \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/updated_sop_v2.pdf" \
  -F "created_by=admin@company.com" \
  -F "change_notes=Updated objection handling section"
```

**cURL - Scheduled Activation:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123/versions" \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@/path/to/updated_sop_v2.pdf" \
  -F "activation_date=2026-02-01T00:00:00Z" \
  -F "created_by=admin@company.com" \
  -F "change_notes=Q1 2026 updates - takes effect Feb 1"
```

**Response (202 Accepted):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "sop_id": "sop_xyz123",
  "current_version": 1,
  "new_version": 2,
  "status": "queued",
  "activation_date": "2026-02-01T00:00:00Z",
  "is_scheduled": true,
  "message": "Version 2 upload initiated. Will activate on 2026-02-01",
  "status_url": "/api/v1/sop/documents/status/f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "created_at": "2026-01-28T10:00:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "SOP sop_xyz123 not found. Use the upload endpoint to create a new SOP first."
}
```

**Error Response (409 Conflict - Duplicate Content):**
```json
{
  "detail": "This file is identical to the current version (same file hash). No new version created."
}
```

---

### 5.9 Get SOP Version History

**Endpoint:** `GET /api/v1/sop/documents/{sop_id}/versions`

**Description:** Get the complete version history for an SOP document, including archived versions.

**Authentication:** Required

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123/versions" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "sop_id": "sop_xyz123",
  "sop_name": "Sales Call Standard Operating Procedure",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "current_version": 2,
  "total_versions": 3,
  "versions": [
    {
      "history_id": "vh_003",
      "version": 3,
      "status": "scheduled",
      "created_at": "2026-01-28T10:00:00Z",
      "activation_date": "2026-02-01T00:00:00Z",
      "created_by": "admin@company.com",
      "change_notes": "Q1 2026 updates",
      "total_metrics": 15,
      "file_hash": "abc123..."
    },
    {
      "history_id": "vh_002",
      "version": 2,
      "status": "active",
      "created_at": "2026-01-15T10:00:00Z",
      "activated_at": "2026-01-15T10:00:00Z",
      "created_by": "admin@company.com",
      "change_notes": "Added closing techniques section",
      "total_metrics": 14,
      "file_hash": "def456..."
    },
    {
      "history_id": "vh_001",
      "version": 1,
      "status": "archived",
      "created_at": "2026-01-01T10:00:00Z",
      "activated_at": "2026-01-01T10:00:00Z",
      "archived_at": "2026-01-15T10:00:00Z",
      "created_by": "setup@company.com",
      "change_notes": "Initial version",
      "total_metrics": 12,
      "file_hash": "ghi789..."
    }
  ]
}
```

**Version Status Values:**
- `active`: Currently in use for call evaluations
- `scheduled`: Uploaded but will activate on a future date
- `archived`: Previously active, now replaced by newer version

---

### 5.10 Get Specific SOP Version

**Endpoint:** `GET /api/v1/sop/documents/{sop_id}/versions/{version}`

**Description:** Get details of a specific version of an SOP document, including its metrics.

**Authentication:** Required

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier
- `version` (integer, required): The version number

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123/versions/1" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "sop_id": "sop_xyz123",
  "version": 1,
  "status": "archived",
  "sop_name": "Sales Call Standard Operating Procedure",
  "created_at": "2026-01-01T10:00:00Z",
  "activated_at": "2026-01-01T10:00:00Z",
  "archived_at": "2026-01-15T10:00:00Z",
  "created_by": "setup@company.com",
  "change_notes": "Initial version",
  "metrics": [
    {
      "metric_id": "metric_001",
      "metric_name": "Proper Greeting",
      "weight": 0.08
    },
    {
      "metric_id": "metric_002",
      "metric_name": "BANT Qualification",
      "weight": 0.15
    }
  ],
  "total_metrics": 12,
  "file_info": {
    "original_filename": "sales_sop_v1.pdf",
    "file_size": 2457600,
    "file_hash": "ghi789..."
  }
}
```

---

### 5.11 Trigger Call Re-Analysis

**Endpoint:** `POST /api/v1/sop/documents/{sop_id}/reanalyze`

**Description:** Re-analyze historical calls against a new SOP version. This allows you to see how calls would have scored with updated SOP metrics.

**Authentication:** Required

**Content Type:** `multipart/form-data`

**Path Parameters:**
- `sop_id` (string, required): The SOP document identifier

**Form Fields:**
- `company_id` (string, required): Company identifier
- `lookback_days` (int, optional): Number of days to look back (default: 14, max: 90)
- `target_version` (int, optional): Specific version to re-analyze against (default: current active version)

**cURL:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/sop/documents/sop_xyz123/reanalyze" \
  -H "X-API-Key: your_api_key_here" \
  -F "company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8" \
  -F "lookback_days=14"
```

**Response (202 Accepted):**
```json
{
  "job_id": "reanalysis_abc123",
  "sop_id": "sop_xyz123",
  "new_sop_version": 2,
  "lookback_days": 14,
  "status": "queued",
  "total_calls": 45,
  "message": "Re-analysis initiated for 45 calls",
  "status_url": "/api/v1/sop/reanalysis/reanalysis_abc123",
  "created_at": "2026-01-28T10:00:00Z"
}
```

---

### 5.12 Get Re-Analysis Results

**Endpoint:** `GET /api/v1/sop/reanalysis/{job_id}`

**Description:** Get the status and results of a re-analysis job.

**Authentication:** Required

**Path Parameters:**
- `job_id` (string, required): The re-analysis job ID

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/sop/reanalysis/reanalysis_abc123" \
  -H "X-API-Key: your_api_key_here"
```

**Response - Processing (200 OK):**
```json
{
  "job_id": "reanalysis_abc123",
  "sop_id": "sop_xyz123",
  "status": "processing",
  "total_calls": 45,
  "processed_calls": 28,
  "progress_percent": 62,
  "started_at": "2026-01-28T10:00:05Z",
  "estimated_completion": "2026-01-28T10:05:00Z"
}
```

**Response - Completed (200 OK):**
```json
{
  "job_id": "reanalysis_abc123",
  "sop_id": "sop_xyz123",
  "status": "completed",
  "total_calls": 45,
  "processed_calls": 40,
  "failed_calls": 0,
  "skipped_calls": 5,
  "skipped_reason": "already_evaluated_with_current_version",
  "calls_improved": 18,
  "calls_declined": 8,
  "calls_unchanged": 14,
  "avg_score_change": 0.032,
  "avg_old_score": 0.72,
  "avg_new_score": 0.75,
  "results_summary": {
    "calls_improved": 18,
    "calls_declined": 8,
    "calls_unchanged": 14,
    "avg_score_change": 3.2,
    "avg_old_score": 0.72,
    "avg_new_score": 0.75
  },
  "metric_changes": {
    "Warm Entry & Rapport Building": {
      "metric_id": "warm_entry_rapport_building_success",
      "avg_change": 5.2,
      "direction": "improved",
      "avg_old_score": 0.65,
      "avg_new_score": 0.70
    },
    "Proper Greeting": {
      "metric_id": "proper_greeting",
      "avg_change": -1.5,
      "direction": "stable",
      "avg_old_score": 0.82,
      "avg_new_score": 0.81
    },
    "Objection Handling": {
      "metric_id": "objection_handling",
      "avg_change": 8.7,
      "direction": "improved",
      "avg_old_score": 0.58,
      "avg_new_score": 0.67
    }
  },
  "created_at": "2026-01-28T10:00:00Z",
  "completed_at": "2026-01-28T10:04:30Z",
  "error": null
}
```

**Response Fields:**

| Field | Description |
|-------|-------------|
| `total_calls` | Total calls in the lookback period |
| `processed_calls` | Calls that were actually re-evaluated |
| `skipped_calls` | Calls skipped (already evaluated with current SOP version) |
| `skipped_reason` | Reason for skipping (null if no calls skipped) |
| `calls_improved` | Calls with >2% score increase |
| `calls_declined` | Calls with >2% score decrease |
| `calls_unchanged` | Calls with ≤2% score change |
| `avg_score_change` | Average compliance score change (decimal, e.g., 0.032 = 3.2%) |
| `avg_old_score` | Average compliance score before re-analysis |
| `avg_new_score` | Average compliance score after re-analysis |
| `results_summary` | Detailed summary with percentage-formatted changes |
| `metric_changes` | Per-metric analysis showing which SOP criteria improved/declined |

**Use Cases for Re-Analysis:**
1. **Impact Assessment**: See how a new SOP version would affect existing call scores before activation
2. **Compliance Tracking**: Measure improvement after SOP training
3. **A/B Testing**: Compare different SOP versions against the same calls
4. **Historical Reporting**: Generate reports using updated criteria

---

## 6. Tenant Configuration APIs

### 6.1 Create Tenant Configuration

**Endpoint:** `POST /api/v1/tenant-config/`

**Description:** Create a new tenant configuration for a company with custom qualification rules, service prioritization, and keywords.

**Authentication:** Required

**Request Body:**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "company_name": "Arizona Roofers Inc.",
  "qualification_thresholds": {
    "hot_min_score": 0.80,
    "warm_min_score": 0.55,
    "cold_min_score": 0.30,
    "need_weight": 0.3,
    "budget_weight": 0.2,
    "authority_weight": 0.2,
    "timeline_weight": 0.3
  },
  "service_prioritization": {
    "services": [
      {
        "service_type": "roof_replacement",
        "display_name": "Roof Replacement",
        "priority": "high",
        "current_wait_time_weeks": null,
        "is_active": true,
        "qualification_boost": 0.1,
        "notes": "High priority during monsoon season"
      },
      {
        "service_type": "roof_repair",
        "display_name": "Roof Repair",
        "priority": "deferred",
        "current_wait_time_weeks": 8,
        "is_active": true,
        "qualification_boost": 0.0,
        "notes": "Deferred due to high demand for replacements"
      }
    ],
    "defer_low_ticket_during_high_demand": true,
    "default_priority": "normal"
  },
  "custom_keywords": {
    "urgency_keywords": [
      {
        "category": "monsoon_season",
        "keywords": ["monsoon", "rainy season", "before summer"],
        "phrases": ["before the next monsoon", "monsoon is coming"],
        "effect": "high_urgency",
        "score_impact": 0.15
      }
    ],
    "budget_keywords": [
      {
        "category": "insurance_claim",
        "keywords": ["insurance", "claim", "adjuster"],
        "phrases": ["insurance will cover", "filing a claim"],
        "effect": "budget_available",
        "score_impact": 0.2
      }
    ],
    "service_keywords": {
      "roof_replacement": ["new roof", "full replacement", "tear off"],
      "roof_repair": ["patch", "fix", "repair", "small job"]
    }
  },
  "qualification_rules": [
    {
      "rule_id": "emergency_leak_boost",
      "name": "Emergency Leak Priority",
      "description": "Boost score for emergency leak situations",
      "condition": "'leak' in urgency_signals and 'emergency' in urgency_signals",
      "action": "set_status",
      "action_value": "hot",
      "priority": 100,
      "enabled": true
    }
  ],
  "business_hours": {
    "timezone": "America/Phoenix",
    "weekday_start": "08:00",
    "weekday_end": "18:00",
    "saturday_start": "09:00",
    "saturday_end": "14:00",
    "sunday_closed": true
  },
  "service_area": ["85001", "85002", "Phoenix", "Scottsdale", "Tempe"],
  "industry": "home_services",
  "primary_services": ["roofing_repair", "roofing_replacement", "roofing_inspection"],

  "scope_config": {
    "excluded_tags": ["production", "accounting", "warranty"],
    "excluded_call_path_options": ["4", "5"],
    "tag_confidence": {"production": 0.9, "accounting": 0.85, "warranty": 0.75},
    "call_path_confidence": 0.8,
    "llm_confidence_threshold": 0.65,
    "custom_out_of_scope_signals": ["warranty claim", "existing repair follow-up"],
    "custom_in_scope_signals": ["new roof inquiry", "storm damage assessment"]
  },
  "industry_context": {
    "industry_description": "Home services company specializing in roofing",
    "service_focus": ["roof repair", "roof replacement", "inspections"],
    "geographic_region": "Phoenix, Arizona metro area",
    "high_urgency_signals": ["active leak", "water coming in", "emergency", "storm damage", "hail damage"],
    "medium_urgency_signals": ["before monsoon", "insurance deadline", "inspection period"],
    "custom_urgency_signals": ["HOA deadline", "tenant complaint"],
    "extractable_fields": [
      {"field": "roof_type", "description": "tile, shingle, flat, metal, foam"},
      {"field": "property_stories", "description": "single story, two story"},
      {"field": "hoa_status", "description": "in an HOA or not"},
      {"field": "gated_community", "description": "gated or not gated"},
      {"field": "pets_on_property", "description": "dogs, cats on property"},
      {"field": "solar_panels", "description": "solar on the roof or not"},
      {"field": "roof_age", "description": "age of roof in years"}
    ],
    "call_stages": ["Greeting & Identification", "Needs Discovery", "Qualifying", "Scheduling", "Setting Expectations", "Close & Confirmation"],
    "decision_maker_indicators": {
      "primary": ["I decide", "it's my house", "I'm the owner"],
      "secondary": ["spouse", "husband", "wife", "partner"],
      "approval_needed": ["need to check with", "husband has to see", "need approval"]
    }
  },
  "scoring_config": {
    "objection_penalties": {"high": -10, "medium": -5, "low": -2},
    "objection_type_multipliers": {"price": 1.5, "competitor": 1.2, "trust": 1.3, "authority": 1.1, "timing": 1.0, "need": 0.8, "other": 1.0},
    "bonuses": {"urgency_high": 15, "urgency_medium": 7, "referral": 12, "inbound": 5, "multiple_decision_makers": 5, "explicit_need": 8},
    "urgent_timeline_keywords": ["asap", "immediately", "urgent", "emergency", "this week", "next week", "today", "tomorrow"],
    "nearterm_timeline_keywords": ["30 days", "1 month", "this month", "next month", "60 days", "2 months"],
    "medium_timeline_keywords": ["90 days", "3 months", "quarter", "few months"]
  },
  "coaching_config": {
    "min_calls_for_baseline": 3,
    "min_calls_for_validation": 5,
    "default_follow_up_days": 10,
    "extension_days": 7,
    "max_extensions": 1,
    "outlier_percentile": 0.10,
    "improvement_threshold": 0.05
  },
  "insights_config": {
    "change_threshold": 0.03,
    "booking_rate_threshold": 0.6,
    "objection_similarity_threshold": 0.5,
    "objection_handling_threshold": 0.8,
    "default_qualification_status": "cold"
  }
}
```

**New Configuration Sub-Models (v5.3):**

All new sub-models are optional. When omitted, defaults matching previously hardcoded values are used.

| Field | Description | Default Behavior |
|-------|-------------|------------------|
| `scope_config` | Configures the scope classification gate (excluded tags, confidence thresholds, custom scope signals) | Default: production/accounting tags excluded, call path 4, LLM confidence 0.7 |
| `industry_context` | Structured industry fields assembled into LLM prompts at runtime via builder functions | Default: roofing-focused extractable fields, standard call stages, common urgency signals |
| `scoring_config` | Lead scoring penalties, multipliers, bonuses, timeline keywords | Default: HIGH=-10/MED=-5/LOW=-2 penalties, urgency_high=+10, referral=+10 bonuses |
| `coaching_config` | Coaching session thresholds (min calls, follow-up days, extensions) | Default: 5 calls baseline, 14-day follow-up, 1 extension of 7 days |
| `insights_config` | Insight generation thresholds (change, booking rate, similarity) | Default: 5% change threshold, 50% booking rate, "cold" default status |

**cURL:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/tenant-config/ \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "company_name": "Arizona Roofers Inc.",
    "qualification_thresholds": {
      "hot_min_score": 0.80,
      "warm_min_score": 0.55
    },
    "service_prioritization": {
      "services": [
        {
          "service_type": "roof_replacement",
          "display_name": "Roof Replacement",
          "priority": "high"
        },
        {
          "service_type": "roof_repair",
          "display_name": "Roof Repair",
          "priority": "deferred",
          "current_wait_time_weeks": 8
        }
      ]
    },
    "industry": "home_services",
    "primary_services": ["roofing_repair", "roofing_replacement"]
  }'
```

**Response (201 Created):**
```json
{
  "config_id": "config_abc123xyz",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "company_name": "Arizona Roofers Inc.",
  "version": 1,
  "is_active": true,
  "created_at": "2026-01-16T10:00:00Z",
  "message": "Tenant configuration created successfully"
}
```

**Error Response (400 Bad Request - Invalid UUID):**
```json
{
  "detail": "company_id must be a valid UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
}
```

**Error Response (400 Bad Request):**
```json
{
  "detail": "Configuration for company 6ba7b810-9dad-11d1-80b4-00c04fd430c8 already exists"
}
```

---

### 6.2 Get Tenant Configuration

**Endpoint:** `GET /api/v1/tenant-config/{company_id}`

**Description:** Retrieve the current configuration for a tenant.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/tenant-config/arizona_roofers \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "config_id": "config_abc123xyz",
  "company_id": "arizona_roofers",
  "company_name": "Arizona Roofers Inc.",
  "qualification_thresholds": {
    "hot_min_score": 0.80,
    "warm_min_score": 0.55,
    "cold_min_score": 0.30
  },
  "service_prioritization": {
    "services": [
      {
        "service_type": "roof_replacement",
        "display_name": "Roof Replacement",
        "priority": "high",
        "qualification_boost": 0.1
      },
      {
        "service_type": "roof_repair",
        "display_name": "Roof Repair",
        "priority": "deferred",
        "current_wait_time_weeks": 8
      }
    ]
  },
  "custom_keywords": {
    "urgency_keywords": [
      {
        "category": "monsoon_season",
        "keywords": ["monsoon", "rainy season"],
        "effect": "high_urgency",
        "score_impact": 0.15
      }
    ]
  },
  "qualification_rules": [
    {
      "rule_id": "emergency_leak_boost",
      "name": "Emergency Leak Priority",
      "condition": "'leak' in urgency_signals and 'emergency' in urgency_signals",
      "action": "set_status",
      "action_value": "hot",
      "enabled": true
    }
  ],
  "version": 1,
  "is_active": true,
  "created_at": "2026-01-16T10:00:00Z",
  "updated_at": "2026-01-16T10:00:00Z"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Configuration for company arizona_roofers not found"
}
```

---

### 6.3 Update Tenant Configuration

**Endpoint:** `PUT /api/v1/tenant-config/{company_id}`

**Description:** Update an existing tenant configuration. Previous version is archived for rollback.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**Request Body:**
```json
{
  "qualification_thresholds": {
    "hot_min_score": 0.85
  },
  "service_prioritization": {
    "services": [
      {
        "service_type": "roof_repair",
        "priority": "normal",
        "current_wait_time_weeks": null
      }
    ]
  },
  "updated_by": "admin@arizonaroofers.com"
}
```

**cURL:**
```bash
curl -X PUT https://ottoai.shunyalabs.ai/api/v1/tenant-config/arizona_roofers \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "qualification_thresholds": {
      "hot_min_score": 0.85
    },
    "updated_by": "admin@arizonaroofers.com"
  }'
```

**Response (200 OK):**
```json
{
  "config_id": "config_abc123xyz",
  "company_id": "arizona_roofers",
  "version": 2,
  "previous_version": 1,
  "updated_at": "2026-01-16T14:30:00Z",
  "message": "Configuration updated successfully"
}
```

---

### 6.4 Delete Tenant Configuration

**Endpoint:** `DELETE /api/v1/tenant-config/{company_id}`

**Description:** Soft delete (deactivate) a tenant configuration.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**cURL:**
```bash
curl -X DELETE https://ottoai.shunyalabs.ai/api/v1/tenant-config/arizona_roofers \
  -H "X-API-Key: your_api_key_here"
```

**Response (204 No Content):**
```
(Empty response body)
```

---

### 6.5 Get Configuration History

**Endpoint:** `GET /api/v1/tenant-config/{company_id}/history`

**Description:** Get version history of tenant configuration for rollback purposes.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier

**cURL:**
```bash
curl -X GET https://ottoai.shunyalabs.ai/api/v1/tenant-config/arizona_roofers/history \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "arizona_roofers",
  "total_versions": 3,
  "versions": [
    {
      "version": 3,
      "config_id": "config_abc123xyz",
      "is_active": true,
      "created_at": "2026-01-16T16:00:00Z",
      "updated_by": "admin@arizonaroofers.com",
      "changes_summary": "Increased hot threshold to 0.85"
    },
    {
      "version": 2,
      "config_id": "config_abc123xyz",
      "is_active": false,
      "created_at": "2026-01-16T14:30:00Z",
      "archived_at": "2026-01-16T16:00:00Z",
      "updated_by": "admin@arizonaroofers.com"
    },
    {
      "version": 1,
      "config_id": "config_abc123xyz",
      "is_active": false,
      "created_at": "2026-01-16T10:00:00Z",
      "archived_at": "2026-01-16T14:30:00Z",
      "updated_by": null
    }
  ]
}
```

---

### 6.6 Rollback Configuration

**Endpoint:** `POST /api/v1/tenant-config/{company_id}/rollback/{version}`

**Description:** Rollback to a previous configuration version.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier
- `version` (integer, required): Version number to rollback to

**cURL:**
```bash
curl -X POST https://ottoai.shunyalabs.ai/api/v1/tenant-config/arizona_roofers/rollback/1 \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "arizona_roofers",
  "rolled_back_from_version": 3,
  "rolled_back_to_version": 1,
  "new_version": 4,
  "message": "Configuration rolled back successfully"
}
```

---

### 6.7 Add Qualification Rule

**Endpoint:** `POST /api/v1/tenant-config/{company_id}/rules`

**Description:** Add a new qualification rule to the tenant configuration. Rules are evaluated in priority order during call processing.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier (UUID format)

**Request Body:**
```json
{
  "rule_id": "high_value_lead",
  "name": "High Value Lead Boost",
  "description": "Boost score for leads with budget over $10k",
  "condition": "budget_amount > 10000",
  "action": "boost_score",
  "action_value": 15,
  "priority": 1,
  "enabled": true
}
```

**Required Fields:**
- `rule_id` (string): Unique identifier for the rule
- `name` (string): Human-readable rule name
- `description` (string): Rule description
- `condition` (string): Python-evaluable condition expression
- `action` (string): Action to take. Options: `boost_score`, `reduce_score`, `set_status`, `set_priority`, `flag`
- `action_value` (any): Value for the action (e.g., score adjustment amount)

**Optional Fields:**
- `priority` (int): Rule evaluation order (default: 0, lower = higher priority)
- `enabled` (bool): Whether rule is active (default: true)

**cURL:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/tenant-config/6ba7b810-9dad-11d1-80b4-00c04fd430c8/rules" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "high_value_lead",
    "name": "High Value Lead Boost",
    "description": "Boost score for leads with budget over $10k",
    "condition": "budget_amount > 10000",
    "action": "boost_score",
    "action_value": 15,
    "priority": 1,
    "enabled": true
  }'
```

**Response (201 Created):**
```json
{
  "message": "Rule high_value_lead added",
  "rule": {
    "rule_id": "high_value_lead",
    "name": "High Value Lead Boost",
    "description": "Boost score for leads with budget over $10k",
    "condition": "budget_amount > 10000",
    "action": "boost_score",
    "action_value": 15,
    "priority": 1,
    "enabled": true
  }
}
```

**Error Responses:**
- `404 Not Found`: Configuration doesn't exist for company
- `409 Conflict`: Rule with same `rule_id` already exists

---

### 6.8 Add Service Configuration

**Endpoint:** `POST /api/v1/tenant-config/{company_id}/services`

**Description:** Add a new service configuration to the tenant. Services control prioritization and scoring adjustments during call processing.

**Authentication:** Required

**Path Parameters:**
- `company_id` (string, required): Company identifier (UUID format)

**Request Body:**
```json
{
  "service_type": "roof_replacement",
  "display_name": "Roof Replacement",
  "priority": "high",
  "current_wait_time_weeks": 2,
  "is_active": true,
  "qualification_boost": 10.0,
  "notes": "Priority service for full replacements"
}
```

**Required Fields:**
- `service_type` (string): Unique service type identifier
- `display_name` (string): Human-readable service name

**Optional Fields:**
- `priority` (string): Service priority level (default: "normal"). Options: `low`, `normal`, `high`, `urgent`
- `current_wait_time_weeks` (int): Current wait time in weeks
- `is_active` (bool): Whether service is currently offered (default: true)
- `qualification_boost` (float): Score boost for this service type (default: 0.0)
- `notes` (string): Additional notes

**cURL:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/tenant-config/6ba7b810-9dad-11d1-80b4-00c04fd430c8/services" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "service_type": "roof_replacement",
    "display_name": "Roof Replacement",
    "priority": "high",
    "current_wait_time_weeks": 2,
    "is_active": true,
    "qualification_boost": 10.0,
    "notes": "Priority service for full replacements"
  }'
```

**Response (201 Created):**
```json
{
  "message": "Service roof_replacement added",
  "service": {
    "service_type": "roof_replacement",
    "display_name": "Roof Replacement",
    "priority": "high",
    "current_wait_time_weeks": 2,
    "is_active": true,
    "qualification_boost": 10.0,
    "notes": "Priority service for full replacements"
  }
}
```

**Error Responses:**
- `404 Not Found`: Configuration doesn't exist for company
- `409 Conflict`: Service with same `service_type` already exists

---

## 7. Coaching Impact APIs

The Coaching Impact system provides closed-loop measurement of coaching effectiveness. It tracks coaching sessions, automatically calculates baselines from pre-coaching performance, and measures impact during a follow-up period.

### 7.1 Create Coaching Session

**Endpoint:** `POST /api/v1/coaching/sessions`

**Description:** Log a new coaching session. The system automatically calculates a baseline from the rep's last 5 calls and sets up follow-up tracking.

**Authentication:** Required

**Request Body:**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "coach_id": "jane_manager",
  "coach_name": "Jane Manager",
  "focus_areas": ["objection_handling", "closing"],
  "targets": {
    "objection_handling": 0.75,
    "closing": 0.60
  },
  "triggering_call_ids": ["call_001", "call_002"],
  "follow_up_days": 14,
  "notes": "Focus on handling price objections and asking for the business"
}
```

**Required Fields:**
- `company_id` (string, UUID): Company identifier
- `rep_id` (string): Rep being coached (must match `metadata.rep_id` from call processing)
- `rep_name` (string): Rep display name
- `coach_id` (string): Coach/manager identifier
- `coach_name` (string): Coach display name
- `focus_areas` (array): Skills to improve. Options: `compliance_score`, `objection_handling`, `closing`, `needs_assessment`, `budget_qualification`, `timeline_qualification`, `lead_score`

**Optional Fields:**
- `targets` (object): Metric → target score (0.0-1.0)
- `triggering_call_ids` (array): Calls that led to this coaching
- `follow_up_days` (int): Follow-up period (default: 14 days)
- `notes` (string): Coach notes

**cURL:**
```bash
curl -X POST "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "rep_id": "john_smith",
    "rep_name": "John Smith",
    "coach_id": "jane_manager",
    "coach_name": "Jane Manager",
    "focus_areas": ["objection_handling", "closing"],
    "targets": {
      "objection_handling": 0.75,
      "closing": 0.60
    },
    "triggering_call_ids": ["call_001", "call_002"],
    "follow_up_days": 14,
    "notes": "Focus on handling price objections"
  }'
```

**Response (201 Created):**
```json
{
  "session_id": "coach_abc123def456",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "coach_id": "jane_manager",
  "coach_name": "Jane Manager",
  "coached_at": "2026-01-28T10:00:00Z",
  "focus_areas": ["objection_handling", "closing"],
  "targets": {
    "objection_handling": 0.75,
    "closing": 0.60
  },
  "baseline": {
    "calculated_at": "2026-01-28T10:00:00Z",
    "calls_analyzed": 5,
    "call_ids": ["call_001", "call_002", "call_003", "call_004", "call_005"],
    "scores": {
      "objection_handling": 0.45,
      "closing": 0.40
    },
    "confidence": "high",
    "outliers_removed": 1
  },
  "follow_up_period_days": 14,
  "follow_up_end_date": "2026-02-11T10:00:00Z",
  "status": "in_progress",
  "impact": null,
  "created_at": "2026-01-28T10:00:00Z"
}
```

**Baseline Calculation:**
- Uses the rep's last 5 completed calls before the coaching date
- Removes top and bottom 10% outliers for accuracy
- Sets confidence to "low" if fewer than 5 calls available

---

### 7.2 List Coaching Sessions

**Endpoint:** `GET /api/v1/coaching/sessions`

**Description:** List coaching sessions with filtering options.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `rep_id` (string, optional): Filter by rep
- `coach_id` (string, optional): Filter by coach
- `status` (string, optional): Filter by status (`in_progress`, `completed`, `extended`, `insufficient_data`)
- `limit` (int, optional): Results limit (default: 50)
- `offset` (int, optional): Pagination offset

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&status=in_progress" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "total": 12,
  "limit": 50,
  "offset": 0,
  "sessions": [
    {
      "session_id": "coach_abc123def456",
      "rep_id": "john_smith",
      "rep_name": "John Smith",
      "coach_id": "jane_manager",
      "coach_name": "Jane Manager",
      "coached_at": "2026-01-28T10:00:00Z",
      "focus_areas": ["objection_handling", "closing"],
      "status": "in_progress",
      "follow_up_end_date": "2026-02-11T10:00:00Z"
    },
    {
      "session_id": "coach_xyz789ghi012",
      "rep_id": "sarah_jones",
      "rep_name": "Sarah Jones",
      "coach_id": "jane_manager",
      "coach_name": "Jane Manager",
      "coached_at": "2026-01-20T14:00:00Z",
      "focus_areas": ["compliance_score"],
      "status": "completed",
      "follow_up_end_date": "2026-02-03T14:00:00Z"
    }
  ]
}
```

---

### 7.3 Get Session Details

**Endpoint:** `GET /api/v1/coaching/sessions/{session_id}`

**Description:** Get detailed information about a specific coaching session.

**Authentication:** Required

**Path Parameters:**
- `session_id` (string, required): The coaching session ID

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions/coach_abc123def456" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "session_id": "coach_abc123def456",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "coach_id": "jane_manager",
  "coach_name": "Jane Manager",
  "coached_at": "2026-01-28T10:00:00Z",
  "focus_areas": ["objection_handling", "closing"],
  "targets": {
    "objection_handling": 0.75,
    "closing": 0.60
  },
  "triggering_call_ids": ["call_001", "call_002"],
  "notes": "Focus on handling price objections",
  "baseline": {
    "calculated_at": "2026-01-28T10:00:00Z",
    "calls_analyzed": 5,
    "scores": {
      "objection_handling": 0.45,
      "closing": 0.40
    },
    "confidence": "high"
  },
  "follow_up_period_days": 14,
  "follow_up_end_date": "2026-02-11T10:00:00Z",
  "extended_count": 0,
  "status": "in_progress",
  "impact": null,
  "created_at": "2026-01-28T10:00:00Z",
  "updated_at": "2026-01-28T10:00:00Z"
}
```

---

### 7.4 Get Impact Report

**Endpoint:** `GET /api/v1/coaching/sessions/{session_id}/impact`

**Description:** Get the detailed impact report comparing post-coaching performance to baseline.

**Authentication:** Required

**Path Parameters:**
- `session_id` (string, required): The coaching session ID

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions/coach_abc123def456/impact" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "session_id": "coach_abc123def456",
  "rep_id": "john_smith",
  "rep_name": "John Smith",
  "baseline_scores": {
    "objection_handling": 0.45,
    "closing": 0.40
  },
  "current_scores": {
    "objection_handling": 0.72,
    "closing": 0.58
  },
  "improvements": {
    "objection_handling": {
      "metric_name": "objection_handling",
      "baseline_score": 0.45,
      "current_score": 0.72,
      "absolute_change": 0.27,
      "percentage_change": 60.0,
      "target": 0.75,
      "target_met": false,
      "trend": "improving"
    },
    "closing": {
      "metric_name": "closing",
      "baseline_score": 0.40,
      "current_score": 0.58,
      "absolute_change": 0.18,
      "percentage_change": 45.0,
      "target": 0.60,
      "target_met": false,
      "trend": "improving"
    }
  },
  "overall_improved": true,
  "trend_direction": "improving",
  "targets_met": {
    "objection_handling": false,
    "closing": false
  },
  "confidence": "high",
  "calls_analyzed": 6,
  "measured_at": "2026-01-30T10:00:00Z"
}
```

**Impact Calculation:**
- Compares calls taken AFTER coaching date to baseline
- Minimum 5 calls needed for "high" confidence
- Session auto-extends by 7 days if insufficient calls
- Trend: "improving" if ≥5% positive change, "declining" if ≥5% negative
- Trend: "awaiting_data" if no post-coaching calls exist yet

---

### 7.5 Update Session Status

**Endpoint:** `PATCH /api/v1/coaching/sessions/{session_id}/status`

**Description:** Manually update the status of a coaching session. Use this to complete sessions early, extend follow-up periods, or reset sessions for re-evaluation.

**Authentication:** Required

**Path Parameters:**
- `session_id` (string, required): The coaching session ID

**Request Body:**
```json
{
  "status": "completed",
  "measure_impact": true,
  "notes": "Manual completion for testing"
}
```

**Request Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | New status: `in_progress`, `completed`, `extended`, `insufficient_data` |
| `measure_impact` | boolean | No | Measure impact before status change (default: true) |
| `extension_days` | int | No | Days to extend follow-up period, 1-30 (default: 7, only used when status='extended') |
| `notes` | string | No | Optional notes for the status change |

**cURL - Complete Session:**
```bash
curl -X PATCH "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions/coach_abc123def456/status" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed",
    "measure_impact": true,
    "notes": "Manually completed after verification"
  }'
```

**cURL - Extend Session by Custom Days:**
```bash
curl -X PATCH "https://ottoai.shunyalabs.ai/api/v1/coaching/sessions/coach_abc123def456/status" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "extended",
    "extension_days": 14,
    "notes": "Extended for 2 more weeks due to vacation"
  }'
```

**Response - Completed (200 OK):**
```json
{
  "session_id": "coach_abc123def456",
  "previous_status": "in_progress",
  "new_status": "completed",
  "impact_measured": true,
  "impact": {
    "measured_at": "2026-02-04T10:00:00Z",
    "calls_analyzed": 6,
    "scores": {
      "objection_handling": 0.72,
      "closing": 0.58
    },
    "improvements": {
      "objection_handling": {
        "metric_name": "objection_handling",
        "baseline_score": 0.45,
        "current_score": 0.72,
        "absolute_change": 0.27,
        "percentage_change": 60.0,
        "trend": "improving"
      }
    },
    "overall_improved": true,
    "trend_direction": "improving",
    "confidence": "high"
  },
  "new_follow_up_end_date": null,
  "extension_days": null,
  "message": "Session status updated from 'in_progress' to 'completed'"
}
```

**Response - Extended (200 OK):**
```json
{
  "session_id": "coach_abc123def456",
  "previous_status": "in_progress",
  "new_status": "extended",
  "impact_measured": false,
  "impact": null,
  "new_follow_up_end_date": "2026-02-25T10:00:00Z",
  "extension_days": 14,
  "message": "Session extended by 14 days. New end date: 2026-02-25T10:00:00Z"
}
```

**Status Values:**

| Status | Description |
|--------|-------------|
| `in_progress` | Session is active, waiting for follow-up period to end |
| `completed` | Follow-up period ended, impact measured |
| `extended` | Follow-up period extended (insufficient calls) |
| `insufficient_data` | Not enough post-coaching calls after extension |

**Use Cases:**
- **Manual Completion:** Set `status: "completed"` to complete a session before the follow-up period ends
- **Extend Period:** Set `status: "extended"` to add 7 more days to the follow-up period
- **Reset Session:** Set `status: "in_progress"` to re-enable a session for continued tracking

---

### 7.6 Get Coach Effectiveness

**Endpoint:** `GET /api/v1/coaching/coaches/{coach_id}/effectiveness`

**Description:** Get aggregated effectiveness metrics for a specific coach. By default computes live from completed sessions. Optional cache (populated by the weekly job and when sessions are completed via PATCH or daily follow-up) can be used for faster responses.

**Authentication:** Required

**Path Parameters:**
- `coach_id` (string, required): The coach/manager ID

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `timeframe_days` (int, optional): Analysis period (default: 90, max: 365)
- `use_cached` (boolean, optional): If true, return from `coach_effectiveness` collection when available (within last 8 days). Default: false (always compute live).

**Cache updates:** The `coach_effectiveness` collection is updated by: (1) the weekly scheduler job `calculate_weekly_coach_effectiveness`, and (2) when a session is set to `completed` or `insufficient_data` via PATCH session status or the daily follow-up job.

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/coaches/jane_manager/effectiveness?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&timeframe_days=90" \
  -H "X-API-Key: your_api_key_here"

# Use cached result (faster when available)
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/coaches/jane_manager/effectiveness?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&use_cached=true" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "coach_id": "jane_manager",
  "coach_name": "Jane Manager",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "period_start": "2025-10-30T00:00:00Z",
  "period_end": "2026-01-28T00:00:00Z",
  "total_sessions": 15,
  "completed_sessions": 12,
  "reps_coached": 8,
  "reps_improved": 10,
  "improvement_rate": 0.83,
  "avg_improvement_percentage": 28.5,
  "best_focus_area": "objection_handling",
  "worst_focus_area": "closing",
  "skill_effectiveness": {
    "objection_handling": {
      "skill_name": "objection_handling",
      "sessions_count": 10,
      "avg_improvement": 32.5,
      "success_rate": 0.90
    },
    "closing": {
      "skill_name": "closing",
      "sessions_count": 8,
      "avg_improvement": 22.1,
      "success_rate": 0.625
    },
    "compliance_score": {
      "skill_name": "compliance_score",
      "sessions_count": 5,
      "avg_improvement": 18.3,
      "success_rate": 0.80
    }
  }
}
```

---

### 7.7 Get Coaching ROI

**Endpoint:** `GET /api/v1/coaching/roi`

**Description:** Get company-wide coaching ROI metrics across all coaches.

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required): Company identifier
- `timeframe_days` (int, optional): Analysis period (default: 90)

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/roi?company_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&timeframe_days=90" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "period_start": "2025-10-30T00:00:00Z",
  "period_end": "2026-01-28T00:00:00Z",
  "total_sessions": 50,
  "total_coaches": 5,
  "total_reps_coached": 20,
  "avg_improvement_rate": 0.72,
  "overall_success_rate": 0.72,
  "top_coaches": [
    {
      "coach_id": "jane_manager",
      "coach_name": "Jane Manager",
      "sessions": 15,
      "improvement_rate": 0.83
    },
    {
      "coach_id": "bob_supervisor",
      "coach_name": "Bob Supervisor",
      "sessions": 12,
      "improvement_rate": 0.75
    }
  ],
  "most_effective_focus_areas": [
    "objection_handling",
    "needs_assessment",
    "compliance_score"
  ]
}
```

---

### 7.8 List Reps

**Endpoint:** `GET /api/v1/coaching/reps`

**Description:** List all reps (agents) with calls for a company. Returns the `rep_id` values to use when querying the profile and top-3 endpoints. The `rep_id` is the agent ID from call metadata (e.g., `USR_ANTHONY_ARIZONA`).

**Authentication:** Required

**Query Parameters:**
- `company_id` (string, required, UUID): Company identifier

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/reps?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
  "total": 6,
  "reps": [
    {
      "rep_id": "USR3C843ED7AB9B471161CFE46CA61534DB",
      "rep_name": "Diva Shahpur",
      "call_count": 562,
      "latest_call": "2026-03-12T23:59:12Z"
    },
    {
      "rep_id": "USR3C843ED7AB9B471104E5442C4FF87F90",
      "rep_name": "Bronte Pisz",
      "call_count": 543,
      "latest_call": "2026-03-12T22:30:00Z"
    },
    {
      "rep_id": "USR3C843ED7AB9B4711F9903DED76AC22FF",
      "rep_name": "Madi Meyers",
      "call_count": 251,
      "latest_call": "2026-03-11T18:00:00Z"
    }
  ]
}
```

**Notes:**
- `rep_id` is derived from `calls.metadata.agent.id` — use this value in the `/reps/{rep_id}/profile` and `/reps/{rep_id}/top3` endpoints
- Results are sorted by call count descending
- Only reps with `metadata.agent.name` present are included

---

### 7.9 Get Rep Coaching Profile

**Endpoint:** `GET /api/v1/coaching/reps/{rep_id}/profile`

**Description:** Get the full aggregated coaching profile for a rep. Returns all coaching insights bucketed into 15 canonical categories with counts, severity distributions, and representative examples. Includes top-3 most frequent strengths and weaknesses.

**Authentication:** Required

**Path Parameters:**
- `rep_id` (string, required): Rep identifier from the `/reps` list endpoint (e.g., `USR3C843ED7AB9B471161CFE46CA61534DB`)

**Query Parameters:**
- `company_id` (string, required, UUID): Company identifier
- `force_refresh` (bool, default: false): Force rebuild even if a cached profile exists
- `window_days` (int, default: 30, range: 7–180): Time window for aggregation

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/reps/USR3C843ED7AB9B471161CFE46CA61534DB/profile?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&force_refresh=true&window_days=30" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "rep_id": "USR3C843ED7AB9B471161CFE46CA61534DB",
  "rep_name": "Diva Shahpur",
  "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
  "window_start": "2026-02-11T12:14:59Z",
  "window_end": "2026-03-13T12:14:59Z",
  "calls_analyzed": 500,
  "top_weaknesses": [
    {
      "category": "Needs Discovery",
      "count": 79,
      "severity_distribution": {"high": 15, "medium": 52, "low": 12},
      "representative_examples": [
        "After the homeowner asked about fascia replacement, the rep gave a vague limitation and did not ask follow-up questions to understand the job.",
        "After the caller identified themselves as a marketing company, the rep did not use a structured solicitation-handling close.",
        "After the homeowner described tiles sliding out, the rep moved into booking without fully diagnosing urgency."
      ],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-03-12T23:59:12Z"
    },
    {
      "category": "Setting Expectations",
      "count": 75,
      "severity_distribution": {"medium": 58, "low": 10, "high": 7},
      "representative_examples": ["..."],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-03-12T23:59:12Z"
    },
    {
      "category": "Follow-Up & Next Steps",
      "count": 67,
      "severity_distribution": {"medium": 45, "high": 12, "low": 10},
      "representative_examples": ["..."],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-03-12T23:09:29Z"
    }
  ],
  "top_strengths": [
    {
      "category": "Greeting & Rapport",
      "count": 113,
      "severity_distribution": {},
      "representative_examples": [
        "Opened with a professional greeting including company name and rep name, then invited the customer to explain the reason for the call."
      ],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-03-12T23:59:12Z"
    }
  ],
  "all_weakness_buckets": ["... (all 15 categories with counts)"],
  "all_strength_buckets": ["... (all categories with counts)"],
  "calculated_at": "2026-03-13T12:38:14Z"
}
```

**Bucket Object Fields:**
- `category` (string): One of 15 canonical categories (e.g., "Needs Discovery", "Closing Technique", "Other")
- `count` (int): Total occurrences across all calls in the time window
- `severity_distribution` (object): `{"high": N, "medium": N, "low": N}` — only present for weaknesses
- `representative_examples` (array): Up to 3 distinct examples (selected by severity and length)
- `related_sop_metrics` (array): SOP metric IDs associated with items in this bucket
- `latest_occurrence` (datetime): Most recent item in this bucket

**Performance Notes:**
- First request with `force_refresh=true` may take 30–60s (LLM classifies items in batches of 50)
- Subsequent requests return cached profile (24h TTL)
- Nightly job at 03:00 UTC rebuilds profiles for reps with recent calls

---

### 7.10 Get Rep Top-3

**Endpoint:** `GET /api/v1/coaching/reps/{rep_id}/top3`

**Description:** Lightweight endpoint returning just the top-3 most frequent coaching strengths and weaknesses. Suitable for dashboards and coaching session creation flows.

**Authentication:** Required

**Path Parameters:**
- `rep_id` (string, required): Rep identifier

**Query Parameters:**
- `company_id` (string, required, UUID): Company identifier

**cURL:**
```bash
curl -X GET "https://ottoai.shunyalabs.ai/api/v1/coaching/reps/USR3C843ED7AB9B471161CFE46CA61534DB/top3?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37" \
  -H "X-API-Key: your_api_key_here"
```

**Response (200 OK):**
```json
{
  "rep_id": "USR3C843ED7AB9B471161CFE46CA61534DB",
  "rep_name": "Diva Shahpur",
  "calls_analyzed": 500,
  "top_weaknesses": [
    {"category": "Needs Discovery", "count": 79, "severity_distribution": {"high": 15, "medium": 52, "low": 12}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:59:12Z"},
    {"category": "Setting Expectations", "count": 75, "severity_distribution": {"medium": 58, "low": 10, "high": 7}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:59:12Z"},
    {"category": "Follow-Up & Next Steps", "count": 67, "severity_distribution": {"medium": 45, "high": 12, "low": 10}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:09:29Z"}
  ],
  "top_strengths": [
    {"category": "Greeting & Rapport", "count": 113, "severity_distribution": {}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:59:12Z"},
    {"category": "Setting Expectations", "count": 63, "severity_distribution": {}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:59:12Z"},
    {"category": "Follow-Up & Next Steps", "count": 59, "severity_distribution": {}, "representative_examples": ["..."], "related_sop_metrics": [], "latest_occurrence": "2026-03-12T23:09:29Z"}
  ],
  "calculated_at": "2026-03-13T12:38:14Z"
}
```

---

### Coaching Workflow Example

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     COACHING WORKFLOW                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  STEP 0: Discover reps and review coaching profiles                      │
│  ─────────────────────────────────────────────────                      │
│  GET /api/v1/coaching/reps?company_id=X   → list rep_ids                │
│  GET /api/v1/coaching/reps/{rep_id}/top3  → top-3 weaknesses/strengths  │
│  GET /api/v1/coaching/reps/{rep_id}/profile → full categorized profile  │
│                                                                          │
│  STEP 1: Manager identifies rep needing coaching                         │
│  ─────────────────────────────────────────────────                      │
│  - Review rep coaching profile (top weaknesses by category)             │
│  - Review weekly insights (needs_coaching list)                         │
│  - Review specific calls showing issues                                 │
│                                                                          │
│  STEP 2: Create Coaching Session                                         │
│  ─────────────────────────────────                                      │
│  POST /api/v1/coaching/sessions                                          │
│  - System auto-calculates baseline from last 5 calls                    │
│  - Sets follow-up period (default 14 days)                              │
│                                                                          │
│  STEP 3: Conduct Coaching (Offline)                                      │
│  ───────────────────────────────────                                    │
│  - Manager coaches rep on focus areas                                   │
│  - Reviews triggering calls together                                    │
│  - Sets expectations                                                    │
│                                                                          │
│  STEP 4: Rep Takes Calls (Follow-up Period)                             │
│  ──────────────────────────────────────────                             │
│  - All calls automatically processed                                    │
│  - Linked to rep via metadata.rep_id                                    │
│                                                                          │
│  STEP 5: System Auto-Measures Impact                                     │
│  ───────────────────────────────────                                    │
│  - Daily background job checks follow-up end dates                      │
│  - Calculates impact when ≥5 calls completed                            │
│  - Extends by 7 days if insufficient calls                              │
│  - Updates session status to "completed" or "insufficient_data"         │
│                                                                          │
│  STEP 6: Review Results                                                  │
│  ─────────────────────                                                  │
│  GET /api/v1/coaching/sessions/{id}/impact                              │
│  - Compare baseline vs current scores                                   │
│  - Check if targets met                                                 │
│  - Identify trend direction                                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Error Response Format

All error responses follow a consistent format:

**Standard Error Response:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**
- `200 OK` - Request succeeded
- `201 Created` - Resource created successfully
- `202 Accepted` - Request accepted for async processing
- `204 No Content` - Request succeeded with no response body
- `400 Bad Request` - Invalid request parameters or body
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource already exists or conflict with current state
- `413 Payload Too Large` - Request body too large
- `422 Unprocessable Entity` - Request validation failed
- `500 Internal Server Error` - Server error
- `501 Not Implemented` - Feature not yet implemented

---

## Rate Limiting

All API endpoints are rate-limited:
- **Default:** 100 requests per minute per API key
- **Burst:** 10 requests per second

Rate limit headers are included in all responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1673539200
```

---

## Webhooks

For async operations (call processing, insights generation, SOP processing), you can provide a `webhook_url` to receive completion notifications.

### Webhook Payload Structure

All webhook payloads follow this base structure:

```json
{
  "job_id": "string",
  "status": "completed|failed",
  "event_type": "call_processing|insight_generation|sop_processing",
  "timestamp": "2026-01-12T15:05:00Z",
  ... (additional event-specific fields)
}
```

### Call Processing Webhook (Completed)

**Endpoint Requirements:**
- Must accept POST requests with `Content-Type: application/json`
- Should return 2xx status code for successful receipt
- Webhook is a lightweight notification - fetch `summary_url` for full details

**Payload Example:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "event_type": "call_processing",
  "timestamp": "2026-01-12T15:05:00Z",
  "call_id": "call_abc123",
  "summary_url": "/api/v1/call-processing/summary/call_abc123",
  "chunks_url": "/api/v1/call-processing/chunks/call_abc123"
}
```

**Note:** The webhook notification is a lightweight notification. To get the full summary with objections, compliance, and qualification data, fetch the `summary_url`.

### Call Processing Webhook (Failed)

**Payload Example:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "event_type": "call_processing",
  "timestamp": "2026-01-12T15:05:00Z",
  "call_id": "call_abc123",
  "error": {
    "message": "Transcription failed: Audio format not supported",
    "type": "TranscriptionError"
  }
}
```

### Insights Generation Webhook (Completed)

**Payload Example:**
```json
{
  "job_id": "insight_job_abc123",
  "status": "completed",
  "event_type": "insight_generation",
  "timestamp": "2026-01-13T00:06:45Z",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "insights_generated": {
    "company": 5,
    "customer": 87,
    "objection": 5
  },
  "companies_processed": 5,
  "results": {
    "company_insights_url": "/api/v1/insights/company/current",
    "customer_insights_url": "/api/v1/insights/customers",
    "objection_insights_url": "/api/v1/insights/objections"
  }
}
```

### Insights Generation Webhook (Failed)

**Payload Example:**
```json
{
  "job_id": "insight_job_abc123",
  "status": "failed",
  "event_type": "insight_generation",
  "timestamp": "2026-01-13T00:06:45Z",
  "error": {
    "message": "Database connection failed",
    "type": "DatabaseError"
  }
}
```

### SOP Processing Webhook (Completed)

**Payload Example:**
```json
{
  "job_id": "sop_job_abc123",
  "status": "completed",
  "event_type": "sop_processing",
  "timestamp": "2026-01-12T16:04:30Z",
  "sop_id": "sop_xyz123abc456",
  "sop_name": "Sales Call Standard Operating Procedure",
  "sop_type": "call_script",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "target_role": "sales_rep",
  "is_company_wide": false,
  "results": {
    "metrics_extracted": 12,
    "chunks_indexed": 24,
    "page_count": 15,
    "word_count": 3450
  }
}
```

### SOP Processing Webhook (Failed)

**Payload Example:**
```json
{
  "job_id": "sop_job_abc123",
  "status": "failed",
  "event_type": "sop_processing",
  "timestamp": "2026-01-12T16:04:30Z",
  "sop_id": "sop_xyz123abc456",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "error": {
    "message": "Failed to extract text from PDF",
    "type": "DocumentParsingError",
    "code": "PROCESSING_ERROR"
  }
}
```

### Important Notes About Webhooks

1. **Webhook Payload is Lightweight:** The webhook only notifies you of completion. It does NOT include the full summary data. Use the provided URLs to fetch complete data:
   - `summary_url`: Full call summary with objections, compliance, qualification
   - `chunks_url`: Chunk-level summaries for semantic search
   - `insights_url`: Company or customer insights
   - `sop_url`: SOP document details

2. **Objections Data Format:** When you fetch the summary via `summary_url`, the objections field is an array of rich objects. See the "Get Call Summary" endpoint documentation for the complete structure. Do NOT expect simple strings.

3. **Webhook Timeout:** Webhooks have a 10-second timeout. If your endpoint takes longer to process, return a 2xx status immediately and process asynchronously.

4. **Retry Policy:** Failed webhooks are NOT automatically retried. Ensure your endpoint is reliable or implement status polling as a fallback.

### Webhook Security

- All webhook requests include `User-Agent: Otto-Intelligence-Webhook/1.0`
- Requests timeout after 10 seconds
- Failed webhooks (4xx, 5xx, timeout) are logged but not retried
---

## Complete Workflow Guide

### Setting Up a New Tenant

**Important: UUID Format Requirement**
All ID fields must be valid UUIDs. Generate UUIDs using your preferred method (e.g., `uuidgen` command, programming language UUID libraries, etc.).

**Step 1: Create Tenant Configuration** (Optional but Recommended)
```bash
POST /api/v1/tenant-config/
{
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "company_name": "Arizona Roofers Inc.",
  "qualification_thresholds": {...},
  "service_prioritization": {...},
  "custom_keywords": {...}
}
```

**Step 2: Upload CSR SOP**
```bash
POST /api/v1/sop/documents/upload
- file: csr_phone_sop.pdf
- company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
- target_role: "customer_rep"
```

**Step 3: Upload Sales Rep SOP**
```bash
POST /api/v1/sop/documents/upload
- file: sales_meeting_sop.pdf
- company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
- target_role: "sales_rep"
```

**Step 4: Process Calls**

For CSR phone calls:
```bash
POST /api/v1/call-processing/process
{
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rep_role": "customer_rep",
  "phone_number": "+14155551234",
  "audio_url": "https://s3.amazonaws.com/bucket/call.mp3",
  "metadata": {
    "rep_id": "sarah_jones",
    "rep_name": "Sarah Jones"
  }
}
```

For sales rep meetings:
```bash
POST /api/v1/call-processing/process
{
  "call_id": "550e8400-e29b-41d4-a716-446655440001",
  "company_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rep_role": "sales_rep",
  "phone_number": "+14155559876",
  "audio_url": "https://s3.amazonaws.com/bucket/call.mp3",
  "metadata": {
    "rep_id": "mike_chen",
    "rep_name": "Mike Chen",
    "team": "field_sales"
  }
}
```

**IMPORTANT: rep_id and rep_name are REQUIRED in metadata for:**
- Agent Progression Tracking
- Coaching Impact Measurement
- Weekly Insights (top performers, needs coaching)
- Per-rep analytics and dashboards

### Key Requirements

**UUID Format:**
- **Required UUID fields:** Only `company_id` must be a valid UUID
- **Flexible ID fields:** `call_id`, `conversation_id`, `sop_id`, `user_id` can be UUIDs or any string format
- UUID Format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- Non-UUID values for `company_id` will be rejected with a `400 Bad Request` error

**company_id Consistency:**
- The same `company_id` (UUID) must be used across:
  - Tenant configuration creation
  - SOP uploads
  - Call processing requests
- This is how the system links SOPs and configurations to calls

**rep_role and target_role Matching:**
- SOP `target_role` must match call processing `rep_role`
- For phone calls: `target_role: "customer_rep"` and `rep_role: "customer_rep"`
- For in-person: `target_role: "sales_rep"` and `rep_role: "sales_rep"`

**Duplicate Call Prevention:**
- By default, the same `call_id` cannot be processed twice
- Set `"allow_reprocess": true` to force reprocessing of an existing call
- This prevents accidental duplicate processing and costs

**Example Flow:**

```
1. Upload CSR SOP
   company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
   target_role: "customer_rep"
   ↓
2. Upload Sales SOP
   company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
   target_role: "sales_rep"
   ↓
3. Create Tenant Config
   company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
   (service prioritization, keywords, etc.)
   ↓
4. Process Phone Call
   call_id: "550e8400-e29b-41d4-a716-446655440000"
   company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
   rep_role: "customer_rep"
   metadata.rep_id: "sarah_jones"      ← REQUIRED
   metadata.rep_name: "Sarah Jones"    ← REQUIRED
   → System uses CSR SOP + Tenant Config
   → Auto-calculates lead score
   → Auto-detects conversation phases
   ↓
5. Process Sales Meeting
   call_id: "550e8400-e29b-41d4-a716-446655440001"
   company_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
   rep_role: "sales_rep"
   metadata.rep_id: "mike_chen"        ← REQUIRED
   metadata.rep_name: "Mike Chen"      ← REQUIRED
   → System uses Sales SOP + Tenant Config
   ↓
6. Track Agent Progression
   GET /api/v1/insights/agents/sarah_jones/progression
   → Weekly metrics, trends, anomalies
   ↓
7. Create Coaching Session (when needed)
   POST /api/v1/coaching/sessions
   rep_id: "sarah_jones"
   → Auto-calculates baseline, tracks follow-up
   ↓
8. Get Coaching Impact
   GET /api/v1/coaching/sessions/{id}/impact
   → Measure improvement vs baseline
```

### Home Services Context

The system is optimized for home services industries (roofing, plumbing, electrical, HVAC). It automatically:
- Captures property details (roof type, age, HOA, solar, pets, etc.)
- Understands industry-specific terminology
- Recognizes service prioritization (replacements vs. repairs)
- Handles regional keywords (e.g., "monsoon season" in Arizona)

### Call Outcome Categories

The system automatically determines call outcomes based on scope classification, qualification, booking status, and a 5-rule priority cascade:

| Outcome | Description |
|---------|-------------|
| `qualified_and_booked` | Customer qualified and appointment scheduled |
| `qualified_but_unbooked` | Customer meets criteria but no appointment yet |
| `qualified_but_deprioritized` | Customer qualifies but company deferred due to capacity/backlog (has `deferred_reason`) |
| `qualified_service_not_offered` | Customer qualifies but service not available in their area |
| `follow_up_inquiry` | Existing customer following up on their job |
| `existing_customer_service` | Service-related call from existing customer |
| `unqualified` | OUT_OF_SCOPE calls, or cold/unqualified leads without booked appointment |

**5-Rule Cross-Validation Cascade** (priority order):
1. OUT_OF_SCOPE → force `unqualified`
2. `appointment_confirmed=true` → `qualified_and_booked`
3. `deferred_reason` populated → `qualified_but_deprioritized`
4. `service_not_offered_reason` populated → `qualified_service_not_offered`
5. Unqualified/cold without appointment → `unqualified`

---

## Support

For API support and questions:
- **Documentation:** https://ottoai.shunyalabs.ai/docs
- **Email:** support@shunyalabs.ai
