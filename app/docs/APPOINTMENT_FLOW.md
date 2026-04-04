# Appointment Processing Architecture

End-to-end flow from appointment recording to follow-up creation.

## Flow Overview

```
Appointment Created (from CSR call booking or CRM sync)
    → Sales Rep visits appointment
    → Audio recorded on sales rep's phone
    → Mobile app uploads to S3 via /recordings/initiate + /recordings/complete
    → Shoonya analysis triggered with appointment_id
    → Shoonya processes audio (transcription + AI analysis)
    → Job-complete webhook writes analysis to appointment
    → If follow_up_required: PendingAction created for sales rep
    → Follow-up surfaces in sales rep's tasks/pending leads
```

---

## Step 1: Appointment Creation

Appointments are created through three paths:

### Path A: CSR Call Analysis (booking detected)
- CSR takes an inbound call via CTM/GHL
- Shoonya analyzes the call, returns `booking_status: "booked"`
- `CallService._update_dependent_entities()` creates the appointment
- **File**: `app/services/call_service.py:1253` → `_upsert_appointment_from_call()`
- Lead pipeline moves to `BOOKED`

### Path B: GHL/ServiceTitan CRM Sync
- GHL opportunity or ServiceTitan booking synced via webhook
- Creates appointment with scheduled date, contact, and lead linkage
- **Files**: `app/services/ghl_service.py`, `app/services/servicetitan_service.py`

### Path C: Manual Creation
- Executive or CSR creates appointment via API
- **Endpoint**: `POST /api/v1/appointments`
- **File**: `app/services/appointment_service.py`

---

## Step 2: Sales Rep Records the Appointment

The sales rep visits the appointment and records the conversation on their phone. The mobile app uses a two-step upload:

### Step 2a: Initiate Upload
- **Endpoint**: `POST /api/v1/recordings/initiate`
- **File**: `app/routes/v1/recordings.py:51`
- **Input**: `{appointment_id}`
- **Returns**: Pre-signed S3 URL + S3 key
- S3 key format: `recordings/appointment_{id}.wav`
- Mobile app uploads the audio file directly to S3 using the pre-signed URL

### Step 2b: Complete Upload
- **Endpoint**: `POST /api/v1/recordings/complete`
- **File**: `app/routes/v1/recordings.py:132`
- **Input**: `{appointment_id, s3_key}`
- **What happens**:
  1. Sets `appointment.audio_url` from S3 key
  2. Sets `appointment.recording_status = "uploaded"`
  3. Moves lead pipeline to `APPOINTMENT_RAN` (if currently `BOOKED` or `APPOINTMENT`)
  4. Triggers Shoonya processing:
     - Calls `shoonya.process_call()` with `appointment.id` as the `call_id` tracker
     - Sets metadata: `is_appointment=true`, `interaction_type="meeting"`, `call_type="sales_call"`, `role="sales_rep"`
     - Webhook callback: `{API_URL}/api/v1/webhooks/shoonya/job-complete`
  5. Stores `shunya_job_id` on appointment, sets `analysis_status = "processing"`

### Alternative: Audio from CRM
For GHL and ServiceTitan, audio may arrive via webhook instead of mobile upload:
- **GHL**: `app/services/ghl_service.py` — fetches recording from GHL API, uploads to S3, sends to Shoonya via `trigger_analysis_direct()`
- **ServiceTitan**: `app/services/servicetitan_service.py` — streams recording from ST to S3, triggers analysis via `trigger_analysis()`

---

## Step 3: Shoonya Processes Audio

Shoonya receives the audio and processes it asynchronously:
- Transcription
- Call summary, key points, action items, next steps
- SOP compliance scoring
- Objection detection and classification
- Lead qualification (BANT scores, qualification_status, booking_status)
- Follow-up detection (`follow_up_required`, `follow_up_reason`)

**Shoonya API**: `POST {SHOONYA_URL}/api/v1/call-processing/process`

**Returns**: `{"job_id": "...", "status": "submitted"}`

---

## Step 4: Shoonya Callback (Job Complete)

When processing finishes, Shoonya calls `POST /api/v1/webhooks/shoonya/job-complete`.

**Handler**: `app/routes/v1/webhooks.py:90`

### Processing:
1. Validates `status == "completed"`, extracts `call_id`
2. Checks if `call_id` matches an appointment (appointment flow) or a call (call flow)
3. Fetches full analysis from Shoonya Summary API: `GET /api/v1/call-processing/summary/{call_id}`

### Shoonya Response Structure
```json
{
  "summary": {
    "summary": "Customer discussed roof leak...",
    "key_points": ["Active leak reported", "Quoted $25k"],
    "action_items": ["Send financing options"],
    "next_steps": ["Customer getting 3 estimates"],
    "pending_actions": [{"type": "follow_up", "action_item": "..."}],
    "sentiment_score": 0.82
  },
  "compliance": {
    "sop_compliance": {
      "score": 0.72,
      "stages": {"total": 7, "followed": [...], "missed": [...]},
      "issues": [...],
      "positive_behaviors": [...]
    }
  },
  "objections": {
    "objections": [{"category_text": "Service Fee Concerns", "text": "..."}],
    "total_count": 3
  },
  "qualification": {
    "qualification_status": "warm",
    "booking_status": "not_booked",
    "overall_score": 0.65,
    "follow_up_required": true,
    "follow_up_reason": "Customer wants three estimates before deciding",
    "bant_scores": {"need": 0.8, "budget": 0.2, "authority": 1.0, "timeline": 0.3},
    "detected_call_type": "fresh_sales",
    "customer_name": "John Smith",
    "service_requested": "Roof replacement"
  }
}
```

---

## Step 5: Analysis Written to Appointment

**Code**: `app/routes/v1/webhooks.py:323-440`

The webhook handler writes analysis fields directly to the `AppointmentORM` record:

| Appointment Field | Source |
|---|---|
| `summary` | `summary.summary` |
| `key_points` | `summary.key_points` |
| `action_items` | `summary.action_items` |
| `next_steps` | `summary.next_steps` |
| `pending_actions_data` | `summary.pending_actions` |
| `sentiment_score` | `summary.sentiment_score` |
| `objections` | `objections[].category_text` |
| `objection_texts` | `objections[].text` |
| `objections_total_count` | `objections.total_count` |
| `sop_compliance_score` | `compliance.sop_compliance.score` |
| `sop_stages_completed` | `compliance.stages.followed` |
| `sop_stages_missed` | `compliance.stages.missed` |
| `qualification_status` | `qualification.qualification_status` |
| `booking_status` | `qualification.booking_status` |
| `transcript` | Top-level `transcript` |
| `analysis_status` | Set to `"completed"` |

---

## Step 6: Follow-up Creation

**Code**: `app/routes/v1/webhooks.py:399-426`

If `qualification.follow_up_required == true`, a `PendingActionORM` record is created:

```
action_type:    "follow_up"
status:         "pending"
owner_id:       appointment.assigned_rep_id (the sales rep)
lead_id:        appointment.lead_id
call_id:        appointment.interaction_id
raw_text:       follow_up_reason from Shoonya
source:         "ai_analysis"
extra_metadata: {
    "appointment_id": "...",
    "follow_up_reason": "..."
}
```

This makes the follow-up visible in:
- Sales rep's pending tasks (`GET /api/v1/tasks`)
- Sales rep's pending leads (`GET /api/v1/sales_rep/pending-leads`)
- Follow-up details (`GET /api/v1/sales_rep/follow_up?appointment_id=...`)

---

## Pipeline Stage Progression

```
QUALIFIED → BOOKED → APPOINTMENT → APPOINTMENT_RAN → WON / LOST
```

| Stage | Trigger |
|---|---|
| `qualified` | CSR call analysis: qualification_status = hot/warm/cold, not booked |
| `booked` | CSR call analysis: booking_status = "booked", appointment created |
| `appointment` | Appointment scheduled (date approaching) |
| `appointment_ran` | Recording uploaded via `/recordings/complete` (line 185) |
| `won` | Appointment outcome set to "won" (manual or via deal close) |
| `lost` | Appointment outcome set to "lost" |

---

## Lead Status Mapping (from Shoonya analysis)

| qualification_status | booking_status | LeadStatus | PipelineStage |
|---|---|---|---|
| hot/warm/cold | booked | QUALIFIED_BOOKED | BOOKED |
| hot/warm/cold | not_booked | QUALIFIED_UNBOOKED | QUALIFIED |
| hot/warm/cold | service_not_offered | QUALIFIED_SERVICE_NOT_OFFERED | SERVICE_NOT_OFFERED |
| unqualified | any | NEW | — |

---

## Data Model

```
Company
  └── Users (CSR, Sales Rep, Executive)
  └── Contact Cards (phone, name, address)
       └── Leads (status, pipeline_stage, assigned_rep_id)
            ├── Calls (audio_url, transcript, handled_by_user_id)
            │    └── Call Analysis (qualification, objections, SOP)
            ├── Appointments (scheduled_start, outcome, assigned_rep_id)
            │    └── Analysis fields stored directly on appointment row
            │    └── Linked to call via interaction_id
            └── Pending Actions (action_type="follow_up", owner_id=rep)
```

---

## Key Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /recordings/initiate` | Get pre-signed S3 URL for audio upload |
| `POST /recordings/complete` | Confirm upload, trigger Shoonya analysis |
| `POST /webhooks/shoonya/job-complete` | Receive analysis results from Shoonya |
| `GET /sales_rep/follow_up?appointment_id=` | Get follow-up details for an appointment |
| `GET /sales_rep/pending-leads` | Get leads needing follow-up for a rep |
| `GET /appointments/{id}` | Get appointment with analysis |
| `GET /appointments/{id}/context` | Get full appointment context with phases |

---

## Key Files

| Component | File |
|---|---|
| Recording upload (mobile) | `app/routes/v1/recordings.py` |
| Shoonya webhook handler | `app/routes/v1/webhooks.py` |
| Call service (analysis, triggers) | `app/services/call_service.py` |
| GHL call processing | `app/services/ghl_service.py` |
| ServiceTitan call processing | `app/services/servicetitan_service.py` |
| Appointment service | `app/services/appointment_service.py` |
| Shoonya integration | `app/infrastructure/integrations/shoonya.py` |
| Lead service (pending leads) | `app/services/lead_service.py` |
| Sales rep service (follow-ups) | `app/services/sales_rep_service.py` |
| Enums (pipeline stages, statuses) | `app/domain/enums.py` |
| Appointment ORM | `app/infrastructure/database/models/appointment.py` |
| Pending Action ORM | `app/infrastructure/database/models/pending_action.py` |
