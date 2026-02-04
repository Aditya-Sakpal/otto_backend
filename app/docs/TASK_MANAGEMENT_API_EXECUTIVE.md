# Task Management API – Executive Guide

This document describes the **Task Management** APIs for executives (and CSRs/Sales Reps) to manage and assign action items from call logs. Use these endpoints to power the Task Management dashboard: list tasks, view details, create tasks, reassign or update tasks, and load assignee dropdowns.

**Base URL:** `{{base_url}}/api/v1` (e.g. `https://your-api.example.com/api/v1`)

**Authentication:** All endpoints require a valid JWT in the `Authorization: Bearer <token>` header.

---

## 1. List tasks (with summary)

**GET** `/tasks`

Returns the task list for the company with **summary counts** for the dashboard cards (Total, Pending, In Progress, Completed, Cancelled), plus paginated task items with assignee and source call info.

**Query parameters**

| Parameter       | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `company_id`   | UUID   | Yes      | Company ID. |
| `status`       | string | No       | Filter by status: `pending`, `in_progress`, `completed`, `cancelled`. |
| `priority`     | int    | No       | Filter by priority (integer). |
| `assignee_id`  | UUID   | No       | Filter by assignee (owner) user ID. |
| `search`       | string | No       | Search in task title/description (`raw_text`) or customer name/phone/email from source call. |
| `start_date`   | datetime | No     | Filter tasks created on or after (ISO 8601). |
| `end_date`     | datetime | No     | Filter tasks created on or before (ISO 8601). |
| `due_date_from`| datetime | No     | Filter by due date on or after. |
| `due_date_to`  | datetime | No     | Filter by due date on or before. |
| `skip`         | int    | No       | Pagination offset (default: 0). |
| `limit`        | int    | No       | Page size (default: 100, max: 500). |

**Response (200)**

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
      "assigned_to": {
        "user_id": "uuid",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "full_name": "Sarah Johnson",
        "role": "csr",
        "email": "sarah@example.com"
      },
      "source_call": {
        "call_id": "uuid",
        "customer_name": "John Smith",
        "call_date": "2026-02-01T10:30:00Z",
        "call_created_at": "2026-02-01T10:30:00Z"
      },
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

**Access:** EXECUTIVE, CSR, SALES_REP

---

## 2. Get single task

**GET** `/tasks/{task_id}`

Returns one task by ID with full details: assignee, assigned-by user, and source call info.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_id` | UUID | Task (pending action) ID. |

**Response (200)**

Same shape as one element of `tasks` above, plus:

- `appointment_id`, `assigned_by` (user who assigned), `source` (e.g. `manual`, `shunya`).

**Response (404)** – Task not found.

**Access:** EXECUTIVE, CSR, SALES_REP

---

## 3. Create task (manual)

**POST** `/tasks`

Creates a task manually (not from a call). Executives can optionally assign it to a CSR or Sales Rep.

**Request body**

| Field            | Type   | Required | Description |
|------------------|--------|----------|-------------|
| `company_id`     | UUID   | Yes      | Company ID. |
| `action_type`    | string | Yes      | e.g. `follow_up_call`, `send_quote`. |
| `raw_text`       | string | No       | Task title/description. |
| `status`         | string | No       | Default `pending`. Allowed: `pending`, `in_progress`, `completed`, `cancelled`. |
| `priority`       | int    | No       | Higher = more urgent. |
| `due_at`         | datetime | No     | Due date/time (ISO 8601). |
| `owner_id`       | UUID   | No       | Assign to this user (CSR or Sales Rep). |
| `lead_id`        | UUID   | No       | Optional lead ID. |
| `call_id`        | UUID   | No       | Optional call ID (link to source call). |
| `appointment_id` | UUID   | No       | Optional appointment ID. |

**Example**

```json
{
  "company_id": "6d40b509-82bc-4d21-9614-de91cc25dc1b",
  "action_type": "follow_up_call",
  "raw_text": "Follow up on pricing inquiry",
  "status": "pending",
  "priority": 1,
  "due_at": "2026-02-03T17:00:00Z",
  "owner_id": "user-uuid-here"
}
```

**Response (201)** – Created task (same shape as PendingAction: `id`, `company_id`, `status`, `owner_id`, `assigned_by_id`, etc.).

**Access:** EXECUTIVE only

---

## 4. Update task (reassign, status, priority, due date, description)

**PATCH** `/tasks/{task_id}`

Updates a task: reassign (change owner), change status, priority, due date, or description. When you send `owner_id`, the backend records the current user as `assigned_by`.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_id` | UUID | Task ID. |

**Request body (all fields optional)**

| Field      | Type     | Description |
|------------|----------|-------------|
| `owner_id` | UUID     | Reassign to this user (CSR or Sales Rep). |
| `status`   | string   | `pending`, `in_progress`, `completed`, `cancelled`. |
| `priority` | int      | Priority. |
| `due_at`   | datetime | Due date/time. |
| `raw_text` | string   | Task title/description. |

**Example – reassign and set status**

```json
{
  "owner_id": "new-owner-user-uuid",
  "status": "in_progress"
}
```

**Example – mark completed**

```json
{
  "status": "completed"
}
```

**Example – cancel**

```json
{
  "status": "cancelled"
}
```

**Response (200)** – Updated task (PendingAction).

**Response (404)** – Task not found.

**Access:** EXECUTIVE, CSR, SALES_REP

---

## 5. Create task from a call (assign to CSR / Sales Rep)

**POST** `/calls/{call_id}/action-items`

Creates a task linked to a specific call and assigns it to a user. Use this when creating an action item from the call log.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `call_id` | UUID | Call ID. |

**Request body**

| Field       | Type     | Required | Description |
|-------------|----------|----------|-------------|
| `owner_id`  | UUID     | Yes      | User to assign the task to (CSR or Sales Rep). |
| `action_type` | string | Yes      | e.g. `follow_up_call`, `send_quote`. |
| `raw_text`  | string   | No       | Description. |
| `due_at`    | datetime | No       | Due date/time. |
| `priority`  | int      | No       | Priority. |

**Response (201)** – Created task (PendingAction).

**Response (404)** – Call not found.

**Access:** EXECUTIVE, CSR, SALES_REP

---

## 6. Complete task (shortcut)

**PATCH** `/metrics/actions/pending/{action_id}/complete`

Marks a task as completed. Same effect as `PATCH /tasks/{task_id}` with `"status": "completed"`.

**Response (200)** – Updated task.

**Response (404)** – Task not found.

**Access:** CSR, SALES_REP, EXECUTIVE

---

## 7. Reopen task (shortcut)

**PATCH** `/metrics/actions/pending/{action_id}/reopen`

Sets a completed task back to pending.

**Response (200)** – Updated task.

**Response (404)** – Task not found.

**Access:** CSR, SALES_REP, EXECUTIVE

---

## 8. Get assignable users (for “Assign” dropdown)

**GET** `/users/assignees`

Returns users who can be assigned tasks (CSRs and Sales Reps by default) for the company. Use for the “All Assignees” filter and the “Assign” button dropdown.

**Query parameters**

| Parameter     | Type | Required | Description |
|---------------|------|----------|-------------|
| `company_id`  | UUID | Yes      | Company ID. |
| `roles`       | string | No     | Comma-separated: `csr`, `sales_rep` (default: both). |

**Example:** `GET /users/assignees?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b`

**Response (200)** – Array of user objects (id, email, first_name, last_name, role, company_id, is_active, created_at).

**Access:** EXECUTIVE, CSR, SALES_REP

---

## Summary table

| Action                    | Method | Endpoint                                      | Access        |
|---------------------------|--------|-----------------------------------------------|---------------|
| List tasks + summary      | GET    | `/tasks?company_id=...`                       | EXEC, CSR, SR |
| Get one task              | GET    | `/tasks/{task_id}`                            | EXEC, CSR, SR |
| Create task (manual)      | POST   | `/tasks`                                      | EXEC only      |
| Update / reassign task    | PATCH  | `/tasks/{task_id}`                            | EXEC, CSR, SR |
| Create task from call     | POST   | `/calls/{call_id}/action-items`                | EXEC, CSR, SR |
| Complete task             | PATCH  | `/metrics/actions/pending/{id}/complete`       | EXEC, CSR, SR |
| Reopen task                | PATCH  | `/metrics/actions/pending/{id}/reopen`         | EXEC, CSR, SR |
| Get assignees (dropdown)  | GET    | `/users/assignees?company_id=...`              | EXEC, CSR, SR |

*EXEC = EXECUTIVE, SR = SALES_REP*

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
