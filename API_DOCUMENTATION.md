# Otto AI Backend API Documentation

**Base URL:** `http://localhost:8002/api/v1`

**Version:** 1.0

---

## Table of Contents

1. [Authentication](#authentication)
2. [Calls](#calls)
3. [Leads](#leads)
4. [Metrics](#metrics)
5. [RAG / Ask Otto](#rag--ask-otto)
6. [Webhooks](#webhooks)

---

## Authentication

All endpoints (except webhooks) require JWT authentication. Include the access token in the Authorization header:

```
Authorization: Bearer <access_token>
```

### POST `/auth/signup`

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "first_name": "John",
  "last_name": "Doe",
  "role": "sales_rep",
  "company_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Response:** `201 Created`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "user@example.com",
    "role": "sales_rep",
    "is_active": true,
    "first_name": "John",
    "last_name": "Doe",
    "company_id": "123e4567-e89b-12d3-a456-426614174000",
    "created_at": "2026-01-08T10:00:00Z"
  }
}
```

**Roles:** `csr`, `sales_rep`, `executive` (defaults to `sales_rep`)

---

### POST `/auth/login`

Login with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": { ... }
}
```

**Error:** `401 Unauthorized` - Invalid credentials

---

### POST `/auth/refresh`

Refresh access token using refresh token.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error:** `401 Unauthorized` - Invalid refresh token

---

### GET `/auth/me`

Get current authenticated user information.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "user@example.com",
  "role": "sales_rep",
  "is_active": true,
  "first_name": "John",
  "last_name": "Doe",
  "company_id": "123e4567-e89b-12d3-a456-426614174000",
  "created_at": "2026-01-08T10:00:00Z"
}
```

---

## Calls

### GET `/calls`

List calls for a specific company.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "company_id": "123e4567-e89b-12d3-a456-426614174000",
    "contact_card_id": "123e4567-e89b-12d3-a456-426614174001",
    "lead_id": "123e4567-e89b-12d3-a456-426614174002",
    "phone_number": "+1234567890",
    "call_type": "csr_call",
    "missed_call": false,
    "transcript": "Call transcript...",
    "audio_url": "https://...",
    "duration_seconds": 120,
    "owner_id": "123e4567-e89b-12d3-a456-426614174003",
    "created_at": "2026-01-08T10:00:00Z",
    "updated_at": "2026-01-08T10:02:00Z"
  }
]
```

**Required Role:** `CSR` or `EXECUTIVE`

---

### GET `/calls/{call_id}`

Get call by ID.

**Path Parameters:**
- `call_id` (UUID, required) - Call UUID

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "company_id": "123e4567-e89b-12d3-a456-426614174000",
  ...
}
```

**Error:** `404 Not Found` - Call not found

**Required Role:** `CSR` or `EXECUTIVE`

---

## Leads

### GET `/leads`

List leads for a company with optional filters.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `status` (string, optional) - Filter by status (comma-separated, e.g., `"qualified_unbooked"` or `"closed_lost,abandoned,dormant"`)
- `nurturing` (string, optional) - Filter nurturing leads (comma-separated, e.g., `"new,warm,hot"`)
- `sort` (string, optional) - Sort option (e.g., `"priority"`)
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "company_id": "123e4567-e89b-12d3-a456-426614174000",
    "contact_card_id": "123e4567-e89b-12d3-a456-426614174001",
    "status": "qualified_unbooked",
    "deal_status": "booked",
    "assigned_rep_id": "123e4567-e89b-12d3-a456-426614174002",
    "deal_size": 5000.00,
    "closed_at": null,
    "created_at": "2026-01-08T10:00:00Z",
    "updated_at": "2026-01-08T10:00:00Z"
  }
]
```

**Examples:**
- Get qualified unbooked leads: `/leads?company_id=...&status=qualified_unbooked`
- Get qualified booked leads: `/leads?company_id=...&status=qualified_booked`
- Get closed/lost/abandoned leads: `/leads?company_id=...&status=closed_lost,abandoned,dormant`
- Get nurturing leads: `/leads?company_id=...&nurturing=new,warm,hot`
- Sort by priority: `/leads?company_id=...&sort=priority`

**Required Role:** `EXECUTIVE` or `CSR`

---

### GET `/leads/{lead_id}`

Get lead by ID.

**Path Parameters:**
- `lead_id` (UUID, required) - Lead UUID

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "company_id": "123e4567-e89b-12d3-a456-426614174000",
  ...
}
```

**Error:** `404 Not Found` - Lead not found

**Required Role:** `EXECUTIVE` or `CSR`

---

## Metrics

All metrics endpoints support date range filtering with `start_date` and `end_date` query parameters (format: `YYYY-MM-DD`). If not provided, defaults to last 30 days.

### GET `/metrics/exec/company-overview`

Get company overview metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD, defaults to 30 days ago)
- `end_date` (date, optional) - End date (YYYY-MM-DD, defaults to today)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "total_leads": 150,
  "active_leads": 120,
  "total_calls": 500,
  "missed_calls": 25,
  "total_appointments": 80,
  "conversion_rate": 15.5,
  "total_revenue": 75000.00,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/exec/csr/dashboard`

Get CSR dashboard metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_calls": 500,
  "missed_calls": 25,
  "calls_today": 15,
  "avg_call_duration": 180.5,
  "leads_assigned": 120,
  "appointments_scheduled": 80,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/exec/missed-calls`

Get missed calls metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "missed_calls": 25,
  "total_calls": 500,
  "miss_rate": 5.0,
  "recent_missed": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "phone_number": "+1234567890",
      "created_at": "2026-01-08T10:00:00Z"
    }
  ],
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/csr/auto-queued-leads`

Get auto-queued leads for CSR within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)
- `limit` (int, default: 20, max: 100) - Maximum number of leads

**Response:** `200 OK`
```json
{
  "total": 20,
  "hot_leads": 5,
  "warm_leads": 10,
  "new_leads": 5,
  "leads": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "contact_card_id": "123e4567-e89b-12d3-a456-426614174001",
      "status": "hot",
      "deal_size": 5000.00,
      "assigned_rep_id": "123e4567-e89b-12d3-a456-426614174002",
      "created_at": "2026-01-08T10:00:00Z"
    }
  ],
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `CSR` or `EXECUTIVE`

---

### GET `/metrics/booking-rate-improvement`

Get booking rate improvement metrics comparing current period to previous period.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start of current period (YYYY-MM-DD)
- `end_date` (date, optional) - End of current period (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "current_rate": 25.5,
  "previous_rate": 20.0,
  "improvement_percentage": 5.5,
  "total_bookings": 50,
  "total_qualified": 196,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59",
  "previous_period_start": "2025-11-01T00:00:00",
  "previous_period_end": "2025-12-01T00:00:00"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/bookings/summary`

Get bookings summary metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_bookings": 80,
  "confirmed_bookings": 60,
  "pending_bookings": 15,
  "cancelled_bookings": 5,
  "bookings_today": 3,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/objections/top`

Get top objections from call analyses within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)
- `limit` (int, default: 5, max: 20) - Number of top objections

**Response:** `200 OK`
```json
{
  "objections": [
    {
      "objection_type": "price",
      "count": 45,
      "percentage": 35.2
    },
    {
      "objection_type": "timing",
      "count": 30,
      "percentage": 23.4
    }
  ],
  "total_calls_with_objections": 128,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/objections/summary`

Get objections summary within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_objections": 200,
  "unique_objection_types": 6,
  "top_objection": "price",
  "objections_by_type": {
    "price": 80,
    "timing": 50,
    "authority": 30,
    "need": 25,
    "competitor": 10,
    "other": 5
  },
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/objections/{objection_type}/calls`

Get calls with specific objection type within date range.

**Path Parameters:**
- `objection_type` (string, required) - Type of objection (`price`, `timing`, `authority`, `need`, `competitor`, `other`)

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)
- `limit` (int, default: 20, max: 100) - Maximum number of calls

**Response:** `200 OK`
```json
{
  "objection_type": "price",
  "total_calls": 80,
  "calls": [
    {
      "call_id": "123e4567-e89b-12d3-a456-426614174000",
      "phone_number": "+1234567890",
      "created_at": "2026-01-08T10:00:00Z",
      "duration_seconds": 180,
      "objection_texts": ["Customer mentioned price is too high"],
      "summary": "Call summary..."
    }
  ],
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/coaching/opportunities`

Get coaching opportunities based on low SOP compliance within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)
- `limit` (int, default: 10, max: 50) - Maximum number of opportunities

**Response:** `200 OK`
```json
{
  "opportunities": [
    {
      "call_id": "123e4567-e89b-12d3-a456-426614174000",
      "rep_id": "123e4567-e89b-12d3-a456-426614174001",
      "sop_compliance_score": 0.55,
      "sop_stages_missed": ["objection_handling", "close"],
      "sentiment_score": -0.2
    }
  ],
  "total_count": 25,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/conversion/lead-to-sale`

Get lead to sale conversion metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_leads": 200,
  "converted_leads": 30,
  "conversion_rate": 15.0,
  "avg_days_to_conversion": 12.5,
  "total_revenue": 150000.00,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/conversions/pending-to-booked`

Get conversions from pending leads to booked within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "converted_count": 50,
  "conversion_rate": 25.5,
  "avg_days_to_book": 0.0,
  "period_start": "2025-12-01T00:00:00",
  "period_end": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/emergencies/dropped`

Get emergency/dropped calls metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "dropped_calls": 25,
  "emergency_calls": 5,
  "drop_rate": 5.0,
  "avg_response_time": 0.0,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/company/performance`

Get company performance metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_revenue": 750000.00,
  "total_leads": 500,
  "conversion_rate": 15.0,
  "avg_deal_size": 5000.00,
  "active_reps": 10,
  "calls_per_rep": 50.0,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/metrics/calls/summary`

Get calls summary metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_calls": 500,
  "answered_calls": 475,
  "missed_calls": 25,
  "avg_duration": 180.5,
  "total_duration": 85737,
  "calls_today": 15,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/leads/unbooked`

Get unbooked leads metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)
- `limit` (int, default: 20, max: 100) - Maximum number of leads

**Response:** `200 OK`
```json
{
  "total_unbooked": 50,
  "qualified_unbooked": 50,
  "avg_days_unbooked": 5.5,
  "leads": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "contact_card_id": "123e4567-e89b-12d3-a456-426614174001",
      "status": "qualified_unbooked",
      "deal_size": 5000.00,
      "created_at": "2026-01-08T10:00:00Z"
    }
  ],
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

### GET `/metrics/actions/pending`

Get pending actions metrics within date range.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `start_date` (date, optional) - Start date (YYYY-MM-DD)
- `end_date` (date, optional) - End date (YYYY-MM-DD)

**Response:** `200 OK`
```json
{
  "total_pending": 75,
  "follow_ups_needed": 50,
  "calls_to_make": 20,
  "appointments_to_schedule": 5,
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** Any authenticated user

---

## RAG / Ask Otto

### POST `/rag/ask-otto`

Query Ask Otto (RAG-based AI copilot) - Company scope.

**Request Body:**
```json
{
  "query": "What are the top objections this month?",
  "context": {
    "company_id": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "answer": "Based on the analysis, the top objections this month are...",
  "sources": [...]
}
```

**Error:** `503 Service Unavailable` - RAG service not available

**Required Role:** `EXECUTIVE`

---

## Webhooks

Webhook endpoints are public (no JWT required). For production, implement webhook signature verification.

### POST `/webhooks/telephony/call-complete`

Handle call completion webhook from telephony provider (CallRail, Twilio).

**Request Body:**
```json
{
  "company_id": "123e4567-e89b-12d3-a456-426614174000",
  "phone_number": "+1234567890",
  "audio_url": "https://example.com/audio.mp3",
  "call_type": "csr_call",
  "missed_call": false,
  "duration_seconds": 120
}
```

**Headers (alternative):**
```
X-Company-Id: 123e4567-e89b-12d3-a456-426614174000
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "call_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Error:** `400 Bad Request` - Missing required fields

---

### POST `/webhooks/shoonya/job-complete`

Handle job completion webhook from Shoonya (call analysis).

**Request Body:**
```json
{
  "shunya_job_id": "job_123",
  "status": "completed",
  "call_id": "123e4567-e89b-12d3-a456-426614174000",
  "company_id": "123e4567-e89b-12d3-a456-426614174001",
  "result": {
    "transcript": "Call transcript text...",
    "analysis": {
      "qualification_status": "qualified",
      "booking_status": "booked",
      "objections": ["price", "timing"],
      "objection_texts": ["Customer mentioned price is too high"],
      "sop_stages_completed": ["greeting", "qualification", "presentation"],
      "sop_stages_missed": ["objection_handling", "close"],
      "sop_compliance_score": 0.75,
      "sentiment_score": 0.5,
      "summary": "Call summary...",
      "key_points": ["Point 1", "Point 2"]
    }
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "call_id": "123e4567-e89b-12d3-a456-426614174000",
  "analysis_id": "123e4567-e89b-12d3-a456-426614174002"
}
```

**Error:** `400 Bad Request` - Missing required fields or invalid format

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error message describing what went wrong"
}
```

### 401 Unauthorized
```json
{
  "detail": "Invalid email or password"
}
```

### 403 Forbidden
```json
{
  "detail": "Access denied. Required roles: [executive]"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

### 503 Service Unavailable
```json
{
  "detail": "Service not available"
}
```

---

## User Roles

- **CSR** - Customer Service Representative
- **SALES_REP** - Sales Representative
- **EXECUTIVE** - Executive/Manager (formerly MANAGER)

---

## Date Format

All date parameters use `YYYY-MM-DD` format (e.g., `2026-01-08`).

---

## Pagination

Endpoints that support pagination use:
- `skip` - Number of records to skip (default: 0)
- `limit` - Maximum number of records to return (default: 100)

---

## Notes

- All timestamps are in ISO 8601 format with timezone (e.g., `2026-01-08T10:00:00Z`)
- UUIDs are in standard format (e.g., `123e4567-e89b-12d3-a456-426614174000`)
- Metrics endpoints default to last 30 days if `start_date` and `end_date` are not provided
- Webhook endpoints do not require authentication but should implement signature verification in production

