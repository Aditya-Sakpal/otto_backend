# AUTO — Retell AI Voice Agent Specification

**AUTO AI Voice Receptionist** — inbound + outbound roofing reception / lead-intake voice agent, mapped onto the AUTO FastAPI backend and modeled on the reference Retell `conversation-flow` export.

> Objective: **talk to a customer and generate a lead in the system.** Everything else (property capture, appointment booking, follow-up, action items) hangs off that core flow.

---

## 1. Reference architecture (what we mirrored)

The reference JSON (`New Claude Agent (CRM)`) is a Retell **conversation-flow** agent with this shape:

| Reference concept | What it does | AUTO equivalent |
|---|---|---|
| `agent_*` metadata (voice_id, stt, denoising, ambient) | Telephony + voice config | reused as-is, re-themed for AUTO |
| `global_prompt` | Persona + tone + tool-usage rules + CRM rules | rewritten for roofing sales/qualification |
| `conversationFlow.nodes[]` | The graph: `conversation`, `function`, `extract_dynamic_variables`, `end` | rebuilt for the AUTO lead flow |
| `start_node_id` → silent CRM lookup first | "Recognize caller" before greeting | `search_lead` runs silently at start |
| `extract_dynamic_variables` nodes | Pull structured values out of speech | name, address, roof, urgency, etc. |
| `tools[]` (`custom` HTTP, `check_availability_cal`, `book_appointment_cal`) | Backend calls | mapped to AUTO endpoints |
| `response_variables` on tools | Bind tool JSON → `{{vars}}` | same mechanism, AUTO field names |
| Post-call analysis (`post_call_analysis_model`, `pii_config`) | After-call processing | AUTO already does this via Shoonya |

The reference pattern we deliberately copied:
- **Silent recognize-caller `function` node as `start_node_id`** (`speak_during_execution: false`, `wait_for_result: true`) → then greet.
- **`function` node per backend call**, each with a warm "stall" instruction and an `else_edge` to an error/fallback node.
- **`extract_dynamic_variables` nodes with `finetune_transition_examples`** to make extraction reliable.
- **A central "Anything Else" hub** that every branch returns to, then `end`.
- **Fire-and-forget writes** (`wait_for_result: false`) for non-blocking CRM side-effects (lead create, call note).

---

## 2. AUTO backend analysis (as-is)

AUTO is a **post-call intelligence CRM**, not a live IVR. Today, leads are **not** created synchronously by an API — they materialize from:

- **Telephony/CRM webhooks** — `POST /api/v1/webhooks/{ghl/messages, ctm/calls, servicetitan/calls, telephony/call-complete}` → `CallService.ingest_call` / `GHLService` / `CTMService`.
- **Shoonya analysis webhook** — `POST /api/v1/webhooks/shoonya/job-complete` → `CallService.process_analysis` extracts contact, property, objections, action items, qualification, booking status.

Relevant building blocks already present:

| Layer | Module | Relevance to Retell |
|---|---|---|
| Routes | `app/routes/v1/leads.py` | list/get/pipeline/`move-stage`/`assign`/`status` — **read + stage moves, no create** |
| Routes | `app/routes/v1/appointments.py` | full CRUD: `POST /appointments`, `/reschedule`, `/today`, `/upcoming` |
| Routes | `app/routes/v1/follow_up.py` | `otto-proposals/{id}/approve-send` (SMS to lead / rep nudge) |
| Routes | `app/routes/v1/masked_comms.py` | `sessions/{id}/sms`, `sessions/{id}/call` (proxy SMS/voice) |
| Routes | `app/routes/v1/recordings.py` | `/initiate`, `/complete`, `/{appointment_id}/analysis` |
| Routes | `app/routes/v1/contact_card.py` | `GET /contact-card/{id}`, `/contact-card/calls/{call_id}` |
| Routes | `app/routes/v1/sales_rep.py` | `/work-queue`, `/pending-leads`, `/missed-calls`, `/tasks` |
| Services | `lead_service`, `call_service`, `appointment_service`, `pending_action_service`, `followup_notification_service`, `masked_comms_service`, `property_text_extractor`, `lead_phone_resolver` | backing logic the new tool endpoints call |
| Models | `Lead`, `ContactCard`, `Appointment`, `PendingAction` | target rows |
| Util | `property_text_extractor.extract_property_from_text(*parts)` | turns free text → `{roof_type, square_footage, ...}` |

**Implication:** to drive AUTO from Retell we add a **thin, public, tool-facing router** (`/api/v1/voice-agent/*`) that wraps existing services and fills the create/search gaps. The Retell JSON below targets that contract. Missing pieces are listed in §7.

---

## 3. Architecture diagram

```
                          ┌─────────────────────────────────────────┐
   PSTN / SIP  ─────────▶ │            RETELL  (voice layer)          │
   inbound & outbound     │  STT(Azure) · LLM(flow) · TTS · turn-take │
                          └───────────────────┬───────────────────────┘
                                              │  conversation-flow graph
                                              │  (nodes + dynamic vars)
                                              ▼
                          ┌─────────────────────────────────────────┐
                          │      Retell custom tools (HTTPS)          │
                          │  POST/GET https://<auto-host>/api/v1/     │
                          │            voice-agent/*                  │
                          └───────────────────┬───────────────────────┘
                                              │  X-Voice-Agent-Secret
                                              ▼
   ┌──────────────────────────── AUTO FastAPI backend ───────────────────────────┐
   │  NEW  voice_agent router  ──▶  existing service layer                         │
   │  ─────────────────────────    ───────────────────────────────────────────   │
   │  search_lead            ──▶  lead_phone_resolver / lead_service              │
   │  create_lead            ──▶  contact repo + lead_service (+ pipeline_stage)  │
   │  update_lead            ──▶  lead_service.update_status / move_stage         │
   │  save_property_details  ──▶  property_text_extractor + contact.property_snap │
   │  get_available_slots    ──▶  appointment_service (rep availability)          │
   │  create_appointment     ──▶  appointment_service.create_from_schema         │
   │  generate_followup      ──▶  contextual_follow_up_agent / follow_up rows     │
   │  create_pending_action  ──▶  pending_action_service                          │
   │  send_sms / send_email  ──▶  masked_comms_service / email_controller         │
   │  get_customer_history   ──▶  lead_service.get_customer_card / calls          │
   │  save_call_summary      ──▶  call_service.ingest_call + analysis             │
   │  save_recording_analysis──▶  recordings / recording_reconciliation          │
   │  surface_next_actions   ──▶  work_queue_service / pending_action_service     │
   └──────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
              Postgres (leads, contact_cards, appointments,
              pending_actions, calls, analysis, follow_up_otto)
                                   │
                                   ▼   (async, after call)
              Shoonya analysis  +  contextual follow-up agent  +  notifications
```

---

## 4. Dynamic variables

| Variable | Source node | Type | Notes |
|---|---|---|---|
| `customer_name` | Greeting / extract | string | reused everywhere; from `search_lead` if returning caller |
| `phone_number` | call metadata (`{{from_number}}`) | string | resolved automatically by backend; never asked |
| `property_address` | Property Collection extract | string | full street address |
| `house_type` | Property Collection extract | string | single-story / two-story / multi-unit |
| `square_footage` | Property Collection extract | string | numeric string e.g. "2136" |
| `roof_type` | Property Collection extract | string | tile / shingle / flat / metal |
| `roof_age` | Property Collection extract | string | years, e.g. "25" |
| `problem_description` | Problem ID extract | string | one-sentence issue |
| `insurance_status` | Qualification extract | string | insurance / out-of-pocket / unsure |
| `urgency` | Qualification extract | string | emergency / soon / researching |
| `appointment_date` | Scheduling extract | string | YYYY-MM-DD |
| `appointment_time` | Scheduling extract | string | clock time, e.g. "10 AM" |
| `lead_status` | derived | string | qualified / unqualified / service_not_offered |
| `follow_up_required` | derived | string | "true" / "false" |
| `next_action` | derived | string | short human label for the action item |

Backend-bound (from tool `response_variables`): `crm_found`, `crm_lead_id`, `crm_contact_id`, `crm_customer_name`, `crm_history_text`, `selected_start`, `available_slots`.

---

## 5. Tool mapping table

| Retell tool | Method + URL (`/api/v1/voice-agent`) | Backing service | Status |
|---|---|---|---|
| `search_lead` | `POST /search_lead` | `lead_phone_resolver`, `lead_service` | Implemented |
| `create_lead` | `POST /create_lead` | contact repo + `lead_service` | Implemented |
| `update_lead` | `POST /update_lead` | `lead_service.update_status` / `move_pipeline_stage` | Implemented |
| `save_property_details` | `POST /save_property_details` | `property_text_extractor` + contact `property_snapshot` | Implemented |
| `get_available_slots` | `GET /get_available_slots` | `SlotAvailabilityService` | Implemented |
| `create_appointment` | `POST /create_appointment` | `appointment_service.create_from_schema` | Implemented |
| `generate_followup` | `POST /generate_followup` | `VoiceFollowUpService` | Implemented |
| `create_pending_action` | `POST /create_pending_action` | `pending_action_service` | Implemented |
| `send_sms` | `POST /send_sms` | Twilio system number | Implemented |
| `send_email` | `POST /send_email` | `core/email_controller` | Implemented |
| `get_customer_history` | `POST /get_customer_history` | `lead_service.get_customer_card` | Implemented |
| `save_call_summary` | `POST /save_call_summary` | `call_service` + analysis | Implemented |
| `save_recording_analysis` | `POST /save_recording_analysis` | appointment metadata | Implemented |
| `surface_next_actions` | `POST /surface_next_actions` | `pending_action_service` | Implemented |
| `get_current_date` | `GET /get_current_date` | company timezone | Implemented |

Auth for all: header `X-Voice-Agent-Secret: <shared secret>` + `company_id` in body/query (the agent is provisioned per-company, like CTM/ST webhooks use `X-Worker-Secret`).

---

## 6. Conversation flow

```
 (start) Recognize Caller [function: search_lead, silent]
            │ (always)
            ▼
        Greeting [conversation]
   ┌────────┴─────────────────────────────┐
   │ returning caller (crm_found)          │ new caller
   ▼                                       ▼
 Personalized greet ───────────────▶ Capture Name [extract]
                                           │
                                           ▼
                                  Lead Qualification [conversation]
                                  (insurance_status, urgency, service offered?)
                                           │
                          ┌────────────────┼─────────────────┐
                service NOT offered    qualified         not interested
                          │                │                  │
                          ▼                ▼                  ▼
              Extract Qual [extract] ─▶ Property Collection [conversation]
                          │                (address, house_type, sqft,
                          │                 roof_type, roof_age)
                          ▼                       │
                  (lead_status set)               ▼
                          │              Extract Property [extract]
                          │                       │
                          │                       ▼
                          │              save_property_details [function]
                          │                       │
                          │                       ▼
                          │              Problem Identification [conversation]
                          │                       │
                          │                       ▼
                          │              Extract Problem [extract]
                          │                       │
                          │                       ▼
                          │              Appointment Scheduling [conversation]
                          │                       │ wants appt
                          │             ┌─────────┴──────────┐ no appt now
                          │             ▼                    │
                          │   get_current_date [function]    │
                          │             ▼                    │
                          │   Extract Date/Time [extract]    │
                          │             ▼                    │
                          │   get_available_slots [function] │
                          │             ▼                    │
                          │   Confirm Slot [conversation]    │
                          │             ▼                    │
                          │   create_appointment [function]  │
                          │             ▼                    │
                          └────────────▶ Lead Create/Update [function: create_lead]
                                                  │ (wait_for_result: false)
                                                  ▼
                                        Action Summary [conversation]
                                                  ▼
                                        create_pending_action [function]
                                                  ▼
                                        Follow-up Creation [function: generate_followup]
                                                  │ (fire-and-forget)
                                                  ▼
                                        Anything Else [conversation]  ◀────┐
                                          │ more │ done                    │ (every branch
                                          ▼      ▼                         │  returns here)
                                  (re-enter)   End Call [end]──────────────┘
```

Per-node detail (type · prompt intent · extracts · tool · key edges) is encoded directly in the JSON in §8 — every `function` node has a warm stall prompt + `else_edge`, every `extract_dynamic_variables` node has `finetune_transition_examples`, and the hub re-routes by intent exactly like the reference `Anything Else` node.

---

## 7. Voice-agent API (implemented)

Router: `app/routes/v1/voice_agent.py` mounted at `/api/v1/voice-agent`.

Auth: header `X-Voice-Agent-Secret` (env `VOICE_AGENT_SECRET`). Post-call webhook: `POST /api/v1/webhooks/retell/call-ended` with `X-Retell-Signature`.

Setup runbook: [RETELL_SETUP.md](./RETELL_SETUP.md)

| Endpoint | Status |
|----------|--------|
| `POST /search_lead` | Implemented — `LeadPhoneResolver` + customer card history |
| `POST /create_lead` | Implemented — contact upsert + lead create, `retell_call_id` idempotency |
| `POST /save_property_details` | Implemented — `property_text_extractor` + `property_snapshot` |
| `GET /get_available_slots` | Implemented — `SlotAvailabilityService` + `business_hours` |
| `POST /create_appointment` | Implemented — wraps `AppointmentService.create_from_schema` |
| `POST /generate_followup` | Implemented — `VoiceFollowUpService` → `follow_up_otto` proposed row |
| `POST /send_email` | Implemented — `EmailController` / Mailgun |
| `POST /save_call_summary` | Implemented — `CallService.ingest_call` (+ webhook path) |
| All other tools in §5 | Implemented — see `VoiceAgentService` |

Local import: `python scripts/patch_retell_agent.py --host https://<ngrok>.ngrok-free.app` → `AUTO_RETELL_AGENT.local.json`.
