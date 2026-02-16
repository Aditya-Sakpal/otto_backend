# Feature 2: Weekly Insights Engine API

**Version:** 4.0  
**Date:** February 4, 2026  
**Service:** Independent Microservice Architecture  
**Implementation:** APScheduler + FastAPI BackgroundTasks

> **Last Updated:** February 2026 - Added Lead Scoring endpoints, enhanced insight headings with action items, integrated Agent Progression tracking (Feature 8).

---

## Overview

The Weekly Insights Engine provides automated analytics and actionable intelligence through both scheduled background jobs and REST API endpoints. The feature uses **APScheduler AsyncIOScheduler** for in-process scheduling and **FastAPI BackgroundTasks** for on-demand API-triggered generation.

**Implementation Status**: ✅ **Fully Implemented** - No Celery required, runs within FastAPI application.

### Key Enhancements (v4.0)

| Enhancement | Description |
|-------------|-------------|
| **Insight Headings** | All insights include 3-5 word headings + concise insights with action items |
| **Lead Scoring Endpoints** | Full lead filtering, distribution stats, and history tracking |
| **Agent Progression** | Weekly metrics, trend detection, anomaly detection, peer comparison |
| **Customer Engagement Scoring** | Multi-factor engagement score (frequency + history + sentiment) |
| **Enhanced Objection Analysis** | Best response extraction, severity breakdown, category insights, sub_objection breakdown with Jaccard similarity grouping |
| **Priority Calculation** | HIGH/MEDIUM/LOW based on status, activity, sentiment, pending actions |

### Key Changes from Original Architecture

| Aspect | Original (Embedded) | Current (API-Driven + In-Process Scheduler) |
|--------|---------------------|---------------------------------------------|
| **Scheduled Trigger** | Celery Beat (separate process) | APScheduler AsyncIOScheduler (in-process, runs with FastAPI) |
| **On-Demand Trigger** | N/A | REST API + FastAPI BackgroundTasks |
| **Status Check** | Internal logging | REST API polling endpoint |
| **Storage** | PostgreSQL | MongoDB |
| **Locking** | PostgreSQL row locks | Redis distributed locks |
| **Multi-tenancy** | Company filtering | MongoDB company_id + partitioning |
| **Deployment** | Requires separate Celery worker + Beat | Single FastAPI process with embedded scheduler |

### Scheduler Architecture

The weekly insights generation runs via **APScheduler's AsyncIOScheduler**:

- **Automatic Scheduling**: Runs every Sunday at 00:00 UTC automatically
- **In-Process**: Scheduler runs within the FastAPI application (no separate worker needed)
- **On-Demand API**: Can also be triggered manually via REST API
- **Status Monitoring**: `GET /api/v1/scheduler/status` endpoint for job visibility

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCHEDULER ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 FastAPI Application                      │   │
│  │                                                          │   │
│  │  ┌──────────────────┐    ┌──────────────────────────┐   │   │
│  │  │  APScheduler     │    │  REST API Endpoints      │   │   │
│  │  │  (AsyncIO)       │    │                          │   │   │
│  │  │                  │    │  POST /insights/generate │   │   │
│  │  │  Sunday 00:00 ──────► │  GET /insights/status    │   │   │
│  │  │  UTC             │    │  GET /scheduler/status   │   │   │
│  │  └────────┬─────────┘    └────────────┬─────────────┘   │   │
│  │           │                           │                  │   │
│  │           └───────────┬───────────────┘                  │   │
│  │                       ▼                                  │   │
│  │           ┌──────────────────────────┐                   │   │
│  │           │  FastAPI BackgroundTasks │                   │   │
│  │           │  (Async Processing)      │                   │   │
│  │           └──────────────────────────┘                   │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WEEKLY INSIGHTS ENGINE - API FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │          TWO TRIGGER METHODS (Both supported)                        │   │
│  │                                                                      │   │
│  │   1. AUTOMATIC (APScheduler):                                        │   │
│  │      - Runs every Sunday at 00:00 UTC                                │   │
│  │      - In-process scheduler (no external cron needed)                │   │
│  │      - Automatically processes all companies                         │   │
│  │                                                                      │   │
│  │   2. ON-DEMAND (REST API):                                           │   │
│  │      - POST /api/v1/insights/generate                                │   │
│  │      - Can target specific companies/date ranges                     │   │
│  │      - Supports webhook callbacks                                    │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │    POST /api/v1/insights/generate (On-Demand)                        │   │
│  │                                                                      │   │
│  │    Request:                                                          │   │
│  │    {                                                                 │   │
│  │      "week_start": "2026-01-06",  // Optional, defaults to last week │   │
│  │      "week_end": "2026-01-12",                                       │   │
│  │      "company_ids": ["acme_roofing", "xyz_solar"],  // Optional      │   │
│  │      "insight_types": ["company", "customer", "objection"],          │   │
│  │      "webhook_url": "https://otto-backend.com/webhooks/insights"     │   │
│  │    }                                                                 │   │
│  │                                                                      │   │
│  │    Response (202 Accepted):                                          │   │
│  │    {                                                                 │   │
│  │      "job_id": "insight_job_abc123",                                 │   │
│  │      "status": "queued",                                             │   │
│  │      "week_start": "2026-01-06",                                     │   │
│  │      "week_end": "2026-01-12",                                       │   │
│  │      "estimated_duration": "5-10 minutes",                           │   │
│  │      "status_url": "/api/v1/insights/status/insight_job_abc123",    │   │
│  │      "queued_at": "2026-01-13T00:00:05Z"                            │   │
│  │    }                                                                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     REDIS JOB STATUS TRACKING                        │   │
│  │                                                                      │   │
│  │  Key: insight_job:{job_id}:status                                    │   │
│  │  Value: {"status": "queued", "progress": {...}}                      │   │
│  │  TTL: 604800 seconds (7 days)                                        │   │
│  │                                                                      │   │
│  │  Purpose: Track job progress and enable status polling               │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               FASTAPI BACKGROUND TASK (Async Processing)             │   │
│  │                                                                      │   │
│  │  BackgroundTasks.add_task() → Updates Redis status                  │   │
│  │                                                                      │   │
│  │  insight_job:{job_id}:status → {                                     │   │
│  │    "status": "processing",                                           │   │
│  │    "progress": {"percent": 0, "step": "initializing"}                │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              STEP 1: IDENTIFY ACTIVE COMPANIES                       │   │
│  │                                                                      │   │
│  │  MongoDB Query:                                                      │   │
│  │  db.calls.distinct("company_id", {                                   │   │
│  │    call_date: {$gte: week_start, $lte: week_end}                     │   │
│  │  })                                                                  │   │
│  │                                                                      │   │
│  │  Result: ["acme_roofing", "xyz_solar", "best_hvac"]                  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│            Update Redis: {"progress": {"percent": 10, "step": "companies"}} │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │           STEP 2: PARALLEL INSIGHT GENERATION                        │   │
│  │                                                                      │   │
│  │  For each company, spawn parallel tasks:                             │   │
│  │                                                                      │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │   │
│  │  │   COMPANY      │  │   CUSTOMER     │  │   OBJECTION    │         │   │
│  │  │   INSIGHTS     │  │   INSIGHTS     │  │   INSIGHTS     │         │   │
│  │  │                │  │                │  │                │         │   │
│  │  │ • Total calls  │  │ • Per-customer │  │ • Per-category │         │   │
│  │  │ • Booking rate │  │ • Call count   │  │ • Overcome rate│         │   │
│  │  │ • Avg duration │  │ • Status change│  │ • Trend analysis│        │   │
│  │  │ • Top reps     │  │ • Pending acts │  │ • Best responses│        │   │
│  │  │ • Compliance   │  │ • Sentiment    │  │                │         │   │
│  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘         │   │
│  └──────────┼───────────────────┼───────────────────┼──────────────────┘   │
│             │                   │                   │                       │
│             └───────────────────┴───────────────────┘                       │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                  COMPANY INSIGHT GENERATION                          │   │
│  │                                                                      │   │
│  │  MongoDB Aggregation Pipeline:                                       │   │
│  │  1. Match calls in date range for company                            │   │
│  │  2. Lookup call_summaries                                            │   │
│  │  3. Group by metrics:                                                │   │
│  │     - COUNT(*) as total_calls                                        │   │
│  │     - COUNT(booking_status='booked') as booked_calls                 │   │
│  │     - AVG(duration) as avg_duration                                  │   │
│  │     - AVG(compliance.score) as avg_compliance                        │   │
│  │     - AVG(sentiment_score) as avg_sentiment                          │   │
│  │  4. Week-over-week comparison (query previous week)                  │   │
│  │  5. Top performers (group by rep, sort by booking_rate DESC)         │   │
│  │                                                                      │   │
│  │  Store in MongoDB:                                                   │   │
│  │  {                                                                   │   │
│  │    _id: ObjectId,                                                    │   │
│  │    insight_type: "company",                                          │   │
│  │    company_id: "acme_roofing",                                       │   │
│  │    week_start: ISODate("2026-01-06"),                                │   │
│  │    week_end: ISODate("2026-01-12"),                                  │   │
│  │    data: {                                                           │   │
│  │      total_calls: 145,                                               │   │
│  │      total_booked: 87,                                               │   │
│  │      booking_rate: 0.60,                                             │   │
│  │      avg_duration: 420.5,                                            │   │
│  │      avg_compliance: 0.82,                                           │   │
│  │      avg_sentiment: 0.65,                                            │   │
│  │      top_performers: [...],                                          │   │
│  │      week_over_week: {                                               │   │
│  │        booking_rate_change: +0.05,                                   │   │
│  │        calls_change: +12                                             │   │
│  │      }                                                               │   │
│  │    },                                                                │   │
│  │    generated_at: ISODate("2026-01-13T00:05:30Z"),                    │   │
│  │    status: "completed"                                               │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                 CUSTOMER INSIGHT GENERATION                          │   │
│  │                                                                      │   │
│  │  MongoDB Aggregation Pipeline:                                       │   │
│  │  1. Match calls in date range for company                            │   │
│  │  2. Group by customer_id                                             │   │
│  │  3. Calculate per-customer metrics:                                  │   │
│  │     - Call count this week                                           │   │
│  │     - Total calls (historical)                                       │   │
│  │     - Current qualification status                                   │   │
│  │     - Status changes                                                 │   │
│  │     - Sentiment trend                                                │   │
│  │     - Pending actions count                                          │   │
│  │  4. Generate recommendations:                                        │   │
│  │     - "Follow up - 2 pending actions overdue"                        │   │
│  │     - "High priority - sentiment declining"                          │   │
│  │     - "Ready to close - warm status + 3 calls"                       │   │
│  │                                                                      │   │
│  │  Store in MongoDB (one doc per customer):                            │   │
│  │  {                                                                   │   │
│  │    _id: ObjectId,                                                    │   │
│  │    insight_type: "customer",                                         │   │
│  │    company_id: "acme_roofing",                                       │   │
│  │    customer_id: ObjectId("..."),                                     │   │
│  │    phone_number: "+14805551234",                                     │   │
│  │    week_start: ISODate("2026-01-06"),                                │   │
│  │    data: {                                                           │   │
│  │      calls_this_week: 2,                                             │   │
│  │      total_calls: 5,                                                 │   │
│  │      current_status: "warm",                                         │   │
│  │      status_changed: false,                                          │   │
│  │      sentiment_trend: "stable",                                      │   │
│  │      pending_actions: 1,                                             │   │
│  │      overdue_actions: 0,                                             │   │
│  │      recommendation: "Schedule follow-up call"                       │   │
│  │    },                                                                │   │
│  │    generated_at: ISODate("2026-01-13T00:08:15Z"),                    │   │
│  │    status: "completed"                                               │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                OBJECTION INSIGHT GENERATION                          │   │
│  │                                                                      │   │
│  │  MongoDB Aggregation Pipeline:                                       │   │
│  │  1. Match calls in date range for company                            │   │
│  │  2. Lookup objections from call_summaries                            │   │
│  │  3. Unwind objections array                                          │   │
│  │  4. Group by category_id:                                            │   │
│  │     - COUNT(*) as total_count                                        │   │
│  │     - COUNT(overcome=true) as overcome_count                         │   │
│  │     - overcome_rate = overcome_count / total_count                   │   │
│  │     - Group severity: {low: n, medium: n, high: n}                   │   │
│  │  5. Week-over-week trend:                                            │   │
│  │     - Compare with previous week counts                              │   │
│  │     - Calculate trend: "increasing", "decreasing", "stable"          │   │
│  │  6. Find best responses (overcome=true, high confidence)             │   │
│  │                                                                      │   │
│  │  Store in MongoDB (one doc per category):                            │   │
│  │  {                                                                   │   │
│  │    _id: ObjectId,                                                    │   │
│  │    insight_type: "objection",                                        │   │
│  │    company_id: "acme_roofing",                                       │   │
│  │    week_start: ISODate("2026-01-06"),                                │   │
│  │    data: {                                                           │   │
│  │      category_id: 2,                                                 │   │
│  │      category_text: "Timing",                                        │   │
│  │      total_count: 23,                                                │   │
│  │      overcome_count: 15,                                             │   │
│  │      overcome_rate: 0.65,                                            │   │
│  │      severity_breakdown: {low: 5, medium: 15, high: 3},              │   │
│  │      trend_direction: "stable",                                      │   │
│  │      trend_pct: -0.02,                                               │   │
│  │      best_responses: [                                               │   │
│  │        {                                                             │   │
│  │          rep: "Travis",                                              │   │
│  │          response: "Suggested alternatives...",                      │   │
│  │          outcome: "overcome"                                         │   │
│  │        }                                                             │   │
│  │      ],                                                              │   │
│  │      sub_objection_breakdown: [  // Only for category_id=9           │   │
│  │        {                                                             │   │
│  │          sub_objection: "Trust/Quality Concern",                     │   │
│  │          count: 5,                                                   │   │
│  │          overcome_count: 2,                                          │   │
│  │          overcome_rate: 0.4                                          │   │
│  │        }                                                             │   │
│  │      ]  // Uses Jaccard word similarity to group similar labels      │   │
│  │    },                                                                │   │
│  │    generated_at: ISODate("2026-01-13T00:12:45Z"),                    │   │
│  │    status: "completed"                                               │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│         Update Redis: {"progress": {"percent": 90, "step": "finalizing"}}  │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                STEP 3: FINALIZE & CACHE RESULTS                      │   │
│  │                                                                      │   │
│  │  1. Mark all insights as "completed" in MongoDB                      │   │
│  │  2. Cache aggregated results in Redis:                               │   │
│  │     - insights:current:{company_id} → Latest insights                │   │
│  │     - TTL: 7 days                                                    │   │
│  │  3. Update job status in Redis to "completed"                        │   │
│  │  4. Release distributed lock                                         │   │
│  │  5. Send webhook callback (if provided)                              │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              OPTIONAL: WEBHOOK CALLBACK                              │   │
│  │                                                                      │   │
│  │  POST https://otto-backend.com/webhooks/insights                     │   │
│  │  {                                                                   │   │
│  │    "job_id": "insight_job_abc123",                                   │   │
│  │    "status": "completed",                                            │   │
│  │    "week_start": "2026-01-06",                                       │   │
│  │    "week_end": "2026-01-12",                                         │   │
│  │    "companies_processed": 3,                                         │   │
│  │    "insights_generated": {                                           │   │
│  │      "company": 3,                                                   │   │
│  │      "customer": 47,                                                 │   │
│  │      "objection": 30                                                 │   │
│  │    },                                                                │   │
│  │    "duration_seconds": 845,                                          │   │
│  │    "completed_at": "2026-01-13T00:14:10Z"                            │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Trigger Insight Generation

**Endpoint:** `POST /api/v1/insights/generate`

**Description:** Trigger weekly insight generation for all or specific companies. Designed to be called by external cron jobs.

**Request Headers:**
```http
X-API-Key: {api_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "company_ids": ["acme_roofing", "xyz_solar"],
  "insight_types": ["company", "customer", "objection"],
  "webhook_url": "https://otto-backend.com/webhooks/insights",
  "options": {
    "force_regenerate": false,
    "include_inactive_customers": false
  }
}
```

**Field Descriptions:**
- `week_start` (optional): Start date of week (defaults to last Monday)
- `week_end` (optional): End date of week (defaults to last Sunday)
- `company_ids` (optional): Specific companies to generate for (defaults to all active)
- `insight_types` (optional): Types to generate (defaults to all three)
- `webhook_url` (optional): Callback URL when generation completes
- `options.force_regenerate` (optional): Regenerate even if exists (default false)

**Response (202 Accepted):**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "queued",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "company_count": 3,
  "insight_types": ["company", "customer", "objection"],
  "estimated_duration": "15-20 minutes",
  "status_url": "/api/v1/insights/status/insight_job_abc123def456",
  "queued_at": "2026-01-13T00:00:05Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid date range or parameters
- `401 Unauthorized` - Invalid or missing API key
- `409 Conflict` - Generation already in progress for this week
- `500 Internal Server Error` - Server error

---

### 2. Check Generation Status

**Endpoint:** `GET /api/v1/insights/status/{job_id}`

**Description:** Poll the status of insight generation job. Cron jobs should poll this endpoint periodically.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (200 OK) - Processing:**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "processing",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "progress": {
    "percent": 45,
    "current_step": "customer_insights",
    "companies_processed": 1,
    "companies_total": 3,
    "insights_generated": {
      "company": 1,
      "customer": 15,
      "objection": 10
    }
  },
  "started_at": "2026-01-13T00:00:10Z",
  "updated_at": "2026-01-13T00:06:30Z",
  "estimated_completion": "2026-01-13T00:15:00Z"
}
```

**Response (200 OK) - Completed:**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "completed",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "progress": {
    "percent": 100,
    "current_step": "completed",
    "companies_processed": 3,
    "companies_total": 3,
    "insights_generated": {
      "company": 3,
      "customer": 47,
      "objection": 30
    }
  },
  "started_at": "2026-01-13T00:00:10Z",
  "completed_at": "2026-01-13T00:14:10Z",
  "duration_seconds": 840,
  "results": {
    "company_insights_url": "/api/v1/insights/company/current",
    "customer_insights_url": "/api/v1/insights/customers",
    "objection_insights_url": "/api/v1/insights/objections"
  }
}
```

**Response (200 OK) - Failed:**
```json
{
  "job_id": "insight_job_abc123def456",
  "status": "failed",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "progress": {
    "percent": 30,
    "current_step": "company_insights",
    "companies_processed": 1,
    "companies_total": 3
  },
  "started_at": "2026-01-13T00:00:10Z",
  "failed_at": "2026-01-13T00:05:30Z",
  "error": {
    "code": "MONGODB_QUERY_ERROR",
    "message": "Failed to aggregate company metrics",
    "company_id": "acme_roofing",
    "details": "Connection timeout"
  },
  "retry_available": true,
  "retry_url": "/api/v1/insights/retry/insight_job_abc123def456"
}
```

---

### 3. Get Current Week Company Insights

**Endpoint:** `GET /api/v1/insights/company/{company_id}/current`

**Description:** Retrieve the most recent weekly insights for a company.

**Request Headers:**
```http
X-API-Key: {api_key}
```

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "data": {
    "total_calls": 145,
    "total_booked": 87,
    "booking_rate": 0.60,
    "avg_call_duration": 420.5,
    "avg_compliance_score": 0.82,
    "avg_sentiment_score": 0.65,
    "avg_qualification_score": 0.71,
    "top_performers": [
      {
        "rep_id": "rep_123",
        "rep_name": "Travis",
        "calls": 35,
        "booked": 25,
        "booking_rate": 0.71,
        "avg_compliance": 0.90
      },
      {
        "rep_id": "rep_456",
        "rep_name": "Sarah",
        "calls": 40,
        "booked": 26,
        "booking_rate": 0.65,
        "avg_compliance": 0.85
      }
    ],
    "needs_coaching": [
      {
        "rep_id": "rep_789",
        "rep_name": "John",
        "calls": 25,
        "booked": 10,
        "booking_rate": 0.40,
        "issues": ["Low compliance score", "Missing qualification questions"]
      }
    ],
    "top_insight": "Booking rate increased 5% week-over-week driven by improved objection handling",
    "recommendation": "Focus coaching on timing objections - 40% of missed bookings cite timeline concerns",
    "trends": {
      "booking_rate": "up",
      "calls": "stable",
      "compliance": "up",
      "sentiment": "stable"
    },
    "week_over_week": {
      "booking_rate_change": +0.05,
      "calls_change": +12,
      "compliance_change": +0.03,
      "sentiment_change": +0.01
    }
  },
  "generated_at": "2026-01-13T00:05:30Z"
}
```

---

### 4. Get Specific Week Insights

**Endpoint:** `GET /api/v1/insights/company/{company_id}/week/{week_start}`

**Description:** Retrieve insights for a specific week.

**Path Parameters:**
- `company_id`: Company identifier
- `week_start`: Week start date (YYYY-MM-DD)

**Response:** Same structure as current week endpoint

---

### 5. Get Customer Insights

**Endpoint:** `GET /api/v1/insights/customer/{customer_id}`

**Description:** Retrieve weekly insights for a specific customer.

**Query Parameters:**
- `week_start` (optional): Specific week (defaults to current week)

**Response (200 OK):**
```json
{
  "customer_id": "cust_123",
  "company_id": "acme_roofing",
  "phone_number": "+14805551234",
  "customer_name": "Kevin",
  "week_start": "2026-01-06",
  "data": {
    "calls_this_week": 2,
    "total_calls": 5,
    "current_status": "warm",
    "status_changed": false,
    "sentiment_trend": "stable",
    "engagement_score": 0.75,
    "pending_actions": 1,
    "overdue_actions": 0,
    "last_call_date": "2026-01-10T14:30:00Z",
    "next_recommended_action": "Follow-up call to address timeline concerns",
    "priority": "medium"
  },
  "generated_at": "2026-01-13T00:08:15Z"
}
```

---

### 6. Get All Customer Insights

**Endpoint:** `GET /api/v1/insights/customers`

**Description:** Retrieve all customer insights for a company and week.

**Query Parameters:**
- `company_id` (required): Company identifier
- `week_start` (optional): Week start date (defaults to current week)
- `status` (optional): Filter by qualification status
- `priority` (optional): Filter by priority (high, medium, low)
- `page` (optional): Page number (default 1)
- `limit` (optional): Results per page (default 50, max 200)

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "week_start": "2026-01-06",
  "total_customers": 47,
  "page": 1,
  "limit": 50,
  "customers": [
    {
      "customer_id": "cust_123",
      "phone_number": "+14805551234",
      "customer_name": "Kevin",
      "data": {
        "calls_this_week": 2,
        "current_status": "warm",
        "sentiment_trend": "stable",
        "pending_actions": 1,
        "priority": "medium"
      }
    },
    // ... more customers
  ]
}
```

---

### 7. Get Objection Insights

**Endpoint:** `GET /api/v1/insights/objections/{company_id}`

**Description:** Retrieve objection insights for a company.

**Query Parameters:**
- `week_start` (optional): Specific week (defaults to current week)
- `category_id` (optional): Filter by objection category (1-10)

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "week_start": "2026-01-06",
  "total_categories": 10,
  "objections": [
    {
      "category_id": 2,
      "category_text": "Timing",
      "total_count": 23,
      "overcome_count": 15,
      "overcome_rate": 0.65,
      "severity_breakdown": {
        "low": 5,
        "medium": 15,
        "high": 3
      },
      "trend_direction": "stable",
      "trend_pct": -0.02,
      "insight_heading": "Timing Concerns Stable",
      "insight": "Timing objections remain consistent. Overcome rate of 65% is above average. Action: Continue current approach, share best practices with lower performers.",
      "recommendation_heading": "Best Practices",
      "recommendation": "Top performers address timing by proactively offering alternatives. Train team on this approach.",
      "best_responses": [
        {
          "rep": "Travis",
          "call_id": "5002",
          "objection": "7 to 9 weeks is a long time",
          "response": "Offered alternative local contractor suggestion",
          "outcome": "overcome",
          "confidence": 0.8
        }
      ],
      "sub_objection_breakdown": []
    },
    {
      "category_id": 9,
      "category_text": "Other",
      "total_count": 8,
      "overcome_count": 3,
      "overcome_rate": 0.375,
      "severity_breakdown": {
        "low": 2,
        "medium": 5,
        "high": 1
      },
      "trend_direction": "increasing",
      "trend_pct": 0.15,
      "insight_heading": "Uncategorized Objections Rising",
      "insight": "Other category objections increased 15%. Sub-objection breakdown reveals Trust/Quality Concern as dominant.",
      "recommendation_heading": "Address Quality Concerns",
      "recommendation": "Consider adding Trust/Quality as a dedicated category if trend continues.",
      "best_responses": [],
      "sub_objection_breakdown": [
        {
          "sub_objection": "Trust/Quality Concern",
          "count": 5,
          "overcome_count": 2,
          "overcome_rate": 0.4
        },
        {
          "sub_objection": "Unwanted solicitation / Do not call",
          "count": 3,
          "overcome_count": 1,
          "overcome_rate": 0.33
        }
      ]
    }
  ],
  "generated_at": "2026-01-13T00:12:45Z"
}
```

---

### 8. Lead Scoring Endpoints (NEW)

#### 8.1 Get Leads with Filtering

**Endpoint:** `GET /api/v1/insights/leads`

**Description:** Get leads filtered by band, score range, and timeframe.

**Query Parameters:**
- `company_id` (required): Company identifier
- `band` (optional): Filter by lead band ("hot", "warm", "cold")
- `min_score` (optional): Minimum lead score (0-100)
- `max_score` (optional): Maximum lead score (0-100)
- `timeframe_days` (optional): Limit to calls within N days (default: 30)
- `page` (optional): Page number (default: 1)
- `limit` (optional): Results per page (default: 50, max: 200)

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "total": 45,
  "page": 1,
  "limit": 50,
  "leads": [
    {
      "call_id": "5002",
      "customer_phone": "+14805551234",
      "customer_name": "Kevin",
      "lead_score": {
        "total_score": 82,
        "lead_band": "hot",
        "confidence": "high"
      },
      "call_date": "2026-01-08T10:30:00Z",
      "qualification_status": "warm",
      "booking_status": "not_booked"
    }
  ]
}
```

#### 8.2 Lead Score Distribution

**Endpoint:** `GET /api/v1/insights/leads/distribution`

**Description:** Get lead score distribution statistics.

**Query Parameters:**
- `company_id` (required): Company identifier
- `timeframe_days` (optional): Analysis period (default: 30)

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "timeframe_days": 30,
  "total_leads": 145,
  "distribution": {
    "hot": 32,
    "warm": 67,
    "cold": 46
  },
  "percentiles": {
    "p25": 42,
    "p50": 58,
    "p75": 76,
    "p90": 85
  },
  "average_score": 56.3
}
```

#### 8.3 Lead Score History

**Endpoint:** `GET /api/v1/insights/leads/{customer_id}/history`

**Description:** Track lead score changes over time for a customer.

**Query Parameters:**
- `company_id` (required): Company identifier

**Response (200 OK):**
```json
{
  "customer_id": "cust_123",
  "customer_phone": "+14805551234",
  "company_id": "acme_roofing",
  "total_calls": 5,
  "score_history": [
    {
      "call_id": "4998",
      "call_date": "2026-01-02",
      "total_score": 45,
      "lead_band": "cold"
    },
    {
      "call_id": "5002",
      "call_date": "2026-01-08",
      "total_score": 72,
      "lead_band": "warm"
    }
  ],
  "trend": "improving",
  "score_change": 27
}
```

---

### 9. Agent Progression Endpoints

#### 9.1 Get Agent Progression

**Endpoint:** `GET /api/v1/insights/agents/{rep_id}/progression`

**Description:** Track agent metrics over time with trend and anomaly detection.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `weeks` | int | No | Number of weeks to analyze (default: 8) |
| `metrics` | string | No | Comma-separated metrics to include |

**Available Metrics:**
- `compliance_score`, `booking_rate`, `qualification_score`
- `sentiment_score`, `lead_score`, `objection_handling`
- `budget`, `authority`, `need`, `timeline` (BANT)

**Response (200 OK):**
```json
{
  "rep_id": "john_smith",
  "company_id": "acme_roofing",
  "period": {
    "start": "2025-12-09",
    "end": "2026-02-03",
    "weeks_analyzed": 8
  },
  "metrics": {
    "compliance_score": {
      "current": 0.85,
      "trend": "improving",
      "trend_pct": 0.12,
      "weekly_values": [0.72, 0.75, 0.78, 0.80, 0.82, 0.83, 0.84, 0.85],
      "anomalies": []
    },
    "booking_rate": {
      "current": 0.45,
      "trend": "stable",
      "trend_pct": 0.02,
      "weekly_values": [0.42, 0.44, 0.43, 0.45, 0.44, 0.45, 0.44, 0.45],
      "anomalies": []
    }
  },
  "overall_trend": "improving",
  "confidence": "high",
  "total_calls": 87
}
```

---

#### 9.2 Get Peer Comparison

**Endpoint:** `GET /api/v1/insights/agents/{rep_id}/peer-comparison`

**Description:** Compare agent performance against peers (on-demand calculation).

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `metric` | string | No | Specific metric to compare (default: all) |
| `period_days` | int | No | Analysis period in days (default: 30) |

**Response (200 OK):**
```json
{
  "rep_id": "john_smith",
  "company_id": "acme_roofing",
  "period_days": 30,
  "peer_count": 12,
  "comparisons": {
    "compliance_score": {
      "agent_value": 0.85,
      "rank": 2,
      "percentile": 92,
      "peer_average": 0.72,
      "peer_median": 0.74,
      "peer_min": 0.55,
      "peer_max": 0.88
    },
    "booking_rate": {
      "agent_value": 0.45,
      "rank": 5,
      "percentile": 65,
      "peer_average": 0.42,
      "peer_median": 0.43,
      "peer_min": 0.25,
      "peer_max": 0.62
    }
  },
  "strengths": ["compliance_score", "sentiment_score"],
  "improvement_areas": ["closing", "objection_handling"]
}
```

---

#### 9.3 Get Agents Summary

**Endpoint:** `GET /api/v1/insights/agents/summary`

**Description:** Manager dashboard view showing all agents' current performance.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `company_id` | string | Yes | Company identifier |
| `period_days` | int | No | Analysis period (default: 30) |
| `sort_by` | string | No | Sort field (default: `compliance_score`) |
| `sort_order` | string | No | Sort order: `asc`, `desc` (default: desc) |

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "period_days": 30,
  "total_agents": 12,
  "agents": [
    {
      "rep_id": "john_smith",
      "rep_name": "John Smith",
      "call_count": 87,
      "metrics": {
        "compliance_score": 0.85,
        "booking_rate": 0.45,
        "lead_score": 72,
        "sentiment_score": 0.78
      },
      "trend": "improving",
      "coaching_sessions": 2
    }
  ],
  "team_averages": {
    "compliance_score": 0.72,
    "booking_rate": 0.42,
    "lead_score": 58,
    "sentiment_score": 0.68
  }
}
```

---

## MongoDB Collections

### Collection: `weekly_insights`

```javascript
{
  _id: ObjectId("..."),
  insight_type: "company",  // "company" | "customer" | "objection"
  company_id: "acme_roofing",
  customer_id: ObjectId("..."),  // Only for customer insights
  week_start: ISODate("2026-01-06"),
  week_end: ISODate("2026-01-12"),
  data: {
    // Insight-specific data (see examples above)
  },
  generated_at: ISODate("2026-01-13T00:05:30Z"),
  status: "completed",  // "generating" | "completed" | "failed"
  job_id: "insight_job_abc123"
}
```

**Indexes:**
- `{insight_type: 1, company_id: 1, week_start: 1}` (unique)
- `{insight_type: 1, customer_id: 1, week_start: 1}` (unique, sparse)
- `{company_id: 1, week_start: 1}`
- `{status: 1, generated_at: 1}`
- `{job_id: 1}`

---

## Redis Keys

### Job Status
```
Key: insight_job:{job_id}:status
Value: {
  "job_id": "insight_job_abc123",
  "status": "processing",
  "progress": {
    "percent": 45,
    "current_step": "customer_insights",
    "companies_processed": 1,
    "companies_total": 3,
    "insights_generated": {
      "company": 1,
      "customer": 15,
      "objection": 10
    }
  },
  "week_start": "2026-01-06",
  "week_end": "2026-01-12",
  "updated_at": "2026-01-13T00:06:30Z"
}
TTL: 604800 (7 days)
```

### Current Week Cache
```
Key: insights:current:{company_id}
Value: {
  "company": {...},  // Company insight data
  "generated_at": "2026-01-13T00:05:30Z"
}
TTL: 604800 (7 days)
```

---

## Scheduling Options

### Option 1: Built-in APScheduler (Recommended)

The service includes an in-process scheduler using APScheduler that automatically runs weekly insights generation every Sunday at 00:00 UTC. **No external cron job or separate process is required.**

**Scheduler Status Endpoint:**

```http
GET /api/v1/scheduler/status
```

**Response:**
```json
{
  "running": true,
  "jobs_count": 1,
  "jobs": [
    {
      "id": "weekly_insights_generation",
      "name": "Weekly Insights Generation",
      "next_run_time": "2026-01-19T00:00:00+00:00",
      "trigger": "cron[day_of_week='sun', hour='0', minute='0']"
    }
  ]
}
```

**Benefits:**
- No separate Celery Beat process needed
- Runs within the FastAPI application
- Automatically starts/stops with the application
- Easy monitoring via REST API

### Option 2: External Cron Job (Optional)

For environments that prefer external scheduling or need to trigger generation from external systems:

```bash
#!/bin/bash

# weekly_insights_cron.sh
# Run every Sunday at 00:00 UTC (if not using built-in scheduler)

API_BASE_URL="https://intelligence-api.otto.ai"
API_KEY="your_api_key_here"
WEBHOOK_URL="https://otto-backend.com/webhooks/insights"

# Trigger insight generation
response=$(curl -X POST "$API_BASE_URL/api/v1/insights/generate" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"webhook_url\": \"$WEBHOOK_URL\"
  }")

job_id=$(echo $response | jq -r '.job_id')
echo "Insight generation started: $job_id"

# Poll status every 60 seconds
while true; do
  sleep 60
  
  status_response=$(curl -X GET "$API_BASE_URL/api/v1/insights/status/$job_id" \
    -H "X-API-Key: $API_KEY")
  
  status=$(echo $status_response | jq -r '.status')
  percent=$(echo $status_response | jq -r '.progress.percent')
  
  echo "Status: $status ($percent%)"
  
  if [ "$status" = "completed" ]; then
    echo "Insight generation completed successfully"
    exit 0
  elif [ "$status" = "failed" ]; then
    echo "Insight generation failed"
    echo $status_response | jq '.error'
    exit 1
  fi
done
```

**Note:** If using an external cron job, consider disabling the built-in APScheduler to prevent duplicate runs.

---

## MongoDB Aggregation Pipelines

### Company Insights Aggregation

```javascript
db.calls.aggregate([
  // Stage 1: Match date range and company
  {
    $match: {
      company_id: "acme_roofing",
      call_date: {
        $gte: ISODate("2026-01-06"),
        $lte: ISODate("2026-01-12")
      }
    }
  },
  
  // Stage 2: Lookup summaries
  {
    $lookup: {
      from: "call_summaries",
      localField: "call_id",
      foreignField: "call_id",
      as: "summary"
    }
  },
  
  // Stage 3: Unwind summary
  { $unwind: { path: "$summary", preserveNullAndEmptyArrays: true } },
  
  // Stage 4: Group and calculate metrics
  {
    $group: {
      _id: "$company_id",
      total_calls: { $sum: 1 },
      total_booked: {
        $sum: {
          $cond: [
            { $eq: ["$summary.qualification.booking_status", "booked"] },
            1,
            0
          ]
        }
      },
      avg_duration: { $avg: "$duration" },
      avg_compliance: { $avg: "$summary.compliance.sop_compliance.score" },
      avg_sentiment: { $avg: "$summary.summary.sentiment_score" },
      calls_by_rep: {
        $push: {
          rep_name: "$metadata.rep_name",
          booked: { $cond: [{ $eq: ["$summary.qualification.booking_status", "booked"] }, 1, 0] }
        }
      }
    }
  },
  
  // Stage 5: Calculate booking rate
  {
    $project: {
      company_id: "$_id",
      total_calls: 1,
      total_booked: 1,
      booking_rate: { $divide: ["$total_booked", "$total_calls"] },
      avg_duration: 1,
      avg_compliance: 1,
      avg_sentiment: 1,
      calls_by_rep: 1
    }
  }
])
```

---

## Performance Considerations

### Parallel Processing
- Generate company, customer, and objection insights sequentially per company
- Process companies one at a time to manage resource usage
- Use async/await for non-blocking I/O operations

### Caching Strategy
- Cache current week insights in Redis (7-day TTL)
- Pre-aggregate common queries
- Cache objection category lookup

### Query Optimization
- Index on `{company_id, call_date}` for date range queries
- Use MongoDB aggregation pipeline (runs on server)
- Batch customer insights (100 customers per batch)

### Resource Management
- APScheduler runs insight generation during off-peak hours (Sunday 00:00 UTC)
- Limit concurrent MongoDB connections
- Use MongoDB read preference: secondaryPreferred
- Single-process architecture reduces operational complexity

---

## Success Metrics

| Metric | Target | Monitoring |
|--------|--------|------------|
| Total generation time | < 30 min (all companies) | Job duration metric |
| API response time (trigger) | < 200ms | HTTP middleware |
| API response time (status) | < 100ms | Redis cache hit rate |
| Job success rate | > 99% | Job status aggregation |
| Data freshness | < 2 hours after scheduled run | Timestamp comparison |
| Scheduler uptime | 100% (with app) | `/api/v1/scheduler/status` |

---

## File Structure

```
app/
├── core/
│   └── scheduler.py              # APScheduler configuration & job definitions
│
├── tasks/
│   └── insight_tasks.py          # Background task implementation (FastAPI BackgroundTasks)
│
├── api/v1/
│   └── insights.py               # REST API endpoints
│
├── services/insights/
│   ├── __init__.py
│   ├── company_insights.py       # Company-level insight generation
│   ├── customer_insights.py      # Customer-level insight generation
│   └── objection_insights.py     # Objection insight generation
│
└── main.py                       # Scheduler start/stop in lifespan
```

### Key Components

| File | Purpose |
|------|---------|
| `app/core/scheduler.py` | APScheduler setup, job definitions, start/stop functions |
| `app/tasks/insight_tasks.py` | Async background task for insight generation |
| `app/api/v1/insights.py` | REST API for on-demand generation and status polling |
| `app/main.py` | Scheduler lifecycle management (start on startup, stop on shutdown) |

---

## Extended Features (v4.0)

The Insights Engine includes the following integrated capabilities:

### Feature 8: Agent Progression Tracking
See **[Features 5-9](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md)** for full details.

#### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/insights/agents/{rep_id}/progression` | Track agent metrics over time |
| `GET /api/v1/insights/agents/{rep_id}/peer-comparison` | Compare to peers (on-demand) |
| `GET /api/v1/insights/agents/summary` | Manager dashboard view |

#### Progression Tracking

**Weekly Metrics Calculation:**
- Aggregates calls by rep_id and week
- Supports metrics: `compliance_score`, `booking_rate`, `qualification_score`, `sentiment_score`, `lead_score`, BANT scores, `objection_handling`
- Confidence: "high" if ≥5 calls per week

**Trend Detection:**
- Algorithm: Compares first vs last value in period
- Thresholds: ≥5% improvement = improving, ≤-5% = declining, otherwise stable

**Anomaly Detection:**
- Threshold: >20% week-over-week change flagged
- Output: List of `Anomaly` objects with week_index, change_magnitude, direction

**Peer Comparison:**
- On-demand only (not shown by default per manager decision)
- Returns: rank, percentile, average, median, min, max
- Analysis period: configurable (default 30 days)

### Insight Headings & Action Items (NEW)

All insights now include structured headings:

```python
# Format for all insight types
{
  "insight_heading": "3-5 word summary",
  "insight": "Detailed insight text. Action: [specific action items]",
  "recommendation_heading": "3-5 word summary",
  "recommendation": "Specific recommendations with actions"
}
```

### Customer Engagement Scoring (NEW)

Multi-factor engagement calculation:

```python
engagement_score = (
    frequency_score * 0.4 +    # 0-0.4 based on calls this week
    history_score * 0.3 +       # 0-0.3 based on total call history
    sentiment_score * 0.3       # 0-0.3 based on average sentiment
)
```

### Priority Calculation (NEW)

Customer priority determined by multiple factors:

| Priority | Criteria |
|----------|----------|
| **HIGH** | Status = hot, OR pending actions, OR declining sentiment |
| **MEDIUM** | Status = warm, OR recent activity (≥2 calls this week) |
| **LOW** | Status = cold, minimal activity, stable sentiment |

---

## File Structure

```
app/
├── api/v1/
│   └── insights.py                   # API endpoints (12 endpoints)
│
├── tasks/
│   └── insight_tasks.py              # Background task for weekly generation
│
├── services/insights/
│   ├── __init__.py
│   ├── company_insights.py           # Company-level insight generation
│   ├── customer_insights.py          # Customer-level insight generation
│   ├── objection_insights.py         # Objection category analysis
│   └── progression_service.py        # Agent progression tracking (Feature 8)
│
├── models/
│   └── insight.py                    # MongoDB models
│
├── schemas/
│   └── insight.py                    # Pydantic request/response schemas
│
└── core/
    └── scheduler.py                  # APScheduler configuration
```

---

**Next:** [Feature 3: Ask Otto Chat Enhancement](./ARCHITECTURE_FEATURE_3_ASK_OTTO.md)

