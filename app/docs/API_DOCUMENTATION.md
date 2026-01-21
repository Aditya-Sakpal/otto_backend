# Otto AI Backend API Documentation

**Base URL:** `http://localhost:8000/api/v1` (or `http://localhost:8001/api/v1`)

**Version:** 2.0.0

---

## Test Data

This documentation uses real UUIDs from the seed data (`backend/seed_dummy_data.sql`). Key test IDs:

- **Company:** `11111111-1111-1111-1111-111111111111` (Acme Corporation)
- **Users:**
  - Executive: `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` (exec@acme.com)
  - Sales Rep: `cccccccc-cccc-cccc-cccc-cccccccccccc` (sales1@acme.com)
  - CSR: `ffffffff-ffff-ffff-ffff-ffffffffffff` (csr1@acme.com)
- **Contact Card:** `10000000-0000-0000-0000-000000000001` (Alice Johnson)
- **Lead:** `20000000-0000-0000-0000-000000000001` (Qualified Booked)
- **Call:** `30000000-0000-0000-0000-000000000001` (Sales call with transcript)
- **Call Processing Job:** `80000000-0000-0000-0000-000000000003` (Completed)
- **Ask Otto Conversation:** `90000000-0000-0000-0000-000000000001`
- **Insight Job:** `b0000000-0000-0000-0000-000000000003` (Completed)

To use this data, run `backend/seed_dummy_data.sql` against your database.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Users](#users)
3. [Calls](#calls)
4. [Leads](#leads)
5. [Metrics](#metrics)
6. [Analytics](#analytics)
7. [Call Processing (Shunya)](#call-processing-shunya)
8. [Ask Otto (Shunya)](#ask-otto-shunya)
9. [Insights (Shunya)](#insights-shunya)
10. [RAG / Ask Otto](#rag--ask-otto)
11. [Webhooks](#webhooks)
12. [Invites](#invites)
13. [Onboarding](#onboarding)

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
  "email": "test.user@example.com",
  "password": "SecurePassword123!",
  "first_name": "Test",
  "last_name": "User",
  "role": "sales_rep",
  "company_id": "11111111-1111-1111-1111-111111111111"
}
```

**Note:** Use real company ID from seed data: `11111111-1111-1111-1111-111111111111` (Acme Corporation)

**Response:** `201 Created`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "email": "test.user@example.com",
    "role": "sales_rep",
    "is_active": true,
    "first_name": "Test",
    "last_name": "User",
    "company_id": "11111111-1111-1111-1111-111111111111",
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
  "email": "sales1@acme.com",
  "password": "SecurePassword123!"
}
```

**Note:** Use real user emails from seed data:
- Executive: `exec@acme.com`
- Sales Rep: `sales1@acme.com`, `sales2@acme.com`
- CSR: `csr1@acme.com`, `csr2@acme.com`

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
  "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "email": "sales1@acme.com",
  "role": "sales_rep",
  "is_active": true,
  "first_name": "Mike",
  "last_name": "Salesman",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2026-01-08T10:00:00Z"
}
```

---

## Users

### GET `/users`

List users with optional filters.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return
- `role` (string, optional) - Filter by role (`csr`, `sales_rep`, `executive`)
- `is_active` (boolean, optional) - Filter by active status

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "email": "exec@acme.com",
    "role": "executive",
    "is_active": true,
    "first_name": "John",
    "last_name": "Executive",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "created_at": "2025-01-08T10:00:00Z"
  }
]
```

**Required Role:** `EXECUTIVE`

---

### GET `/users/{user_id}`

Get user by ID.

**Path Parameters:**
- `user_id` (UUID, required) - User UUID

**Response:** `200 OK`
```json
{
  "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "email": "sales1@acme.com",
  "role": "sales_rep",
  "is_active": true,
  "first_name": "Mike",
  "last_name": "Salesman",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2025-05-08T10:00:00Z"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/users/me`

Get current user's profile.

**Response:** `200 OK`
```json
{
  "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "email": "sales1@acme.com",
  "role": "sales_rep",
  "is_active": true,
  "first_name": "Mike",
  "last_name": "Salesman",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2025-05-08T10:00:00Z"
}
```

**Required Role:** Any authenticated user

---

### GET `/users/companies`

List all companies.

**Response:** `200 OK`
```json
[
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Acme Corporation",
    "phone_number": "+1-555-0100",
    "address": "123 Business St, New York, NY 10001"
  }
]
```

**Required Role:** Any authenticated user

---

### GET `/users/sales-reps`

Get all sales reps for a company.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `is_active` (boolean, optional, default: true) - Filter by active status
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100, max: 1000) - Maximum number of records to return

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
GET /api/v1/users/sales-reps?company_id=11111111-1111-1111-1111-111111111111&is_active=true&skip=0&limit=100
```

**Response:** `200 OK`
```json
[
  {
    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "email": "sales1@acme.com",
    "role": "sales_rep",
    "is_active": true,
    "first_name": "Mike",
    "last_name": "Salesman",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "created_at": "2025-05-08T10:00:00Z"
  },
  {
    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "email": "sales2@acme.com",
    "role": "sales_rep",
    "is_active": true,
    "first_name": "Sarah",
    "last_name": "Seller",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "created_at": "2025-05-09T10:00:00Z"
  }
]
```

**Required Role:** Any authenticated user

---

### POST `/users`

Create a new user (EXECUTIVE only).

**Request Body:**
```json
{
  "email": "new.user@example.com",
  "password": "SecurePassword123!",
  "first_name": "New",
  "last_name": "User",
  "role": "csr",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "is_active": true
}
```

**Response:** `201 Created`

**Required Role:** `EXECUTIVE`

---

### PUT `/users/{user_id}`

Update user by ID (EXECUTIVE only).

**Request Body:**
```json
{
  "first_name": "Updated",
  "last_name": "Name",
  "role": "executive",
  "is_active": true
}
```

**Response:** `200 OK`

**Required Role:** `EXECUTIVE`

---

### DELETE `/users/{user_id}`

Delete user by ID (EXECUTIVE only).

**Response:** `204 No Content`

**Required Role:** `EXECUTIVE`

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

**Example Request:**
```
GET /api/v1/calls?company_id=11111111-1111-1111-1111-111111111111&skip=0&limit=100
```

**Response:** `200 OK`
```json
[
  {
    "id": "30000000-0000-0000-0000-000000000001",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "contact_card_id": "10000000-0000-0000-0000-000000000001",
    "lead_id": "20000000-0000-0000-0000-000000000001",
    "phone_number": "+1-555-1001",
    "call_type": "sales_call",
    "missed_call": false,
    "transcript": "Hello, I am interested in your services. What are your pricing options?",
    "audio_url": "https://storage.example.com/audio/call1.mp3",
    "duration_seconds": 180,
    "owner_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "answered_at": "2025-10-20T10:00:08Z",
    "created_at": "2025-10-20T10:00:00Z",
    "updated_at": "2025-10-20T10:00:00Z"
  }
]
```

**Note:** Real call IDs from seed data:
- `30000000-0000-0000-0000-000000000001` - Sales call with transcript
- `30000000-0000-0000-0000-000000000006` - CSR call
- `30000000-0000-0000-0000-000000000008` - Missed call

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

**Example Request:**
```
GET /api/v1/calls/30000000-0000-0000-0000-000000000001
```

**Response:** `200 OK`
```json
{
  "id": "30000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "contact_card_id": "10000000-0000-0000-0000-000000000001",
  "lead_id": "20000000-0000-0000-0000-000000000001",
  "phone_number": "+1-555-1001",
  "call_type": "sales_call",
  "missed_call": false,
  "transcript": "Hello, I am interested in your services. What are your pricing options?",
  "audio_url": "https://storage.example.com/audio/call1.mp3",
  "duration_seconds": 180,
  "owner_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "answered_at": "2025-10-20T10:00:08Z",
  "created_at": "2025-10-20T10:00:00Z",
  "updated_at": "2025-10-20T10:00:00Z"
}
```

**Note:** The `answered_at` field indicates when the call was answered. This is used to calculate response time metrics for CSR performance. For missed calls, `answered_at` will be `null`.

**Error:** `404 Not Found` - Call not found

**Required Role:** `CSR` or `EXECUTIVE`

---

### GET `/calls/by-objection/self`

Get comprehensive objection details data for the objection details page.

**Query Parameters:**
- `objection` (string, required) - Objection type (e.g., `authority`, `price`, `timing`, `competitor`, `need`)
- `company_id` (UUID, optional) - Company UUID (defaults to user's company if not provided)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
GET /api/v1/calls/by-objection/self?objection=authority&company_id=11111111-1111-1111-1111-111111111111
```

**Response:** `200 OK`
```json
{
  "objection": "authority",
  "calls": [
    {
      "id": "30000000-0000-0000-0000-000000000004",
      "contact_name": "David Brown",
      "call_recording_url": "https://storage.example.com/audio/call4.mp3",
      "phone_number": "+1-555-4001",
      "call_type": "sales_call",
      "duration_seconds": 120,
      "created_at": "2025-12-20T10:00:00Z",
      "transcript": "I need to check with my manager before making a decision.",
      "summary": "Customer needs manager approval. Decision maker not on call."
    }
  ],
  "unbooked_leads": [
    {
      "id": "20000000-0000-0000-0000-000000000004",
      "contact_name": "David Brown",
      "status": "new",
      "deal_status": "new",
      "created_at": "2025-12-20T10:00:00Z"
    }
  ],
  "most_coaching_need": [
    {
      "csr_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
      "csr_name": "Lisa Support",
      "unbooked_calls": 2
    }
  ]
}
```

**Note:** 
- Returns data for three tabs: Calls, Unbooked Leads, and Most Coaching Need
- Objection matching is case-insensitive and handles variations (e.g., `price` matches `pricing`, `cost`, `costs`)
- For CSR role, results are filtered to the current user's calls only
- For EXECUTIVE role, results show company-wide data

**Required Role:** `CSR` or `EXECUTIVE`

---

### GET `/calls/by-objection/{objection}/details`

Get comprehensive objection details for a single objection.

Returns all details for the objection details modal including:
1. **Unbooked leads tab**: Booking rate improvement, graph data, and unbooked leads list
2. **Most coaching need tab**: CSRs with unbooked calls count
3. **Calls tab**: Call recordings with contact names

**Path Parameters:**
- `objection` (string, required) - Objection type (e.g., `authority`, `price`, `timing`, `competitor`, `need`)

**Query Parameters:**
- `company_id` (UUID, optional) - Company UUID (defaults to user's company)
- `start_date` (string, optional) - Start date for filtering (YYYY-MM-DD, defaults to 30 days ago)
- `end_date` (string, optional) - End date for filtering (YYYY-MM-DD, defaults to today)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
GET /api/v1/calls/by-objection/authority/details?company_id=11111111-1111-1111-1111-111111111111&start_date=2025-12-01&end_date=2026-01-15
```

**Response:** `200 OK`
```json
{
  "objection": "authority",
  "unbooked_leads": {
    "booking_rate_improvement": {
      "title": "Booking Rate Improvement",
      "percentage": 32.0,
      "description": "32.0% Increase in Booking Appointments",
      "context": "Growth in qualified leads booked from start to end of the selected timeframe.",
      "current_rate": 45.5,
      "previous_rate": 13.5,
      "total_qualified": 100,
      "booked_count": 45,
      "unbooked_count": 55
    },
    "graph_data": [
      {
        "date": "2025-12-01",
        "booking_rate": 10.5,
        "qualified_count": 20,
        "booked_count": 2
      },
      {
        "date": "2025-12-02",
        "booking_rate": 15.0,
        "qualified_count": 20,
        "booked_count": 3
      }
    ],
    "leads": [
      {
        "id": "20000000-0000-0000-0000-000000000002",
        "contact_name": "Alice Johnson",
        "phone_number": "+1-555-1001",
        "status": "qualified_unbooked",
        "deal_status": "qualified",
        "created_at": "2025-12-01T10:00:00Z"
      }
    ]
  },
  "most_coaching_need": {
    "total_csr": 4,
    "csrs": [
      {
        "csr_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "csr_name": "Raven",
        "unbooked_calls": 10
      },
      {
        "csr_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        "csr_name": "Navia Baxter",
        "unbooked_calls": 10
      },
      {
        "csr_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "csr_name": "Layla",
        "unbooked_calls": 3
      },
      {
        "csr_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "csr_name": "Jayda",
        "unbooked_calls": 1
      }
    ]
  },
  "calls": {
    "total_calls": 3,
    "call_recordings": [
      {
        "id": "30000000-0000-0000-0000-000000000001",
        "contact_name": "Courtney",
        "call_recording_url": "https://storage.example.com/audio/call1.mp3",
        "phone_number": "+1-555-1001",
        "call_type": "csr_call",
        "duration_seconds": 180,
        "created_at": "2025-12-01T10:00:00Z",
        "transcript": "Call transcript...",
        "summary": "Call summary..."
      },
      {
        "id": "30000000-0000-0000-0000-000000000002",
        "contact_name": "Heather",
        "call_recording_url": "https://storage.example.com/audio/call2.mp3",
        "phone_number": "+1-555-1002",
        "call_type": "csr_call",
        "duration_seconds": 200,
        "created_at": "2025-12-02T10:00:00Z",
        "transcript": "Call transcript...",
        "summary": "Call summary..."
      },
      {
        "id": "30000000-0000-0000-0000-000000000003",
        "contact_name": "Kevin",
        "call_recording_url": "https://storage.example.com/audio/call3.mp3",
        "phone_number": "+1-555-1003",
        "call_type": "csr_call",
        "duration_seconds": 150,
        "created_at": "2025-12-03T10:00:00Z",
        "transcript": "Call transcript...",
        "summary": "Call summary..."
      }
    ]
  },
  "start_date": "2025-12-01",
  "end_date": "2026-01-15"
}
```

**Note:** 
- Objection matching is case-insensitive and handles variations (e.g., `price` matches `pricing`, `cost`, `costs`)
- For CSR role, results are filtered to the current user's calls only
- For EXECUTIVE role, results show company-wide data
- Graph data provides daily booking rates for visualization
- Booking rate improvement compares first half vs second half of the date range

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

**Example Request:**
```
GET /api/v1/leads?company_id=11111111-1111-1111-1111-111111111111&status=qualified_unbooked
```

**Response:** `200 OK`
```json
[
  {
    "id": "20000000-0000-0000-0000-000000000002",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "contact_card_id": "10000000-0000-0000-0000-000000000002",
    "status": "qualified_unbooked",
    "deal_status": "qualified",
    "assigned_rep_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "deal_size": 7500.00,
    "closed_at": null,
    "created_at": "2025-11-20T10:00:00Z",
    "updated_at": "2025-11-25T10:00:00Z"
  }
]
```

**Examples:**
- Get qualified unbooked leads: `/leads?company_id=11111111-1111-1111-1111-111111111111&status=qualified_unbooked`
- Get qualified booked leads: `/leads?company_id=11111111-1111-1111-1111-111111111111&status=qualified_booked`
- Get closed/lost/abandoned leads: `/leads?company_id=11111111-1111-1111-1111-111111111111&status=closed_lost,abandoned,dormant`
- Get nurturing leads: `/leads?company_id=11111111-1111-1111-1111-111111111111&nurturing=new,warm,hot`
- Sort by priority: `/leads?company_id=11111111-1111-1111-1111-111111111111&sort=priority`

**Note:** Real lead IDs from seed data:
- `20000000-0000-0000-0000-000000000001` - Qualified booked
- `20000000-0000-0000-0000-000000000002` - Qualified unbooked
- `20000000-0000-0000-0000-000000000007` - Hot lead

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

**Example Request:**
```
GET /api/v1/leads/20000000-0000-0000-0000-000000000001
```

**Response:** `200 OK`
```json
{
  "id": "20000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "contact_card_id": "10000000-0000-0000-0000-000000000001",
  "status": "qualified_booked",
  "deal_status": "qualified",
  "assigned_rep_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "deal_size": 5000.00,
  "closed_at": null,
  "created_at": "2025-10-20T10:00:00Z",
  "updated_at": "2025-10-25T10:00:00Z"
}
```

**Error:** `404 Not Found` - Lead not found

**Required Role:** `EXECUTIVE` or `CSR`

---

### GET `/leads/{lead_id}/details`

Get detailed lead information for lead details page.

**Path Parameters:**
- `lead_id` (UUID, required) - Lead UUID

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
GET /api/v1/leads/20000000-0000-0000-0000-000000000001/details
```

**Response:** `200 OK`
```json
{
  "id": "20000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "status": "qualified_booked",
  "deal_status": "qualified",
  "deal_size": 5000.00,
  "created_at": "2025-10-20T10:00:00Z",
  "updated_at": "2025-10-25T10:00:00Z",
  "contact": {
    "id": "10000000-0000-0000-0000-000000000001",
    "first_name": "Alice",
    "last_name": "Johnson",
    "primary_phone": "+1-555-1001",
    "email": "customer1@example.com"
  },
  "agent": {
    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "first_name": "Mike",
    "last_name": "Salesman",
    "email": "sales1@acme.com"
  },
  "overall_engagement": {
    "summary": "Customer inquired about pricing and expressed concerns about cost. Qualified lead but not ready to book.",
    "key_points": [
      "Price concern",
      "Qualified lead",
      "Needs follow-up"
    ],
    "action_items": [
      "Follow up on pricing concerns"
    ],
    "appointment_status": "Qualified and booked"
  },
  "conversations": [
    {
      "id": "30000000-0000-0000-0000-000000000001",
      "call_type": "sales_call",
      "phone_number": "+1-555-1001",
      "duration_seconds": 180,
      "missed_call": false,
      "transcript": "Hello, I am interested in your services...",
      "call_recording_url": "https://storage.example.com/audio/call1.mp3",
      "handled_by_user_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "created_at": "2025-10-20T10:00:00Z",
      "summary": "Customer inquired about pricing...",
      "key_points": ["Price concern", "Qualified lead"],
      "objections": ["price", "pricing"],
      "sentiment_score": 0.65,
      "sop_compliance_score": 75.5,
      "qualification_status": "qualified",
      "booking_status": "not_booked"
    }
  ]
}
```

**Error:** `404 Not Found` - Lead not found

**Required Role:** `EXECUTIVE` or `CSR`

---

### POST `/leads/{lead_id}/assign`

Assign a lead to a sales rep.

**Path Parameters:**
- `lead_id` (UUID, required) - Lead UUID

**Request Body:**
```json
{
  "sales_rep_id": "cccccccc-cccc-cccc-cccc-cccccccccccc"
}
```

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
POST /api/v1/leads/20000000-0000-0000-0000-000000000004/assign
Content-Type: application/json

{
  "sales_rep_id": "cccccccc-cccc-cccc-cccc-cccccccccccc"
}
```

**Response:** `200 OK`
```json
{
  "lead": {
    "id": "20000000-0000-0000-0000-000000000004",
    "company_id": "11111111-1111-1111-1111-111111111111",
    "contact_card_id": "10000000-0000-0000-0000-000000000004",
    "status": "new",
    "deal_status": "new",
    "assigned_rep_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "deal_size": null,
    "closed_at": null,
    "extra_metadata": {
      "last_assignment": {
        "assigned_by": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "assigned_at": "2026-01-15T10:30:00Z",
        "previous_rep_id": null
      },
      "assignment_history": [
        {
          "assigned_by": "ffffffff-ffff-ffff-ffff-ffffffffffff",
          "assigned_at": "2026-01-15T10:30:00Z",
          "previous_rep_id": null
        }
      ]
    },
    "created_at": "2025-12-20T10:00:00Z",
    "updated_at": "2026-01-15T10:30:00Z"
  },
  "assigned_by": "ffffffff-ffff-ffff-ffff-ffffffffffff",
  "assigned_at": "2026-01-15T10:30:00Z",
  "assigned_rep_name": "Mike Salesman"
}
```

**Errors:**
- `400 Bad Request` - Sales rep not found, wrong company, or validation error
- `404 Not Found` - Lead not found

**Required Role:** `EXECUTIVE` or `CSR`

**Note:** The assignment is tracked in the lead's `extra_metadata` with full history of who assigned it and when.

---

### PUT `/leads/{lead_id}/status`

Update lead status.

**Path Parameters:**
- `lead_id` (UUID, required) - Lead UUID

**Request Body:**
```json
{
  "status": "qualified_booked"
}
```

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Example Request:**
```
PUT /api/v1/leads/20000000-0000-0000-0000-000000000001/status
Content-Type: application/json

{
  "status": "qualified_booked"
}
```

**Response:** `200 OK`
```json
{
  "id": "20000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "contact_card_id": "10000000-0000-0000-0000-000000000001",
  "status": "qualified_booked",
  "deal_status": "qualified",
  "assigned_rep_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "deal_size": 5000.00,
  "closed_at": null,
  "extra_metadata": null,
  "call_audio_urls": [
    "https://storage.example.com/audio/call1.mp3"
  ],
  "created_at": "2025-10-20T10:00:00Z",
  "updated_at": "2026-01-15T10:30:00Z",
  "name": "Alice Johnson",
  "phone_number": "+1-555-1001",
  "reason_not_booked": null,
  "objection": null,
  "response": null
}
```

**Valid Status Values:**
- `new`, `warm`, `hot`
- `qualified_booked`, `qualified_unbooked`, `qualified_service_not_offered`
- `nurturing`, `dormant`, `abandoned`
- `closed_won`, `closed_lost`

**Errors:**
- `400 Bad Request` - Invalid status value
- `404 Not Found` - Lead not found

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

**Example Request:**
```
GET /api/v1/metrics/exec/company-overview?company_id=11111111-1111-1111-1111-111111111111
```

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "total_leads": 5,
  "active_leads": 3,
  "qualified_leads": 0,
  "total_calls": 6,
  "missed_calls": 0,
  "total_appointments": 3,
  "conversion_rate": 0.0,
  "total_revenue": 0.0,
  "start_date": "2025-12-16T00:00:00",
  "end_date": "2026-01-15T23:59:59"
}
```

**Note:** Response values reflect actual data from seed_dummy_data.sql

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
      "created_at": "2026-01-08T10:00:00Z",
      "name": "Alice Johnson",
      "phone_number": "+1-555-1001"
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

### GET `/metrics/csr/me/profile`

Get current CSR's own profile with all metrics, rank, and coaching insights.

**Query Parameters:**
- `start_date` (date, optional) - Start date (YYYY-MM-DD, defaults to 30 days ago)
- `end_date` (date, optional) - End date (YYYY-MM-DD, defaults to today)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "user": {
    "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "email": "csr1@acme.com",
    "first_name": "Lisa",
    "last_name": "Support",
    "role": "csr",
    "rank": 1
  },
  "kpis": {
    "total_calls": 50,
    "answered_calls": 45,
    "missed_calls": 5,
    "leads_assigned": 30,
    "appointments_scheduled": 25,
    "booking_rate": 55.6,
    "avg_response_time": 8.5
  },
  "executive_view": {
    "booking_rate": 55.6,
    "conversion_rate": 45.0,
    "calls_answered": 45,
    "avg_response_time": 8.5,
    "response_time_status": "on_target"
  },
  "coaching_insights": [
    {
      "type": "response_time",
      "message": "Excellent response time, consistently below target",
      "avg_response_time": 8.5,
      "response_time_target": 15.0,
      "response_time_status": "on_target"
    }
  ],
  "start_date": "2025-12-16T00:00:00",
  "end_date": "2026-01-15T23:59:59"
}
```

**Required Role:** `CSR` (returns own profile only)

---

### GET `/metrics/csr/{user_id}/profile`

Get comprehensive CSR profile with all metrics, rank, and coaching insights.

**Path Parameters:**
- `user_id` (UUID, required) - CSR user UUID

**Query Parameters:**
- `start_date` (date, optional) - Start date (YYYY-MM-DD, defaults to 30 days ago)
- `end_date` (date, optional) - End date (YYYY-MM-DD, defaults to today)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Example Request:**
```
GET /api/v1/metrics/csr/ffffffff-ffff-ffff-ffff-ffffffffffff/profile?start_date=2025-12-01&end_date=2026-01-08
```

**Response:** `200 OK`
```json
{
  "user": {
    "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "email": "csr1@acme.com",
    "first_name": "Lisa",
    "last_name": "Support",
    "role": "csr",
    "rank": 1
  },
  "kpis": {
    "total_calls": 50,
    "answered_calls": 45,
    "missed_calls": 5,
    "leads_assigned": 30,
    "appointments_scheduled": 25,
    "booking_rate": 55.6,
    "avg_response_time": 8.5
  },
  "executive_view": {
    "booking_rate": 55.6,
    "conversion_rate": 45.0,
    "calls_answered": 45,
    "avg_response_time": 8.5,
    "response_time_status": "on_target"
  },
  "coaching_insights": [
    {
      "type": "response_time",
      "message": "Excellent response time, consistently below target",
      "avg_response_time": 8.5,
      "response_time_target": 15.0,
      "response_time_status": "on_target"
    },
    {
      "type": "objection_handling",
      "message": "Needs improvement in handling price objections",
      "objection_type": "price",
      "affected_calls": 5
    }
  ],
  "start_date": "2025-12-01T00:00:00",
  "end_date": "2026-01-08T23:59:59"
}
```

**Required Role:** `CSR` or `EXECUTIVE`

**Note:** Response time is calculated from the `answered_at` field on calls. The target response time is 15 seconds. Status can be:
- `on_target`: ≤ 15 seconds
- `above_target`: > 15 seconds but ≤ 22.5 seconds
- `below_target`: > 22.5 seconds

---

## Analytics

### GET `/analytics/top-objections`

Get top objections aggregated by company.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID

**Example Request:**
```
GET /api/v1/analytics/top-objections?company_id=11111111-1111-1111-1111-111111111111
```

**Response:** `200 OK`
```json
[
  {
    "objection_type": "pricing",
    "count": 3,
    "affected_leads_count": 2
  },
  {
    "objection_type": "price",
    "count": 2,
    "affected_leads_count": 2
  }
]
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/analytics/objection-calls`

Get calls filtered by objection type and optionally by CSR owner.

**Query Parameters:**
- `objection` (string, required) - Objection type (e.g., `price`, `timing`, `authority`)
- `company_id` (UUID, required) - Company UUID
- `owner_id` (UUID, optional) - Filter by CSR/owner UUID

**Example Request:**
```
GET /api/v1/analytics/objection-calls?objection=price&company_id=11111111-1111-1111-1111-111111111111
```

**Response:** `200 OK`
```json
[
  {
    "call_id": "30000000-0000-0000-0000-000000000001",
    "contact_card": {
      "id": "10000000-0000-0000-0000-000000000001",
      "first_name": "Alice",
      "last_name": "Johnson",
      "primary_phone": "+1-555-1001"
    },
    "audio_url": "https://storage.example.com/audio/call1.mp3",
    "qualification_status": "qualified",
    "booking_status": "not_booked"
  }
]
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

## Call Processing (Shunya)

### POST `/call-processing/process`

Submit a call for AI processing.

**Request Body:**
```json
{
  "call_id": "30000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "audio_url": "https://storage.example.com/audio/call1.mp3",
  "phone_number": "+1-555-1001",
  "duration": 180,
  "call_date": "2025-10-20T10:30:00Z",
  "metadata": {
    "call_type": "csr_call",
    "source": "twilio"
  },
  "options": {
    "skip_rag_indexing": false,
    "skip_summary_generation": false,
    "priority": "normal"
  }
}
```

**Response:** `202 Accepted`
```json
{
  "job_id": "80000000-0000-0000-0000-000000000001",
  "call_id": "30000000-0000-0000-0000-000000000001",
  "status": "queued",
  "message": "Call processing job created",
  "status_url": "/api/v1/call-processing/status/80000000-0000-0000-0000-000000000001",
  "created_at": "2026-01-15T10:30:00Z"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/call-processing/status/{job_id}`

Get call processing job status.

**Path Parameters:**
- `job_id` (UUID, required) - Job UUID

**Example Request:**
```
GET /api/v1/call-processing/status/80000000-0000-0000-0000-000000000003
```

**Response:** `200 OK`
```json
{
  "job_id": "80000000-0000-0000-0000-000000000003",
  "status": "completed",
  "progress_percent": 100,
  "current_step": "completed",
  "summary_url": "https://storage.example.com/summaries/job003.json",
  "chunks_url": "https://storage.example.com/chunks/job003.json",
  "transcript_url": "https://storage.example.com/transcripts/job003.txt"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/call-processing/summary/{call_id}`

Get call summary with compliance analysis, objections, qualification.

**Path Parameters:**
- `call_id` (UUID, required) - Call UUID

**Query Parameters:**
- `include_chunks` (boolean, optional, default: false) - Include call chunks

**Example Request:**
```
GET /api/v1/call-processing/summary/30000000-0000-0000-0000-000000000001?include_chunks=false
```

**Response:** `200 OK`
```json
{
  "call_id": "30000000-0000-0000-0000-000000000001",
  "summary": "Customer inquired about pricing and expressed concerns about cost.",
  "qualification_status": "qualified",
  "booking_status": "not_booked",
  "objections": ["price", "pricing"],
  "sop_compliance_score": 75.5,
  "sentiment_score": 0.65
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/call-processing/chunks/{call_id}`

Get call chunks with summaries and Milvus IDs.

**Path Parameters:**
- `call_id` (UUID, required) - Call UUID

**Response:** `200 OK`
```json
{
  "call_id": "30000000-0000-0000-0000-000000000001",
  "chunks": [
    {
      "chunk_id": "chunk_001",
      "text": "Hello, I am interested in your services.",
      "summary": "Customer greeting and interest",
      "milvus_id": "milvus_123"
    }
  ]
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### POST `/call-processing/retry/{job_id}`

Retry a failed call processing job.

**Path Parameters:**
- `job_id` (UUID, required) - Job UUID

**Response:** `202 Accepted`
```json
{
  "job_id": "80000000-0000-0000-0000-000000000005",
  "status": "queued",
  "message": "Job retry initiated"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

## Ask Otto (Shunya)

### POST `/ask-otto/conversations`

Create a new Ask Otto conversation.

**Request Body:**
```json
{
  "company_id": "11111111-1111-1111-1111-111111111111",
  "context": {
    "user_role": "executive",
    "focus_area": "sales"
  }
}
```

**Response:** `201 Created`
```json
{
  "id": "90000000-0000-0000-0000-000000000001",
  "conversation_id": "shunya_conv_001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "title": "Sales Performance Questions",
  "created_at": "2026-01-10T10:00:00Z"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### POST `/ask-otto/conversations/{conversation_id}/messages`

Send a message in an Ask Otto conversation.

**Path Parameters:**
- `conversation_id` (UUID, required) - Conversation UUID

**Request Body:**
```json
{
  "message": "What are the top objections this week?"
}
```

**Response:** `200 OK`
```json
{
  "message_id": "a0000000-0000-0000-0000-000000000002",
  "role": "assistant",
  "content": "The top objections this week are: 1. Price (40%), 2. Timing (25%), 3. Competitor (20%)",
  "created_at": "2026-01-10T10:00:05Z"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/ask-otto/conversations/{conversation_id}/messages`

Get all messages in an Ask Otto conversation.

**Path Parameters:**
- `conversation_id` (UUID, required) - Conversation UUID

**Response:** `200 OK`
```json
[
  {
    "id": "a0000000-0000-0000-0000-000000000001",
    "role": "user",
    "content": "What are the top objections this week?",
    "created_at": "2026-01-10T10:00:00Z"
  },
  {
    "id": "a0000000-0000-0000-0000-000000000002",
    "role": "assistant",
    "content": "The top objections this week are...",
    "created_at": "2026-01-10T10:00:05Z"
  }
]
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### GET `/ask-otto/conversations/{conversation_id}`

Get Ask Otto conversation details.

**Path Parameters:**
- `conversation_id` (UUID, required) - Conversation UUID

**Response:** `200 OK`
```json
{
  "id": "90000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "title": "Sales Performance Questions",
  "created_at": "2026-01-10T10:00:00Z",
  "updated_at": "2026-01-11T10:00:00Z"
}
```

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

### DELETE `/ask-otto/conversations/{conversation_id}`

Delete an Ask Otto conversation.

**Path Parameters:**
- `conversation_id` (UUID, required) - Conversation UUID

**Response:** `204 No Content`

**Required Role:** `CSR`, `SALES_REP`, or `EXECUTIVE`

---

## Insights (Shunya)

### POST `/insights/generate`

Generate insights for specified companies and week range.

**Request Body:**
```json
{
  "week_start": "2026-01-08",
  "week_end": "2026-01-15",
  "company_ids": ["11111111-1111-1111-1111-111111111111"],
  "insight_types": ["company", "customer", "objection"],
  "webhook_url": null,
  "options": {
    "force_regenerate": false,
    "include_inactive_customers": false
  }
}
```

**Response:** `202 Accepted`
```json
{
  "job_id": "b0000000-0000-0000-0000-000000000001",
  "status": "queued",
  "message": "Insight generation job created"
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/insights/status/{job_id}`

Get insight generation job status.

**Path Parameters:**
- `job_id` (UUID, required) - Job UUID

**Response:** `200 OK`
```json
{
  "job_id": "b0000000-0000-0000-0000-000000000003",
  "status": "completed",
  "week_start": "2025-12-18",
  "week_end": "2025-12-25",
  "results": {
    "insights": [
      {
        "type": "objection",
        "data": {
          "top_objections": ["price", "timing", "competitor"]
        }
      }
    ]
  }
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/insights/company/{company_id}/current`

Get current company insight.

**Path Parameters:**
- `company_id` (UUID, required) - Company UUID

**Response:** `200 OK`
```json
{
  "company_id": "11111111-1111-1111-1111-111111111111",
  "week_start": "2026-01-08",
  "week_end": "2026-01-15",
  "insights": {
    "trends": "positive",
    "top_objections": ["price", "timing"]
  }
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/insights/customers`

Get customer insights with pagination and filters.

**Query Parameters:**
- `company_id` (UUID, required) - Company UUID
- `week_start` (date, optional) - Week start date (YYYY-MM-DD)
- `status` (string, optional) - Filter by status (`active`, `inactive`)
- `priority` (string, optional) - Filter by priority (`high`, `medium`, `low`)
- `page` (int, default: 1) - Page number
- `limit` (int, default: 50) - Items per page

**Response:** `200 OK`
```json
{
  "customers": [],
  "total": 0,
  "page": 1,
  "limit": 50
}
```

**Required Role:** `EXECUTIVE`

---

### GET `/insights/objections/{company_id}`

Get objection insights for a company.

**Path Parameters:**
- `company_id` (UUID, required) - Company UUID

**Response:** `200 OK`
```json
{
  "company_id": "11111111-1111-1111-1111-111111111111",
  "top_objections": ["price", "timing", "competitor"],
  "trends": "increasing"
}
```

**Required Role:** `EXECUTIVE`

---

## RAG / Ask Otto

### POST `/rag/ask-otto`

Query Ask Otto (RAG-based AI copilot) - Company scope.

**Request Body:**
```json
{
  "query": "What are the top objections this month?",
  "context": {
    "company_id": "11111111-1111-1111-1111-111111111111"
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
  "company_id": "11111111-1111-1111-1111-111111111111",
  "phone_number": "+1-555-1001",
  "audio_url": "https://storage.example.com/audio/call1.mp3",
  "call_type": "csr_call",
  "missed_call": false,
  "duration_seconds": 180,
  "call_date": "2025-10-20T10:30:00Z",
  "metadata": {
    "source": "twilio",
    "call_sid": "CA1234567890"
  }
}
```

**Headers (alternative):**
```
X-Company-Id: 11111111-1111-1111-1111-111111111111
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "call_id": "30000000-0000-0000-0000-000000000001"
}
```

**Error:** `400 Bad Request` - Missing required fields

---

### POST `/webhooks/shoonya/job-complete`

Handle job completion webhook from Shoonya (call analysis).

**Request Body:**
```json
{
  "job_id": "shunya_job_completed_003",
  "status": "completed",
  "call_id": "30000000-0000-0000-0000-000000000001",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "results": {
    "summary_url": "https://storage.example.com/summaries/job003.json",
    "chunks_url": "https://storage.example.com/chunks/job003.json",
    "transcript_url": "https://storage.example.com/transcripts/job003.txt"
  },
  "metadata": {}
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "call_id": "30000000-0000-0000-0000-000000000001",
  "analysis_id": "40000000-0000-0000-0000-000000000001"
}
```

**Error:** `400 Bad Request` - Missing required fields or invalid format

---

## Invites

### POST `/invites`

Create a new user invitation.

**Request Body:**
```json
{
  "email": "invitee@example.com",
  "role": "sales_rep",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "message": "Welcome to our team!"
}
```

**Response:** `201 Created`
```json
{
  "id": "60000000-0000-0000-0000-000000000001",
  "email": "invitee@example.com",
  "company_id": "11111111-1111-1111-1111-111111111111",
  "role": "sales_rep",
  "status": "pending",
  "expires_at": "2026-01-22T10:00:00Z",
  "created_at": "2026-01-15T10:00:00Z"
}
```

**Required Role:** `EXECUTIVE`

---

### POST `/invites/accept/{token}`

Accept an invitation and create user account.

**Path Parameters:**
- `token` (string, required) - Invitation token

**Request Body:**
```json
{
  "token": "token_pending_12345",
  "password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "user": {
    "id": "new-user-id",
    "email": "invitee@example.com",
    "role": "sales_rep",
    "company_id": "11111111-1111-1111-1111-111111111111"
  }
}
```

**No authentication required**

---

## Onboarding

### POST `/onboarding/validate-ghl`

Verify GoHighLevel (GHL) credentials before final submission.

**Request Body:**
```json
{
  "location_id": "NYC-001",
  "api_key": "your_ghl_api_key_here"
}
```

**Response:** `200 OK`
```json
{
  "company_id": "sf_company_12345",
  "company_name": "Acme Corporation"
}
```

**Error:** `401 Unauthorized` - Invalid GHL API key or location ID

**Note:** This endpoint validates credentials without creating any records. Use this before calling `/onboarding/complete`.

---

### POST `/onboarding/validate-ctm`

Verify Call Tracking Metrics (CTM) credentials before final submission.

**Request Body:**
```json
{
  "access_key": "your_ctm_access_key",
  "secret_key": "your_ctm_secret_key"
}
```

**Response:** `200 OK`
```json
{
  "secret_key": "encrypted_secret_key",
  "company_name": "Acme Corporation",
  "company_id": "ctm_company_67890"
}
```

**Error:** `401 Unauthorized` - Invalid CTM access key or secret key

**Note:** This endpoint validates credentials without creating any records. Use this before calling `/onboarding/complete`.

---

### POST `/onboarding/complete`

Complete onboarding: create user, company, integration, and upload documents.

This endpoint performs an atomic operation:
1. Validates all fields and files
2. Uploads documents to S3
3. Creates Company, User, and CompanyIntegration records in a transaction

**Request Body (multipart/form-data):**
- `firstName` (string, required) - User's first name
- `lastName` (string, required) - User's last name
- `email` (string, required) - User's email address
- `password` (string, required) - User's password
- `companyName` (string, required) - Company name
- `location_id` (string, required) - GHL location ID
- `crm_provider` (string, required) - CRM provider (e.g., "gohighlevel", "salesforce", "hubspot")
- `crm_api_key` (string, required) - CRM API key (will be encrypted)
- `crm_company_id` (string, required) - CRM company ID
- `voip_provider` (string, required) - VoIP provider (e.g., "ringcentral", "twilio", "callrail")
- `voip_api_key` (string, required) - VoIP API key (will be encrypted)
- `voip_company_id` (string, required) - VoIP company ID
- `reference_doc` (file, required) - Reference document file (PDF, DOCX, etc.)
- `sop_doc` (file, required) - SOP document file (PDF, DOCX, etc.)

**Example Request (using curl):**
```bash
curl -X POST "http://localhost:8000/api/v1/onboarding/complete" \
  -F "firstName=John" \
  -F "lastName=Doe" \
  -F "email=john.doe@example.com" \
  -F "password=SecurePassword123!" \
  -F "companyName=Acme Corp" \
  -F "location_id=NYC-001" \
  -F "crm_provider=gohighlevel" \
  -F "crm_api_key=ghl_api_key_123" \
  -F "crm_company_id=sf_company_12345" \
  -F "voip_provider=ringcentral" \
  -F "voip_api_key=rc_api_key_456" \
  -F "voip_company_id=rc_company_67890" \
  -F "reference_doc=@/path/to/reference.pdf" \
  -F "sop_doc=@/path/to/sop.pdf"
```

**Response:** `201 Created`
```json
{
  "id": "new-user-uuid",
  "email": "john.doe@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "role": "executive",
  "company_id": "new-company-uuid",
  "created_at": "2026-01-15T10:00:00Z"
}
```

**Errors:**
- `400 Bad Request` - Validation fails, user already exists, or files missing
- `500 Internal Server Error` - Creation fails

**Note:**
- The user is created with `EXECUTIVE` role by default (company owner)
- API keys are encrypted before storage
- Documents are uploaded to S3 and URLs are stored in the company record
- If any step fails, uploaded S3 files should be cleaned up manually

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
- UUIDs are in standard format (e.g., `11111111-1111-1111-1111-111111111111`)
- Metrics endpoints default to last 30 days if `start_date` and `end_date` are not provided
- Webhook endpoints do not require authentication but should implement signature verification in production
- All example UUIDs in this documentation match the seed data in `backend/seed_dummy_data.sql`
- The Postman collection (`backend/app/docs/postman_collection.json`) uses variables for easy testing with different data

---

## Quick Reference: Seed Data IDs

For quick testing, here are the main IDs from seed data:

| Type | ID | Description |
|------|-----|-------------|
| Company | `11111111-1111-1111-1111-111111111111` | Acme Corporation |
| User (Executive) | `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` | exec@acme.com |
| User (Sales Rep) | `cccccccc-cccc-cccc-cccc-cccccccccccc` | sales1@acme.com |
| User (CSR) | `ffffffff-ffff-ffff-ffff-ffffffffffff` | csr1@acme.com |
| Contact Card | `10000000-0000-0000-0000-000000000001` | Alice Johnson |
| Lead | `20000000-0000-0000-0000-000000000001` | Qualified Booked |
| Lead (Unbooked) | `20000000-0000-0000-0000-000000000002` | Qualified Unbooked |
| Call | `30000000-0000-0000-0000-000000000001` | Sales call |
| Call Analysis | `40000000-0000-0000-0000-000000000001` | Completed analysis |
| Appointment | `50000000-0000-0000-0000-000000000001` | Pending appointment |
| Call Processing Job | `80000000-0000-0000-0000-000000000003` | Completed job |
| Ask Otto Conversation | `90000000-0000-0000-0000-000000000001` | Sales Performance |
| Insight Job | `b0000000-0000-0000-0000-000000000003` | Completed insights |

