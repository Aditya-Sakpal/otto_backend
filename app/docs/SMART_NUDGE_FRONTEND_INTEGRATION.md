# Smart Nudge — React Native Integration Guide

Smart nudges are AI-generated coaching notifications that surface rep performance changes to managers (Executives). They are generated automatically by a nightly cron job and whenever a 7-day coaching cycle completes.

This guide covers every API endpoint the frontend needs, the full data shapes, recommended UX patterns, and TypeScript types.

---

## Table of Contents

1. [How Smart Nudges Work](#how-smart-nudges-work)
2. [Auth & Role Requirements](#auth--role-requirements)
3. [Base URL & Headers](#base-url--headers)
4. [API Endpoints](#api-endpoints)
   - [GET /coaching/nudges — List Nudges](#get-coachingnudges)
   - [GET /coaching/nudges/unread-count — Badge Count](#get-coachingnudgesunread-count)
   - [POST /coaching/nudges/:id/read — Mark Read](#post-coachingnudgesidread)
   - [POST /coaching/nudges/:id/dismiss — Dismiss](#post-coachingnudgesiddismiss)
   - [POST /coaching/nudges/mark-all-read — Mark All Read](#post-coachingnudgesmark-all-read)
5. [Data Reference](#data-reference)
   - [NudgeType](#nudgetype)
   - [Priority](#priority)
   - [ReadStatus](#readstatus)
6. [TypeScript Types](#typescript-types)
7. [Recommended UX Patterns](#recommended-ux-patterns)
8. [Error Handling](#error-handling)

---

## How Smart Nudges Work

- **Daily generation:** Every night at 2:00 AM UTC the backend evaluates all active coaching sessions and generates nudges for significant metric changes, recurring issues, and target outcomes.
- **Cycle-end generation:** When a 7-day coaching cycle auto-completes, a `cycle_summary` nudge is created.
- **Expiry:** Nudges expire after **7 days** and are cleaned up automatically.
- **Per-user state:** Read/dismissed state is tracked per manager. Two executives looking at the same nudge each have their own `read_status`.
- **Deduplication:** The backend deduplicates nudges within a 7-day window so managers don't see the same alert twice.

---

## Auth & Role Requirements

All nudge endpoints require:
- A valid JWT in the `Authorization: Bearer <token>` header.
- The authenticated user must have role **EXECUTIVE** (managers/coaches). CSRs and Sales Reps cannot access these endpoints — calls will return `403 Forbidden`.

---

## Base URL & Headers

```
Base: /api/v1

Headers:
  Authorization: Bearer <access_token>
  Content-Type: application/json
```

---

## API Endpoints

### GET /coaching/nudges

Paginated list of smart nudges scoped to the manager's company. Use this to populate the notification panel.

**URL:** `GET /api/v1/coaching/nudges`

**Query Parameters:**

| Parameter    | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `company_id` | UUID   | Yes      | Company UUID (from auth context) |
| `status`     | string | No       | Filter by read state: `unread`, `read`, or `dismissed`. Omit for all. |
| `priority`   | string | No       | Filter by priority: `critical`, `high`, `medium`, `low`, `positive`. Omit for all. |
| `rep_user_id`| UUID   | No       | Filter nudges about a specific rep. Omit for all reps. |
| `limit`      | int    | No       | Page size. Default `50`, max `200`. |
| `offset`     | int    | No       | Pagination offset. Default `0`. |

**Response: `200 OK`**

```json
{
  "total": 12,
  "unread_count": 4,
  "limit": 50,
  "offset": 0,
  "nudges": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
      "rep_user_id": "3eed8382-6b30-44c9-82f6-6d70570e175e",
      "rep_name": "Ananya Sharma",
      "nudge_type": "metric_decline",
      "priority": "high",
      "title": "Ananya's SOP compliance dropped 15%",
      "message": "CSR Ananya's SOP compliance dropped by 15% compared to last cycle's baseline (0.72 → 0.61).",
      "metric_name": "compliance_score",
      "previous_value": 0.72,
      "current_value": 0.61,
      "change_pct": -15.3,
      "window_description": "last 24 hours vs cycle baseline",
      "source_session_id": "f7a1b2c3-...",
      "extra_data": null,
      "created_at": "2026-03-11T02:00:00Z",
      "expires_at": "2026-03-18T02:00:00Z",
      "read_status": "unread",
      "read_at": null
    }
  ]
}
```

**Field notes:**
- `metric_name`, `previous_value`, `current_value`, `change_pct`, `window_description` — only present for metric-based nudges (improvement/decline types). Null for `recurring_issue`, `cycle_summary`, etc.
- `source_session_id` — the coaching session that triggered this nudge. Use to deep-link into the coaching detail screen.
- `extra_data` — freeform JSON, may contain additional context depending on `nudge_type`. Treat as optional.
- Nudges are sorted by `created_at` descending (newest first).

---

### GET /coaching/nudges/unread-count

Lightweight endpoint for the notification bell badge. Poll this instead of the full list endpoint.

**URL:** `GET /api/v1/coaching/nudges/unread-count`

**Query Parameters:**

| Parameter    | Type | Required | Description |
|-------------|------|----------|-------------|
| `company_id` | UUID | Yes      | Company UUID |

**Response: `200 OK`**

```json
{
  "unread_count": 4
}
```

**Usage:** Show a badge on the notification bell icon when `unread_count > 0`. When the user taps the bell, call `GET /coaching/nudges` for full content.

---

### POST /coaching/nudges/:id/read

Mark a single nudge as read for the current user. Call this when the user opens/views a nudge.

**URL:** `POST /api/v1/coaching/nudges/{nudge_id}/read`

**Path Parameters:**

| Parameter  | Type | Description |
|-----------|------|-------------|
| `nudge_id` | UUID | The nudge to mark as read |

**Request Body:** None

**Response: `200 OK`**

```json
{
  "success": true,
  "nudge_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "read"
}
```

---

### POST /coaching/nudges/:id/dismiss

Dismiss a nudge for the current user. Dismissed nudges are hidden from the default list (they can still be retrieved with `?status=dismissed`).

**URL:** `POST /api/v1/coaching/nudges/{nudge_id}/dismiss`

**Path Parameters:**

| Parameter  | Type | Description |
|-----------|------|-------------|
| `nudge_id` | UUID | The nudge to dismiss |

**Request Body:** None

**Response: `200 OK`**

```json
{
  "success": true,
  "nudge_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "dismissed"
}
```

---

### POST /coaching/nudges/mark-all-read

Mark all unread nudges as read for the current user. Use this for a "Mark all as read" button.

**URL:** `POST /api/v1/coaching/nudges/mark-all-read`

**Query Parameters:**

| Parameter    | Type | Required | Description |
|-------------|------|----------|-------------|
| `company_id` | UUID | Yes      | Company UUID |

**Request Body:** None

**Response: `200 OK`**

```json
{
  "success": true,
  "marked_count": 4
}
```

---

## Data Reference

### NudgeType

| Value | When It's Created | Typical Priority |
|-------|------------------|-----------------|
| `metric_improvement` | A rep's metric improved ≥10% vs coaching baseline | `positive` |
| `metric_decline` | A rep's metric declined ≥10% vs coaching baseline | `high` |
| `critical_decline` | A rep's metric declined ≥20% | `critical` |
| `recurring_issue` | Same coaching issue appeared 3+ times in recent calls | `high` |
| `objection_weakness` | Rep overcomes <30% of a specific objection type | `high` |
| `objection_improvement` | Rep's objection overcome rate improved significantly | `positive` |
| `coaching_target_met` | Rep hit a target set in the coaching session | `positive` |
| `coaching_target_missed` | Rep is far from a coaching target | `high` |
| `new_strength` | A new positive behavior detected consistently | `positive` |
| `cycle_summary` | End-of-cycle summary when a 7-day cycle completes | `medium` |

### Priority

| Value | Color Suggestion | Meaning |
|-------|-----------------|---------|
| `critical` | Red | Needs immediate attention (≥20% metric decline) |
| `high` | Orange | Important change requiring manager action |
| `medium` | Yellow | Informational, review recommended |
| `low` | Gray | Minor observation |
| `positive` | Green | Good news (improvement, target met) |

### ReadStatus

| Value | Meaning |
|-------|---------|
| `unread` | User has not seen this nudge yet |
| `read` | User has opened/viewed this nudge |
| `dismissed` | User explicitly dismissed this nudge (hidden from default list) |

---

## TypeScript Types

```typescript
export type NudgeType =
  | 'metric_improvement'
  | 'metric_decline'
  | 'critical_decline'
  | 'recurring_issue'
  | 'objection_weakness'
  | 'objection_improvement'
  | 'coaching_target_met'
  | 'coaching_target_missed'
  | 'new_strength'
  | 'cycle_summary';

export type NudgePriority = 'critical' | 'high' | 'medium' | 'low' | 'positive';

export type NudgeReadStatus = 'unread' | 'read' | 'dismissed';

export interface SmartNudge {
  id: string;                          // UUID
  company_id: string;                  // UUID
  rep_user_id: string;                 // UUID
  rep_name: string | null;
  nudge_type: NudgeType;
  priority: NudgePriority;
  title: string;
  message: string;
  metric_name: string | null;
  previous_value: number | null;
  current_value: number | null;
  change_pct: number | null;           // e.g. -15.3 means 15.3% decline
  window_description: string | null;
  source_session_id: string | null;    // UUID — deep-link to coaching session
  extra_data: Record<string, unknown> | null;
  created_at: string;                  // ISO 8601
  expires_at: string | null;           // ISO 8601
  read_status: NudgeReadStatus;
  read_at: string | null;              // ISO 8601, null if unread
}

export interface SmartNudgeListResponse {
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
  nudges: SmartNudge[];
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface MarkReadResponse {
  success: boolean;
  nudge_id: string;
  status: 'read' | 'dismissed';
}

export interface MarkAllReadResponse {
  success: boolean;
  marked_count: number;
}
```

---

## Recommended UX Patterns

### Notification Bell Badge

Poll `GET /coaching/nudges/unread-count` every **30–60 seconds** in the background when the manager is logged in. Show a badge on the bell icon when `unread_count > 0`.

```typescript
// Poll every 30s
useEffect(() => {
  const interval = setInterval(async () => {
    const { unread_count } = await fetchUnreadCount(companyId);
    setUnreadCount(unread_count);
  }, 30_000);
  return () => clearInterval(interval);
}, [companyId]);
```

### Notification Panel

When the user opens the notification panel:
1. Call `GET /coaching/nudges` (no status filter — shows unread + read, excludes dismissed by default behavior).
2. Display nudges sorted newest-first (the API already does this).
3. Use `priority` to color-code cards (see priority table above).
4. Render `title` as the headline and `message` as the body.
5. If `metric_name` is present, show a mini stat: previous → current with `change_pct`.

### Marking as Read

Mark a nudge read **when it becomes visible** in the panel (on scroll into view or on tap), not just on explicit user action:

```typescript
const onNudgeVisible = async (nudgeId: string) => {
  if (nudge.read_status === 'unread') {
    await markNudgeRead(nudgeId);
    // Optimistically update local state
    setNudges(prev =>
      prev.map(n => n.id === nudgeId ? { ...n, read_status: 'read' } : n)
    );
    setUnreadCount(c => Math.max(0, c - 1));
  }
};
```

### Dismiss

Show a swipe-to-dismiss gesture or a "✕" button per nudge card. After dismissal the nudge disappears from the list locally. The backend hides it from the default response automatically.

### Mark All as Read

Show a "Mark all as read" button in the panel header. On tap:
1. Call `POST /coaching/nudges/mark-all-read?company_id=...`.
2. Update local list state to set all `read_status` to `"read"`.
3. Set badge count to `0`.

### Deep-Linking to Coaching Session

If `source_session_id` is non-null, render a "View Coaching Session" CTA that navigates to the coaching detail screen for that session UUID.

### Filtering

The notification panel can offer tabs:
- **All** — no status filter
- **Unread** — `?status=unread`
- **Dismissed** — `?status=dismissed`

And a filter chip for **Priority** if you want to let managers focus on `critical` or `positive` nudges.

### Pagination

Default page size is 50, which is enough for most cases. If `total > offset + limit`, fetch the next page on scroll.

```typescript
const loadMore = async () => {
  if (nudges.length < total) {
    const next = await fetchNudges({ offset: nudges.length, limit: 50 });
    setNudges(prev => [...prev, ...next.nudges]);
  }
};
```

---

## Error Handling

| HTTP Status | Meaning | Suggested Handling |
|------------|---------|-------------------|
| `401 Unauthorized` | JWT missing or expired | Redirect to login |
| `403 Forbidden` | User is not EXECUTIVE role | Hide nudge features entirely for non-executive roles |
| `404 Not Found` | Nudge UUID doesn't exist | Show toast: "Nudge not found" |
| `500 Internal Server Error` | Backend error | Show generic error state; retry after backoff |

All error responses follow the shape:
```json
{ "detail": "Error description string" }
```
