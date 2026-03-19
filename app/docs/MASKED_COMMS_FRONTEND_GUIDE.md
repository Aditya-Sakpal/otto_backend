# Masked Communications — Frontend Implementation Guide

Sales reps communicate with homeowners through Twilio proxy numbers. Neither party sees the other's real number. This document covers the API contracts and UI requirements for both **web app** and **mobile app**.

---

## Architecture Overview

```
Rep (mobile/web) → API → Twilio Proxy Number → Homeowner
Homeowner replies → Twilio webhook → API → Push notification → Rep
```

- Sessions auto-create when a lead reaches `APPOINTMENT_RAN` pipeline stage
- Sessions auto-close when lead moves to `WON` or `LOST`
- All communication is logged with direction, type, and homeowner reply tracking

---

## API Endpoints

**Base URL:** `/api/v1/masked-comms`
**Auth:** JWT Bearer token required on all endpoints (role: `SALES_REP` or `EXECUTIVE`)

### 1. Phone Registration (one-time setup)

Before a rep can use masked comms, they must register and verify their personal phone number.

#### `POST /phone/register`

Start OTP verification — sends a 6-digit SMS code to the rep's phone.

```json
// Request
{ "phone_number": "+16234695412" }

// Response 200
{ "status": "otp_sent", "expires_in_minutes": 10 }
```

#### `POST /phone/verify`

Complete OTP verification.

```json
// Request
{ "phone_number": "+16234695412", "code": "483921" }

// Response 200
{ "status": "verified", "phone_number": "+1***5412" }

// Response 400
{ "detail": "Invalid or expired verification code" }
```

#### `GET /phone/status`

Check if rep has a verified phone.

```json
// Response 200
{ "has_phone": true, "is_verified": true, "phone_number": "+1***5412" }
// or
{ "has_phone": false, "is_verified": false, "phone_number": null }
```

### 2. Push Token Registration (mobile only)

#### `POST /push-token`

Register or update Expo push notification token. Call this on app launch and whenever the token refreshes.

```json
// Request
{ "expo_push_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]" }

// Response 200
{ "status": "updated" }
```

### 3. Sessions

#### `GET /sessions`

List all active proxy sessions for the authenticated rep.

```json
// Response 200
{
  "sessions": [
    {
      "id": "uuid",
      "lead_id": "uuid",
      "proxy_number_id": "uuid",
      "homeowner_phone_masked": "+1***5412",
      "status": "active",
      "created_at": "2026-03-18T10:00:00Z"
    }
  ]
}
```

**UI notes:**
- Show homeowner name by resolving `lead_id` → lead detail → contact card name
- Sort by most recent activity (you can use `created_at` or track last message locally)
- Show unread badge if homeowner has replied since last view

### 4. Conversation Thread

#### `GET /sessions/{session_id}/conversation?skip=0&limit=50`

Get paginated conversation history (SMS + calls + recordings).

```json
// Response 200
{
  "session_id": "uuid",
  "messages": [
    {
      "id": "uuid",
      "comm_type": "sms",           // "sms" | "call" | "recording"
      "direction": "homeowner_to_rep", // "homeowner_to_rep" | "rep_to_homeowner"
      "message_body": "Hi, I'm interested in the quote",
      "call_status": null,
      "duration_seconds": null,
      "is_homeowner_reply": true,
      "source_metadata": null,       // null = human, { "agent": "follow_up" } = automated
      "audio_url": null,
      "created_at": "2026-03-18T10:05:00Z"
    },
    {
      "id": "uuid",
      "comm_type": "call",
      "direction": "rep_to_homeowner",
      "message_body": null,
      "call_status": "completed",    // "initiated" | "ringing" | "in-progress" | "completed" | "no-answer" | "busy" | "failed"
      "duration_seconds": 180,
      "is_homeowner_reply": false,
      "source_metadata": null,
      "audio_url": "https://s3.../recording.mp3",
      "created_at": "2026-03-18T10:10:00Z"
    },
    {
      "id": "uuid",
      "comm_type": "sms",
      "direction": "rep_to_homeowner",
      "message_body": "Thanks for your interest! I can come by tomorrow at 2pm.",
      "call_status": null,
      "duration_seconds": null,
      "is_homeowner_reply": false,
      "source_metadata": { "agent": "contextual_follow_up", "attempt": 1 },
      "audio_url": null,
      "created_at": "2026-03-18T09:00:00Z"
    }
  ]
}
```

**UI rendering rules:**

| `comm_type` | `direction` | Display |
|-------------|-------------|---------|
| `sms` | `homeowner_to_rep` | Left-aligned bubble (incoming) |
| `sms` | `rep_to_homeowner` | Right-aligned bubble (outgoing) |
| `call` | `rep_to_homeowner` | Call log card: "You called {name} — {duration}" |
| `call` | `homeowner_to_rep` | Call log card: "{name} called you — {duration}" |
| `recording` | any | Audio player with play/pause |

**Agent badge:** If `source_metadata` is not null and contains `"agent"`, show an automation badge (e.g., indigo flash icon) on the message bubble to distinguish AI-generated messages from human ones.

### 5. Send SMS

#### `POST /sessions/{session_id}/sms`

Send an SMS to the homeowner through the proxy number.

```json
// Request
{ "body": "Hi! Following up on our conversation about the roof estimate." }

// Response 200
{ "message_sid": "SM...", "status": "queued" }

// Response 404
{ "detail": "Session not found" }

// Response 503
{ "detail": "Twilio service unavailable" }
```

**Constraints:** `body` max length 1600 characters.

### 6. Initiate Call

#### `POST /sessions/{session_id}/call`

Start an outbound call. Twilio calls the rep first, then bridges to the homeowner.

```json
// Response 200
{ "call_sid": "CA...", "status": "initiated" }

// Response 404
{ "detail": "Session not found" }

// Response 503
{ "detail": "Twilio service unavailable" }
```

**Flow:**
1. Rep taps "Call" button
2. API responds with `call_sid`
3. Rep's phone rings (incoming from proxy number)
4. Rep picks up → homeowner's phone rings
5. Both connected through proxy — recording starts if company has `recording_disclosure_enabled`

---

## Push Notifications (Mobile)

Two notification types are sent when a homeowner initiates contact:

### `homeowner_reply` (SMS received)

```json
{
  "type": "homeowner_reply",
  "session_id": "uuid",
  "title": "Sarah replied",       // Resolved from lead → contact_card name, fallback: "Homeowner"
  "body": "Hi, I'm interested..."  // Message preview
}
```

### `homeowner_call` (Inbound call)

```json
{
  "type": "homeowner_call",
  "session_id": "uuid",
  "title": "Mike is calling",
  "body": "Incoming call via Otto"
}
```

**Deep linking:** On notification tap, navigate to `/masked-comms/{session_id}` (the conversation screen).

---

## Web App Implementation

### Pages

#### 1. Sessions List (`/masked-comms/sessions`)

- Fetch `GET /sessions` on mount
- For each session, resolve homeowner name from the lead/contact card (you likely already have this from the pipeline)
- Show last message preview + timestamp
- Highlight sessions with unread homeowner replies
- Link each card to the conversation view

#### 2. Conversation Thread (`/masked-comms/sessions/{sessionId}`)

- Fetch `GET /sessions/{sessionId}/conversation` with pagination
- Render messages as chat bubbles (SMS) or log entries (calls/recordings)
- Text input at bottom with send button → `POST /sessions/{sessionId}/sms`
- Call button → `POST /sessions/{sessionId}/call`
- Auto-scroll to bottom on new messages
- Poll for new messages every 5-10 seconds (or use WebSocket if available)

#### 3. Phone Registration (`/masked-comms/register-phone`)

- Check `GET /phone/status` on mount
- If not registered: show phone input → `POST /phone/register` → show OTP input → `POST /phone/verify`
- If verified: show green checkmark with masked number
- Gate access to sessions list behind verified phone status

### Navigation Entry Point

Add a "Messages" card/tab to the sales rep dashboard that links to `/masked-comms/sessions`. Show a badge count for sessions with unread homeowner replies.

---

## Mobile App Implementation (React Native / Expo)

### Screens

#### 1. Sessions List (`/masked-comms/sessions`)

```tsx
// Fetch sessions
const { data } = await api.get('/api/v1/masked-comms/sessions');

// Render FlatList of SessionCard components
// Each card shows: homeowner name, last message, timestamp, unread indicator
// onPress → navigate to conversation screen
```

#### 2. Conversation Thread (`/masked-comms/[sessionId]`)

```tsx
// Fetch conversation
const { data } = await api.get(`/api/v1/masked-comms/sessions/${sessionId}/conversation`);

// Render FlatList (inverted) of:
//   - MessageBubble for SMS (left/right based on direction)
//   - CallLogEntry for calls (centered card with duration + status)
//   - Audio player for recordings

// Bottom ActionBar:
//   - TextInput + Send button → POST /sessions/{sessionId}/sms
//   - Phone icon button → POST /sessions/{sessionId}/call
```

#### 3. Phone Registration (`/masked-comms/register-phone`)

```tsx
// Step 1: Phone number input → POST /phone/register
// Step 2: 6-digit OTP input → POST /phone/verify
// Step 3: Success screen → navigate to sessions
```

### Push Notification Handling

In your app layout/root component, add notification tap handlers:

```tsx
// In notification response handler (e.g., useLastNotificationResponse)
const data = notification.request.content.data;

switch (data.type) {
  case 'homeowner_reply':
  case 'homeowner_call':
    router.push(`/masked-comms/${data.session_id}`);
    break;
}
```

Register push token on app launch:

```tsx
// After getting Expo push token
await api.post('/api/v1/masked-comms/push-token', {
  expo_push_token: token,
});
```

### Component Guide

| Component | Purpose |
|-----------|---------|
| `SessionCard` | Session list item — homeowner name, last message preview, timestamp |
| `MessageBubble` | SMS message — left (incoming) or right (outgoing), agent badge if `source_metadata` |
| `CallLogEntry` | Call log — centered card with phone icon, status, duration, audio player |
| `ActionBar` | Bottom bar — text input + send + call button |

---

## Error Handling

| Status | Meaning | UI Action |
|--------|---------|-----------|
| 400 | Invalid input (bad OTP, etc.) | Show inline error |
| 401 | Token expired | Redirect to login |
| 403 | Wrong role | Show "access denied" |
| 404 | Session not found | Show "session ended" and navigate back |
| 503 | Twilio unavailable | Show "service temporarily unavailable, try again" |
| 500 | Server error | Show generic error toast |

---

## State Management Tips

- Cache sessions list locally, refresh on focus/pull-to-refresh
- Optimistically add sent messages to the conversation before API confirms
- Track "last seen message" per session to compute unread counts
- On `homeowner_reply` push notification, invalidate the sessions list cache and bump the unread count

---

## API Endpoint Summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/sessions` | List active sessions |
| GET | `/sessions/{id}/conversation?skip=0&limit=50` | Get conversation thread |
| POST | `/sessions/{id}/sms` | Send SMS via proxy |
| POST | `/sessions/{id}/call` | Initiate call via proxy |
| POST | `/phone/register` | Start OTP phone registration |
| POST | `/phone/verify` | Complete OTP verification |
| GET | `/phone/status` | Check phone registration status |
| POST | `/push-token` | Register/update Expo push token |
