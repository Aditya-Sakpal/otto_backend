# Task Management API

This document describes the Task Management APIs for the **Executive** and **CSR** task management tabs.

- **Screenshot reference:** **ss1** = CSR Task Management tab (“My Tasks” – action items assigned to you from call logs). **ss2** = Executive Task Management tab (“Task Management” – manage and assign action items from call logs across the company).

**Base URL:** `{{base_url}}/api/v1`

---

## Table of contents

- [Executive Guide](#executive-guide) – APIs for the Executive Task Management tab (ss2)
- [CSR Guide](#csr-guide) – APIs for the CSR My Tasks tab (ss1)
- [Task status values](#task-status-values)
- [Error responses](#error-responses)

---

## Executive Guide

APIs for the **Executive Task Management** tab (ss2): list all company tasks, filter by status/priority/assignee, create tasks, reassign, and manage action items from call logs.

---

### 1. List tasks (with summary)

**Endpoint:** `GET /tasks`

**Description:**  
Returns the task list for the company with summary counts (Total, Pending, In Progress, Completed, Cancelled) for the dashboard cards. Supports filtering by status, priority, assignee, search, and date ranges.

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json (optional for GET) |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| company_id | UUID | Yes | Company ID. |
| status | string | No | Filter: `pending`, `in_progress`, `completed`, `cancelled`. |
| priority | int | No | Filter by priority (integer). |
| assignee_id | UUID | No | Filter by assignee (owner) user ID. |
| search | string | No | Search in task title/description or customer name/phone/email from source call. |
| start_date | datetime | No | Filter tasks created on or after (ISO 8601). |
| end_date | datetime | No | Filter tasks created on or before (ISO 8601). |
| due_date_from | datetime | No | Filter by due date on or after. |
| due_date_to | datetime | No | Filter by due date on or before. |
| skip | int | No | Pagination offset (default: 0). |
| limit | int | No | Page size (default: 100, max: 500). |

**Response Body (200):**
```json
{
  "summary": {
    "total_tasks": 6,
    "pending": 2,
    "in_progress": 2,
    "completed": 1,
    "cancelled": 1
  },
  "tasks": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "action_type": "follow_up_call",
      "raw_text": "Follow up on pricing inquiry",
      "status": "pending",
      "priority": 1,
      "due_at": "2026-02-03T00:00:00Z",
      "created_at": "2026-02-01T10:30:00Z",
      "updated_at": null,
      "owner_id": "uuid",
      "assigned_to": { "user_id": "uuid", "first_name": "Sarah", "last_name": "Johnson", "full_name": "Sarah Johnson", "role": "csr", "email": "sarah@example.com" },
      "assigned_by": { "user_id": "uuid", "first_name": "Michael", "last_name": "Roberts", "full_name": "Michael Roberts", "role": "executive", "email": "michael@example.com" },
      "source_call": { "call_id": "uuid", "customer_name": "John Smith", "customer_phone": "(555) 123-4567", "call_date": "2026-02-01T10:30:00Z", "call_created_at": "2026-02-01T10:30:00Z" },
      "call_id": "uuid",
      "lead_id": "uuid",
      "assigned_by_id": "uuid"
    }
  ],
  "total": 6,
  "skip": 0,
  "limit": 100
}
```

---

### 2. Get single task

**Endpoint:** `GET /tasks/{task_id}`

**Description:**  
Returns one task by ID with full details: assignee, assigned-by user, source call info, and source (e.g. manual, shunya).

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id | UUID | Yes (path) | Task (pending action) ID. |

**Response Body (200):** Same shape as one element of `tasks` in the list response, plus: `appointment_id`, `assigned_by`, `source`.  
**Response (404):** Task not found.

---

### 3. Create task (manual)

**Endpoint:** `POST /tasks`

**Description:**  
Creates a task manually (not from a call). Executives can optionally assign it to a CSR or Sales Rep. Backend sets `assigned_by_id` to the current user.

**Request Body:**
```json
{
  "company_id": "uuid",
  "action_type": "follow_up_call",
  "raw_text": "Follow up on pricing inquiry",
  "status": "pending",
  "priority": 1,
  "due_at": "2026-02-03T17:00:00Z",
  "owner_id": "uuid",
  "lead_id": "uuid",
  "call_id": "uuid",
  "appointment_id": "uuid"
}
```
| Field | Type | Required | Description |
|--------|------|----------|-------------|
| company_id | UUID | Yes | Company ID. |
| action_type | string | Yes | e.g. `follow_up_call`, `send_quote`. |
| raw_text | string | No | Task title/description. |
| status | string | No | Default `pending`. Allowed: `pending`, `in_progress`, `completed`, `cancelled`. |
| priority | int | No | Higher = more urgent. |
| due_at | datetime | No | Due date/time (ISO 8601). |
| owner_id | UUID | No | Assign to this user (CSR or Sales Rep). |
| lead_id | UUID | No | Optional lead ID. |
| call_id | UUID | No | Optional call ID (link to source call). |
| appointment_id | UUID | No | Optional appointment ID. |

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json |

**Params:** None (body only).

**Response Body (201):** Created task (PendingAction: `id`, `company_id`, `status`, `owner_id`, `assigned_by_id`, `created_at`, etc.).

---

### 4. Update task (reassign, status, priority, due date, description)

**Endpoint:** `PATCH /tasks/{task_id}`

**Description:**  
Updates a task: reassign (change owner), change status, priority, due date, or description. When `owner_id` is sent, the backend sets `assigned_by_id` to the current user.

**Request Body (all fields optional):**
```json
{
  "owner_id": "uuid",
  "status": "in_progress",
  "priority": 2,
  "due_at": "2026-02-05T17:00:00Z",
  "raw_text": "Updated task description"
}
```
| Field | Type | Description |
|--------|------|-------------|
| owner_id | UUID | Reassign to this user (CSR or Sales Rep). |
| status | string | `pending`, `in_progress`, `completed`, `cancelled`. |
| priority | int | Priority. |
| due_at | datetime | Due date/time. |
| raw_text | string | Task title/description. |

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Updated task (PendingAction).  
**Response (404):** Task not found.

---

### 5. Create task from a call (assign to CSR / Sales Rep)

**Endpoint:** `POST /calls/{call_id}/action-items`

**Description:**  
Creates a task linked to a specific call and assigns it to a user. Use when creating an action item from the call log. Backend sets `assigned_by_id` to the current user.

**Request Body:**
```json
{
  "owner_id": "uuid",
  "action_type": "follow_up_call",
  "raw_text": "Call back to confirm appointment",
  "due_at": "2026-02-03T17:00:00Z",
  "priority": 1
}
```
| Field | Type | Required | Description |
|--------|------|----------|-------------|
| owner_id | UUID | Yes | User to assign the task to (CSR or Sales Rep). |
| action_type | string | Yes | e.g. `follow_up_call`, `send_quote`. |
| raw_text | string | No | Description. |
| due_at | datetime | No | Due date/time. |
| priority | int | No | Priority. |

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| call_id | UUID | Yes (path) | Call ID. |

**Response Body (201):** Created task (PendingAction).  
**Response (404):** Call not found.

---

### 6. Complete task (shortcut)

**Endpoint:** `PATCH /metrics/actions/pending/{action_id}/complete`

**Description:**  
Marks a task as completed. Same effect as `PATCH /tasks/{task_id}` with `"status": "completed"`. Use for “Mark Complete” in the UI.

**Request Body:** N/A (empty body or `{}`).

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| action_id | UUID | Yes (path) | Task (pending action) ID. |

**Response Body (200):** Updated task (PendingAction with `status: "completed"`).  
**Response (404):** Task not found.

---

### 7. Reopen task (shortcut)

**Endpoint:** `PATCH /metrics/actions/pending/{action_id}/reopen`

**Description:**  
Sets a completed task back to pending. Use when a user mistakenly marked a task complete and needs to undo.

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| action_id | UUID | Yes (path) | Task (pending action) ID. |

**Response Body (200):** Updated task (PendingAction with `status: "pending"`).  
**Response (404):** Task not found.

---

### 8. Get assignable users (for “Assign” dropdown)

**Endpoint:** `GET /users/assignees`

**Description:**  
Returns users who can be assigned tasks (CSRs and Sales Reps by default) for the company. Use for the “All Assignees” filter and the “Assign” button dropdown on the Executive tab.

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| company_id | UUID | Yes | Company ID. |
| roles | string | No | Comma-separated: `csr`, `sales_rep` (default: both). |

**Response Body (200):** Array of user objects:
```json
[
  { "id": "uuid", "email": "csr1@example.com", "first_name": "Sarah", "last_name": "Johnson", "role": "csr", "company_id": "uuid", "is_active": true, "created_at": "..." }
]
```

---

## CSR Guide

APIs for the **CSR My Tasks** tab (ss1): view and manage only the action items assigned to the logged-in user. Use the same endpoints as the Executive guide; the main difference is passing **`assignee_id` = current user’s ID** when listing tasks so summary and list are scoped to “my tasks.”

---

### 1. List my tasks (with summary)

**Endpoint:** `GET /tasks`

**Description:**  
Returns the task list and summary counts for **tasks assigned to the current user only**. Use for the My Tasks dashboard: Total, Pending, In Progress, Completed, completion rate, and progress bar. Summary and list respect the same filters (e.g. status, priority, search).

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| company_id | UUID | Yes | Company ID (from auth/session). |
| assignee_id | UUID | Yes (for My Tasks) | **Current user’s ID** so only their tasks are returned. |
| status | string | No | Filter: `pending`, `in_progress`, `completed`, `cancelled`. |
| priority | int | No | Filter by priority. |
| search | string | No | Search in task title/description or customer name/phone/email. |
| skip | int | No | Pagination offset (default: 0). |
| limit | int | No | Page size (default: 100, max: 500). |

**Response Body (200):** Same structure as Executive list response. `summary` and `tasks` are scoped to the user’s tasks. Each task includes `assigned_by` (who assigned) and `source_call.customer_phone` for the source call contact.

**UI mapping (ss1):** Total tasks, Pending, In Progress, Completed → `summary.*`. Completion rate → `summary.completed / summary.total_tasks`. Progress bar → “X of Y completed” from `summary.completed`, `summary.total_tasks`. High priority count → derive from `tasks[].priority` (e.g. count where priority in “high” band).

---

### 2. Get single task (task details / expanded card)

**Endpoint:** `GET /tasks/{task_id}`

**Description:**  
Returns full details for one task. Use when the CSR expands a task card or opens task details (customer name, phone, original call, assigned by, created, due date).

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Single task object with `assigned_to`, `assigned_by`, `source_call` (customer_name, customer_phone, call_date, call_created_at), `created_at`, `due_at`, `raw_text`, `status`, `priority`, `source`.  
**Response (404):** Task not found.

---

### 3. Start task

**Endpoint:** `PATCH /tasks/{task_id}`

**Description:**  
Updates the task status to “in progress.” Use when the CSR clicks “Start Task” on a task card.

**Request Body:**
```json
{
  "status": "in_progress"
}
```

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Updated task (PendingAction with `status: "in_progress"`).  
**Response (404):** Task not found.

---

### 4. Mark task complete

**Endpoint:** `PATCH /tasks/{task_id}` **or** `PATCH /metrics/actions/pending/{action_id}/complete`

**Description:**  
Marks the task as completed. Use when the CSR clicks “Mark Complete.” Either send a PATCH to `/tasks/{task_id}` with `status: "completed"` or use the complete shortcut.

**Request Body (for PATCH /tasks/{task_id}):**
```json
{
  "status": "completed"
}
```
For `PATCH /metrics/actions/pending/{action_id}/complete`: no body.

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json (only for PATCH /tasks/{task_id}) |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id / action_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Updated task (PendingAction with `status: "completed"`).  
**Response (404):** Task not found.

---

### 5. Reopen task

**Endpoint:** `PATCH /metrics/actions/pending/{action_id}/reopen`

**Description:**  
Sets a completed task back to pending. Use when the CSR needs to undo “Mark Complete.”

**Request Body:** N/A

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| action_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Updated task (PendingAction with `status: "pending"`).  
**Response (404):** Task not found.

---

### 6. Update task (due date, priority, description)

**Endpoint:** `PATCH /tasks/{task_id}`

**Description:**  
Updates the task’s due date, priority, or description. Use when the CSR edits task details from the “…” menu (if the UI allows).

**Request Body (all fields optional):**
```json
{
  "due_at": "2026-02-05T17:00:00Z",
  "priority": 2,
  "raw_text": "Updated description"
}
```

**Headers:**
| Key | Value |
|-----|--------|
| Authorization | Bearer \<token\> |
| Content-Type | application/json |

**Params:**

| Param | Type | Required | Description |
|--------|------|----------|-------------|
| task_id | UUID | Yes (path) | Task ID. |

**Response Body (200):** Updated task.  
**Response (404):** Task not found.

---

**Note for CSR:** CSRs **cannot** create tasks via `POST /tasks` (EXECUTIVE only). Tasks appear in My Tasks when an Executive (or another user with access) assigns them via the Executive tab or via `POST /calls/{call_id}/action-items`.

---

## Task status values

- `pending` – Not started
- `in_progress` – In progress
- `completed` – Done
- `cancelled` – Cancelled
- `converted` – (Internal) Converted to another outcome

Use `pending`, `in_progress`, `completed`, and `cancelled` in filters and when creating/updating tasks.

---

## Error responses

- **400** – Bad request (e.g. invalid body or query).
- **403** – Forbidden (role or permission).
- **404** – Task or call not found.
- **422** – Validation error (invalid UUID, date, etc.).
- **500** – Internal server error.

All errors return a JSON body with a `detail` message.
