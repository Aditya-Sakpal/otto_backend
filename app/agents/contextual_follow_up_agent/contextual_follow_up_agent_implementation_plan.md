# Contextual Follow-Up Agent Implementation Plan

## Objective

Implement the contextual follow-up agent so that:

1. Customer replies (after our outbound follow-up) are persisted in DB.
2. Those customer replies are visible in frontend follow-up timeline.
3. A frontend ON/OFF toggle controls manual approval before automated send.
4. When toggle is ON, all generated outbound messages require edit/approval before sending.

---

## Current Codebase Baseline (Already Present)

- Agent pipeline and outbound generation in:
  - `backend/app/agents/contextual_follow_up_agent/orchestrator.py`
- Outbound persistence table/model:
  - `follow_up_otto`
  - ORM: `backend/app/infrastructure/database/models/follow_up_otto.py`
- Status lifecycle already includes `proposed` (review queue concept).
- Follow-up aggregation for lead detail already exists in:
  - `backend/app/infrastructure/repositories/lead.py`
  - domain schema in `backend/app/domain/models/lead_detail.py`

This implementation extends the existing architecture instead of replacing it.

---

## Phase 1 — Data Layer (DB + ORM)

### 1.1 Add inbound customer reply table

Create migration: `backend/app/infrastructure/database/migrations/create_follow_up_customer_messages.sql`

Suggested schema:

- `id UUID PK`
- `company_id UUID NOT NULL`
- `lead_id UUID NOT NULL`
- `follow_up_otto_id UUID NULL` (link to outbound row when identifiable)
- `channel VARCHAR(32) NOT NULL` (`sms`, `whatsapp`, `email`)
- `direction VARCHAR(16) NOT NULL DEFAULT 'inbound'`
- `message_content TEXT NOT NULL`
- `provider_message_id VARCHAR(255) NULL`
- `provider_timestamp TIMESTAMPTZ NULL`
- `raw_payload JSONB NULL`
- `created_at TIMESTAMPTZ DEFAULT now()`

Indexes:

- `(company_id, lead_id, created_at DESC)`
- `provider_message_id` unique (or provider-scoped unique key)

### 1.2 Add manual-review setting (company scoped)

Option A (preferred): add to existing company settings table if available.  
Option B: create small dedicated table, e.g. `follow_up_agent_settings`:

- `company_id UUID PK`
- `manual_review_enabled BOOLEAN NOT NULL DEFAULT FALSE`
- `updated_at TIMESTAMPTZ`
- `updated_by UUID NULL`

### 1.3 ORM additions

- Add ORM model for inbound table:
  - `backend/app/infrastructure/database/models/follow_up_customer_message.py`
- Export in:
  - `backend/app/infrastructure/database/models/__init__.py`

---

## Phase 2 — Backend Write Path

### 2.1 Manual approval gate in orchestrator

File: `backend/app/agents/contextual_follow_up_agent/orchestrator.py`

Update `_process_sms(...)` logic:

- Read `manual_review_enabled` for `ctx.lead.company_id`.
- If ON:
  - Keep row in `follow_up_otto` as `status='proposed'`.
  - Do not execute Twilio send.
  - Return log row ID.
- If OFF:
  - Existing auto-send behavior remains unchanged (`sent`/`failed` updates).

### 2.2 Inbound customer reply ingestion

Add endpoint in:

- `backend/app/routes/v1/webhooks.py` (or new `follow_up.py` route)

Endpoint example:

- `POST /api/v1/followup/inbound/webhook`

Responsibilities:

- Verify webhook signature.
- Parse provider payload.
- Identify lead/company by phone/message metadata.
- Insert inbound row into `follow_up_customer_messages`.
- Optionally set follow-up state to paused when customer replied.
- Return idempotent success response.

### 2.3 Service layer extraction (recommended)

Create services:

- `backend/app/services/follow_up_settings_service.py`
- `backend/app/services/follow_up_message_ingestion_service.py`
- `backend/app/services/follow_up_send_service.py`

This keeps route + orchestrator thin and testable.

---

## Phase 3 — Read APIs for Frontend

### 3.1 Follow-up timeline API

Add endpoint:

- `GET /api/v1/followup/leads/{lead_id}/thread`

Returns chronological merged timeline:

- Outbound AI messages from `follow_up_otto`
- Inbound customer replies from `follow_up_customer_messages`

Response item contract:

- `id`
- `message_type` (`outbound_ai`, `inbound_customer`, `rep_nudge`)
- `channel`
- `content`
- `status`
- `created_at`
- `sent_at`
- `source`

### 3.2 Settings API (manual review toggle)

- `GET /api/v1/followup/settings?company_id=...`
- `PATCH /api/v1/followup/settings`
  - body: `{ "manual_review_enabled": true|false }`

### 3.3 Approval/edit APIs

- `PATCH /api/v1/followup/messages/{id}`
  - edit message content when status is `proposed`.
- `POST /api/v1/followup/messages/{id}/approve-send`
  - send edited message and update to `sent`/`failed`.
- `POST /api/v1/followup/messages/{id}/reject` (optional)

---

## Phase 4 — Repository and Schema Integration

### 4.1 Domain models

Update:

- `backend/app/domain/models/lead_detail.py`

Add timeline message schema support for inbound customer messages.

### 4.2 Repository merge logic

Update:

- `backend/app/infrastructure/repositories/lead.py`

Extend follow-up builder to merge 3 sources:

1. `follow_up_otto` (AI outbound)
2. `pending_actions` (rep tasks)
3. `follow_up_customer_messages` (customer inbound)

Sort by event timestamp and return unified payload for frontend.

---

## Phase 5 — Frontend Implementation Requirements

### 5.1 Manual toggle

- Add company-level switch:
  - **Manual review before sending automated follow-ups**
- Persist via settings API.

### 5.2 Timeline UX

- Show inbound and outbound in one thread.
- Status badges:
  - `Proposed`
  - `Sent`
  - `Failed`
  - `Received`
  - `Paused`

### 5.3 Manual review queue

When toggle ON:

- Show proposed outbound messages.
- Actions: `Edit`, `Approve & Send`, `Reject`.

---

## Phase 6 — Security, Reliability, Observability

### Security

- Enforce webhook signature validation.
- RBAC on approval/edit/settings endpoints.

### Reliability

- Idempotency by `provider_message_id`.
- Retry policy for outbound send failures.

### Auditability

Track:

- `edited_by`, `edited_at`
- `approved_by`, `approved_at`
- message history (optional snapshot table)

### Metrics

- outbound sent count
- approval latency
- customer reply rate
- send failure rate
- duplicate webhook suppression count

---

## Testing Plan

### Unit tests

- Manual toggle ON => no Twilio send call from orchestrator.
- Manual toggle OFF => existing send behavior unchanged.
- Webhook ingestion writes inbound row correctly.
- Duplicate provider message ignored (idempotency).

### Integration tests

- Generate outbound -> inbound webhook -> timeline API returns both.
- Edit + approve workflow updates status and sends.

### Regression tests

- Existing follow-up tab behavior for current rows remains functional.
- Existing pending action logic remains intact.

---

## Rollout Strategy

1. Deploy migration with read/write disabled by feature flag.
2. Deploy webhook ingestion path.
3. Deploy timeline API merge.
4. Deploy frontend timeline + toggle.
5. Enable for one pilot company.
6. Monitor metrics and logs.
7. Gradually roll out to all companies.

---

## File-by-File Execution Checklist

### Migrations

- `backend/app/infrastructure/database/migrations/create_follow_up_customer_messages.sql`
- `backend/app/infrastructure/database/migrations/add_follow_up_manual_review_setting.sql`

### Models

- `backend/app/infrastructure/database/models/follow_up_customer_message.py` (new)
- `backend/app/infrastructure/database/models/follow_up_otto.py` (optional audit columns)
- `backend/app/infrastructure/database/models/__init__.py` (register new model)

### Agent

- `backend/app/agents/contextual_follow_up_agent/orchestrator.py` (manual gate logic)

### Routes

- `backend/app/routes/v1/webhooks.py` (inbound follow-up webhook)
- `backend/app/routes/v1/follow_up.py` (new: settings + thread + approval APIs)
- `backend/app/routes/v1/__init__.py` (include follow-up router)

### Services/Repositories

- `backend/app/services/follow_up_settings_service.py` (new)
- `backend/app/services/follow_up_message_ingestion_service.py` (new)
- `backend/app/services/follow_up_send_service.py` (new)
- `backend/app/infrastructure/repositories/lead.py` (merge inbound messages in timeline)

### Domain Schemas

- `backend/app/domain/models/lead_detail.py` (inbound message schema + merged thread contract)

---

## Definition of Done

- Customer replies after follow-up are stored in DB.
- Customer replies are visible in frontend timeline.
- Manual review toggle exists and works company-wide.
- With toggle ON, generated messages require edit/approval before send.
- Approval workflow sends and updates status correctly.
- Webhook ingestion is secure + idempotent.
- No regression in current follow-up behavior for toggle OFF companies.

---

## 5 Differentiator Features To Make This Agent Stronger

1. **Intent-to-Action Engine**
   - Classify each inbound customer reply into intent buckets (`interested`, `price objection`, `timing issue`, `not interested`, `call me`) and auto-suggest the best next action (reply draft, rep call task, pause, nurture sequence).

2. **Best-Time + Channel Optimization**
   - Learn per-lead engagement pattern and pick the most likely winning send time and channel (SMS vs WhatsApp vs email), with fallback rules when no reply is received.

3. **Confidence-Based Safety Routing**
   - Even when manual mode is OFF globally, force manual approval for low-confidence, high-risk, or compliance-sensitive messages (dynamic human-in-the-loop).

4. **Outcome Feedback Loop**
   - Track what got replies/bookings and continuously tune prompts/rules by company, market, and lead segment so performance keeps improving over time.

5. **Client-Facing ROI Dashboard**
   - Expose metrics clients care about: reply-rate lift, booking conversion lift, average response time, recovered opportunities, and revenue influenced by the follow-up agent.

