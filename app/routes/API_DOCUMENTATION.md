# API Documentation

Base URL: `/api/v1`

All endpoints require authentication except webhooks. Include JWT token in header: `Authorization: Bearer <token>`

---

## Authentication

### POST `/auth/signup`
Create new user account.

**Body:**
- `email` (string, required)
- `password` (string, required)
- `first_name` (string, optional)
- `last_name` (string, optional)
- `role` (string, optional) - Default: `sales_rep`
- `company_id` (UUID, optional)

**Returns:** Access token, refresh token, user info

---

### POST `/auth/login`
Login with email and password.

**Body:**
- `email` (string, required)
- `password` (string, required)

**Returns:** Access token, refresh token, user info

---

### POST `/auth/refresh`
Get new access token using refresh token.

**Body:**
- `refresh_token` (string, required)

**Returns:** New access token

---

### GET `/auth/me`
Get current user information.

**Returns:** User details

---

## Calls

### GET `/calls`
List calls for a company.

**Query:**
- `company_id` (UUID, required)
- `skip` (int, default: 0)
- `limit` (int, default: 100)

**Access:** CSR, EXECUTIVE

---

### GET `/calls/{call_id}`
Get call by ID.

**Access:** CSR, EXECUTIVE

---

## Leads

### GET `/leads`
List leads with filters.

**Query:**
- `company_id` (UUID, required)
- `status` (string, optional) - Comma-separated: `"qualified_unbooked"` or `"closed_lost,abandoned"`
- `nurturing` (string, optional) - Comma-separated: `"new,warm,hot"`
- `sort` (string, optional) - `"priority"`
- `skip` (int, default: 0)
- `limit` (int, default: 100)

**Access:** EXECUTIVE, CSR

---

### GET `/leads/{lead_id}`
Get lead by ID.

**Access:** EXECUTIVE, CSR

---

## Metrics

All metrics endpoints require:
- `company_id` (UUID, required)
- `start_date` (date, optional) - Format: `YYYY-MM-DD`, defaults to 30 days ago
- `end_date` (date, optional) - Format: `YYYY-MM-DD`, defaults to today

### GET `/metrics/exec/company-overview`
Company overview: leads, calls, appointments, revenue, conversion rate.

**Access:** EXECUTIVE

---

### GET `/metrics/exec/csr/dashboard`
CSR dashboard: calls, missed calls, leads, appointments.

**Access:** EXECUTIVE

---

### GET `/metrics/exec/missed-calls`
Missed calls count and rate.

**Access:** EXECUTIVE

---

### GET `/metrics/csr/auto-queued-leads`
Auto-queued leads for CSR (hot, warm, new).

**Query:**
- `limit` (int, default: 20)

**Access:** CSR, EXECUTIVE

---

### GET `/metrics/booking-rate-improvement`
Booking rate comparison: current vs previous period.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/bookings/summary`
Bookings summary: total, confirmed, pending, cancelled.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/objections/top`
Top objections from call analyses.

**Query:**
- `limit` (int, default: 5)

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/objections/summary`
Objections summary: total, types, breakdown.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/objections/{objection_type}/calls`
Calls with specific objection type.

**Query:**
- `limit` (int, default: 20)

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/coaching/opportunities`
Calls with low SOP compliance (< 70%).

**Query:**
- `limit` (int, default: 10)

**Access:** EXECUTIVE

---

### GET `/metrics/conversion/lead-to-sale`
Lead to sale conversion metrics.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/conversions/pending-to-booked`
Pending to booked conversion rate.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/emergencies/dropped`
Dropped calls and emergency calls.

**Access:** EXECUTIVE

---

### GET `/metrics/company/performance`
Company performance: revenue, conversion rate, deal size.

**Access:** EXECUTIVE

---

### GET `/metrics/calls/summary`
Calls summary: total, answered, missed, duration.

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/leads/unbooked`
Unbooked leads count and average days.

**Query:**
- `limit` (int, default: 20)

**Access:** CSR, SALES_REP, EXECUTIVE

---

### GET `/metrics/actions/pending`
Pending actions: follow-ups, callbacks, appointments.

**Access:** CSR, SALES_REP, EXECUTIVE

---

## RAG / Ask Otto

### POST `/rag/ask-otto`
Query Ask Otto AI copilot.

**Body:**
- `query` (string, required)
- `context` (object, optional)

**Access:** EXECUTIVE

---

## Webhooks

### POST `/webhooks/telephony/call-complete`
Receive call completion from telephony provider.

**Body:**
- `company_id` (UUID, required)
- `phone_number` (string, required)
- `audio_url` (string, optional)
- `call_type` (string, optional)
- `missed_call` (boolean, default: false)
- `duration_seconds` (int, optional)

**No authentication required**

---

### POST `/webhooks/shoonya/job-complete`
Receive job completion from Shoonya.

**Body:**
- `shunya_job_id` (string, required)
- `status` (string, required) - Must be `"completed"`
- `call_id` (UUID string, required)
- `company_id` (UUID string, required)
- `result` (object, required)
  - `transcript` (string, optional)
  - `analysis` (object, required)
    - `qualification_status` (string, optional)
    - `booking_status` (string, optional)
    - `objections` (array, optional)
    - `objection_texts` (array, optional)
    - `sop_stages_completed` (array, optional)
    - `sop_stages_missed` (array, optional)
    - `sop_compliance_score` (float, optional)
    - `sentiment_score` (float, optional)
    - `summary` (string, optional)
    - `key_points` (array, optional)

**No authentication required**

---

## User Roles

- `CSR` - Customer Service Representative
- `SALES_REP` - Sales Representative
- `EXECUTIVE` - Executive/Manager

---

## Common Response Codes

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Server Error

