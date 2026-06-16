# Appointment Call Phases API

## Overview

Live conversation phase detection from Shunya is available on **single-appointment endpoints only** (not list endpoints, to avoid performance overhead).

## Endpoints returning `phases`

| Endpoint | Has `phases` |
|---|---|
| `GET /api/v1/appointments/{id}` | Yes |
| `GET /api/v1/appointments/{id}/context` | Yes |
| `GET /api/v1/appointments` | No |
| `GET /api/v1/appointments/today` | No |
| `GET /api/v1/appointments/upcoming` | No |
| `GET /api/v1/appointments/past` | No |

## `phases` field

**Type:** `object | null`

Returns `null` when no phase data is available (no associated call, Shunya unavailable, or call not yet processed).

**Example response (within `AppointmentResponse` or `AppointmentContextResponse`):**

```json
{
  "id": "...",
  "scheduled_start": "...",
  "phases": {
    "greeting": {
      "detected": true,
      "start_time": 0.0,
      "end_time": 12.5,
      "confidence": 0.92
    },
    "problem_discovery": {
      "detected": true,
      "start_time": 12.5,
      "end_time": 45.0,
      "confidence": 0.87
    },
    "qualification": {
      "detected": true,
      "start_time": 45.0,
      "end_time": 120.0,
      "confidence": 0.85
    },
    "objection_handling": {
      "detected": false,
      "start_time": null,
      "end_time": null,
      "confidence": 0.0
    },
    "closing": {
      "detected": true,
      "start_time": 120.0,
      "end_time": 150.0,
      "confidence": 0.78
    },
    "post_close": {
      "detected": false,
      "start_time": null,
      "end_time": null,
      "confidence": 0.0
    }
  }
}
```

## 6 Conversation Phases

| Phase | Description |
|---|---|
| `greeting` | Opening — introductions, rapport building |
| `problem_discovery` | Identifying customer needs, asking about the issue/service |
| `qualification` | BANT — budget, authority, need, timeline |
| `objection_handling` | Addressing customer concerns or pushback |
| `closing` | Booking the appointment, confirming details |
| `post_close` | Wrap-up after commitment — next steps, thank you |

## Phase object fields

| Field | Type | Description |
|---|---|---|
| `detected` | `boolean` | Whether this phase was identified in the call |
| `start_time` | `float \| null` | Start time in seconds from call start |
| `end_time` | `float \| null` | End time in seconds |
| `confidence` | `float` | Confidence score (0.0–1.0) |

## Notes

- Phases are fetched **live from Shunya** per request (not cached in DB)
- Only available for appointments linked to a processed call recording
- If Shunya is down or slow, `phases` returns `null` gracefully
