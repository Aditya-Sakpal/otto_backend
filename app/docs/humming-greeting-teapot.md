# Otto Sales Rep App — Gap Analysis & Build Plan

## Context

The sales rep mobile app is Otto's core operational interface — the single place where in-person sales reps manage their entire workflow: see appointments, prep with intelligence, record meetings, classify outcomes, track pending actions, get smart nudges, communicate with customers (masked), receive coaching, and improve over time. The executive dashboard mirrors this data across all reps.

This document maps **every step of the rep's journey** against what exists today across three codebases, identifies every gap, and lays out what needs to be built.

### Codebases
- **otto-intelligence** (`/Otto/otto-intelligence`) — AI brain: call processing, objection extraction, insights, coaching, lead scoring, Ask Otto
- **Otto-Backend** (`/Otto/Otto-Backend`) — Operations: leads, appointments, recordings, tasks, metrics, ghost mode, WebSocket
- **Otto-Mobile-App** (`/Otto/Otto-Mobile-App`) — Expo app: screens, components, API integration

---

## CURRENT STATE SUMMARY

### What's Fully Working (End-to-End)
| Capability | Intelligence | Backend | Mobile |
|-----------|-------------|---------|--------|
| Auth (login, tokens, refresh) | — | Done | Done |
| Appointments list + detail | — | Done (CRUD + enrichment) | Done (real API) |
| Audio recording (capture → S3 → complete) | — | Done (initiate/complete) | Done (full flow) |
| Call processing pipeline | Done (8-stage objections, 3-call summary, BANT, compliance) | Done (webhook triggers) | — (submits, doesn't consume results) |
| Outcome classification (Won/Not Won) | — | — | Done (OutcomeSelector) |
| KPI dashboard | — | Done (sales_rep/kpi) | Done (real API) |
| Geofencing + push notifications | — | — | Done (100m radius, heartbeat) |
| Ghost mode service | — | Done (company + user level toggle) | Endpoints defined, **no UI** |
| Pending action extraction | Done (3-call pipeline + noise filter) | Done (pending_actions table + CRUD) | — |
| Weekly insights generation | Done (company, customer, objection) | Done (proxy endpoints) | — |
| Agent progression tracking | Done (trends, anomalies, peer comparison) | — | — |
| Coaching sessions + impact | Done (baseline → follow-up → measurement) | — | — |
| Ask Otto conversational AI | Done (RAG over calls + SOP + coaching) | — | UI shell, **mock responses** |
| Lead scoring (BANT-based) | Done (0-100, hot/warm/cold) | — | — |
| SOP compliance evaluation | Done (per-metric scores) | — | — |
| Conversation phase detection | Done (greeting → discovery → closing) | — | — |

### What's Partially Built
| Capability | What Exists | What's Missing |
|-----------|------------|----------------|
| Follow-ups section | Mobile UI maps appointments to follow-ups | Not driven by actual pending actions from intelligence |
| Insights section | Mobile has 3 hardcoded cards | Not connected to any API |
| Feeds/Leaderboard | Mobile UI complete | All hardcoded mock data |
| Messaging | Mobile UI shell | No backend, no real conversations |
| WebSocket notifications | Backend has follow-up reminders (15min/5min) | No nudge service feeding it |

### What Doesn't Exist At All
| Capability | Status |
|-----------|--------|
| Smart nudge service (staleness-based) | Not built |
| Automated follow-up sequence engine | Not built |
| Masked communications (Twilio proxy) | Not built |
| Appointment context / pre-meeting briefing | Not built |
| Recording analysis screen (post-meeting) | Not built |
| Leads pipeline (grouped by urgency/risk) | Not built |
| Deal risk alerts | Not built |
| Re-engagement scripts for dormant leads | Not built |
| Proactive insight cards | Not built |
| Per-rep objection coaching recommendations | Not built |
| CSR conversation history on appointments | Not built |
| Predictive lead scoring (multi-signal, continuous) | Not built |

---

## GAP ANALYSIS BY REP JOURNEY

### JOURNEY 1: Pre-Appointment Prep

**What the rep needs:** Open upcoming appointment → see full context (who is this customer, what did the CSR discuss, what objections came up, what's the lead score, what should I focus on).

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| See upcoming appointments | — | `GET /appointments` | Done (AppointmentsList) | None |
| See lead score + risk level | Lead scoring done (BANT 0-100) | Not proxied to mobile | Not shown | **Backend proxy + Mobile UI** |
| See CSR conversation history | Call summaries exist in MongoDB | No endpoint to fetch by lead_id for mobile | No component | **Backend endpoint + Mobile component** |
| See previous objections raised | Objections stored per call | No endpoint aggregating by lead | No component | **Backend endpoint + Mobile component** |
| Get AI pre-meeting briefing | Ask Otto could generate this | No appointment context endpoint | No component | **Backend `GET /appointments/{id}/context` + Mobile IntelligenceBriefing component** |
| See pending actions from prior interactions | Extracted by intelligence, stored in backend | `GET /tasks` exists but not lead-scoped for mobile | Not shown per appointment | **Mobile integration** |

**What needs building:**
1. **Backend**: `GET /api/v1/appointments/{id}/context` — joins appointment → lead → contact_card → calls → call_summaries (from intelligence) → pending_actions. Generates AI briefing.
2. **Mobile**: `AppointmentContextScreen` or enhanced `AppointmentDetailModal` showing: CSR conversation carousel, lead score, previous objections, pending actions, AI briefing.

---

### JOURNEY 2: At the Appointment (Recording)

**What the rep needs:** Arrive at location → geofence triggers → toggle ghost mode if needed → record meeting → pause/resume.

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| Geofence triggers on arrival | — | — | Done (100m, push notification) | None |
| Navigate to recording | — | — | Done (notification → record screen) | None |
| Toggle ghost mode before recording | — | Service exists (`ghost_mode_service.py`) | **No UI** — endpoints defined in config but no toggle component | **Mobile: GhostModeToggle component** |
| Record meeting audio | — | `POST /recordings/initiate` | Done (Expo Audio, high quality) | None |
| Pause/Resume | — | — | Done | None |
| Auto-stop on geofence exit | — | — | **Not implemented** — geofence detects EXIT but doesn't auto-stop recording | **Mobile: wire EXIT event to stop** |

**What needs building:**
1. **Mobile**: Ghost mode toggle button on recording screen (calls `POST /ghost-mode/toggle`)
2. **Mobile**: Wire geofence EXIT event to auto-stop recording + upload
3. **Backend**: Tag recording with `ghost_mode: true` if active during initiation

---

### JOURNEY 3: Post-Meeting (Analysis & Classification)

**What the rep needs:** Meeting done → classify outcome → see analysis (summary, objections, compliance, coaching tips) → see pending actions extracted.

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| Select outcome (Won/Not Won) | — | — | Done (OutcomeSelector) | None |
| Upload recording to S3 | — | — | Done (presigned URL) | None |
| Complete recording + trigger processing | Done (full pipeline) | Done (`POST /recordings/complete`) | Done | None |
| View call summary | Done (summary, key_points) | No proxy endpoint for mobile | **No screen** | **Backend proxy + Mobile screen** |
| View objections detected | Done (8-stage extraction) | No proxy endpoint | **No screen** | **Backend proxy + Mobile screen** |
| View how objections were handled | Done (overcome status, response suggestions) | No proxy endpoint | **No screen** | **Backend proxy + Mobile screen** |
| View SOP compliance score | Done (per-metric evaluation) | No proxy endpoint | **No screen** | **Backend proxy + Mobile screen** |
| View pending actions extracted | Done (3-call pipeline, filtered) | `pending_actions` table exists | **No screen showing per-call PAs** | **Mobile screen** |
| View coaching tips | Done (phase detection, compliance gaps) | No endpoint | **No screen** | **Backend endpoint + Mobile screen** |

**What needs building:**
1. **Backend**: `GET /api/v1/recordings/{call_id}/analysis` — proxy to intelligence `GET /call-processing/summary/{call_id}` enriched with SOP evaluation, pending actions from backend.
2. **Mobile**: `RecordingAnalysisScreen` — shows summary, objection cards (with overcome status + suggestions), compliance gauge, pending actions, coaching tips. Navigate here after recording is processed.

---

### JOURNEY 4: Follow-Up & Deal Rehash

**What the rep needs:** Deals that didn't close → what pending actions exist → smart nudges to follow up → contextual recommendations → re-engagement scripts for dormant leads.

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| See leads grouped by urgency | Lead scoring exists | No pipeline endpoint | FollowUpsSection derives from appointments (basic) | **Backend `GET /leads/my-pipeline` + Mobile redesign** |
| See pending actions per lead | Extracted per call | `GET /tasks` exists | Not shown per lead | **Mobile: show per-lead** |
| Smart nudges for stale leads | — | **No nudge service** | **No nudge cards** | **Backend LeadNudgeService + scheduler + Mobile NudgeCard** |
| Contextual follow-up recommendations | Intelligence could generate | **No sequence engine** | — | **Backend SequenceEngine + Mobile enrollment UI** |
| Re-engagement scripts for dormant leads | **Not built** | — | — | **Intelligence re-engagement endpoint + Backend proxy + Mobile display** |
| Deal risk alerts | Intelligence has lead scoring | **No risk alert service** | — | **Backend DealRiskAlertService + Mobile risk indicators** |

**What needs building (largest gap area):**
1. **Backend**: `LeadNudgeService` — scans every 30min for stale leads, generates nudges based on staleness rules, anti-spam, routes via WebSocket
2. **Backend**: `SequenceEngine` — multi-step automated follow-up sequences with 3 automation levels
3. **Backend**: `DealRiskAlertService` — consumes lead scores, generates alerts on drops
4. **Backend**: `GET /api/v1/leads/my-pipeline?rep_id={id}` — leads grouped by action-required / follow-up / new / at-risk
5. **Intelligence**: `POST /api/v1/leads/re-engagement-script` — personalized scripts for dormant leads
6. **Mobile**: NudgeCard component, leads pipeline section, risk indicators

---

### JOURNEY 5: Communication (THE BIGGEST GAP)

**What the rep needs:** All customer communication through the app — calls and texts via masked numbers (like Uber/DoorDash). Customer never sees rep's real number. All conversations recorded and get intelligence.

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| Call customer through app (masked) | — | **Not built** | **Not built** | **FULL BUILD: Twilio proxy + backend + mobile** |
| SMS customer through app (masked) | — | **Not built** | **Not built** | **FULL BUILD** |
| Phone calls recorded automatically | Could process if audio available | **Not built** | **Not built** | **Twilio recording → S3 → processing pipeline** |
| Call recordings get intelligence | Done (pipeline processes any audio) | Webhook exists for telephony | — | **Wire Twilio webhook → processing** |
| Customer can't see rep's real number | — | **Not built** | **Not built** | **Twilio proxy number management** |

**What needs building (new infrastructure):**
1. **Backend**: `twilio_proxy.py` — Twilio Proxy Service creation, proxy number management, session lifecycle
2. **Backend**: `communications.py` routes — `POST /communications/masked-call`, `POST /communications/masked-sms`, `POST /communications/sessions/{id}/complete`
3. **Backend**: `masked_call_sessions` table — tracks proxy sessions, links to leads
4. **Backend**: Twilio webhook handler — receives call completion, triggers recording processing
5. **Mobile**: `MaskedCallButton` component — initiates proxy call via API, then `Linking.openURL(tel:proxy_number)`
6. **Mobile**: `MaskedSMSButton` component — sends SMS through backend
7. **Mobile**: Communication history per lead

---

### JOURNEY 6: Coaching & Improvement Over Time

**What the rep needs:** See how they're performing over time — objection handling trends, compliance scores, coaching session status, improvement areas, peer benchmarks.

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| See compliance score over time | Done (`agents/{rep_id}/progression`) | Not proxied | **No screen** | **Backend proxy + Mobile screen** |
| See objection handling trends | Done (objection insights per category) | Not proxied per-rep | **No screen** | **Intelligence per-rep breakdown + Mobile** |
| See coaching session status + impact | Done (full coaching service) | Not proxied | **No screen** | **Backend proxy + Mobile screen** |
| See improvement areas | Done (anomaly detection, declining metrics) | Not proxied | **No screen** | **Backend proxy + Mobile screen** |
| Peer comparison (on-demand) | Done (`agents/{rep_id}/peer-comparison`) | Not proxied | **No screen** | **Backend proxy + Mobile screen** |
| Proactive coaching recommendations | **Not built** (per-rep weak areas) | — | — | **Intelligence service + Backend + Mobile** |

**What needs building:**
1. **Backend**: Proxy endpoints for intelligence coaching/progression APIs
2. **Intelligence**: Per-rep objection breakdown (extend current company-wide to per-rep)
3. **Intelligence**: Proactive coaching recommendations (auto-flag reps weak on specific objections)
4. **Mobile**: `PerformanceScreen` — progression charts, compliance trends, objection handling, coaching sessions, improvement areas

---

### JOURNEY 7: Ask Otto (AI Assistant)

**What the rep needs:** Ask questions like "What should I focus on with this customer?", "Who should I call today?", "How do I handle price objections?"

| Step | Intelligence | Backend | Mobile | Gap? |
|------|-------------|---------|--------|------|
| Create conversation | Done | — | UI shell exists | **Connect mobile to intelligence API** |
| Ask question + get RAG response | Done (calls + SOP + coaching) | — | **Mock responses only** | **Connect to real API** |
| Get follow-up suggestions | Done (suggested_follow_ups) | — | **Not shown** | **Mobile UI update** |
| Source attribution | Done (call_id, text, confidence) | — | **Not shown** | **Mobile UI update** |

**What needs building:**
1. **Mobile**: Replace mock AI response with real Ask Otto API calls (either direct to intelligence or via backend proxy)
2. **Mobile**: Show sources and suggested follow-ups in chat UI

---

## BUILD PRIORITY (Ordered by Revenue Impact)

### Wave 1: Post-Meeting Intelligence (Makes recordings valuable)
**Why first:** Reps are already recording. But they can't see the results. This is the fastest path to value.

| # | What | Where | Effort |
|---|------|-------|--------|
| 1a | `GET /recordings/{call_id}/analysis` proxy endpoint | Backend | Small |
| 1b | RecordingAnalysisScreen (summary, objections, compliance, pending actions, coaching) | Mobile | Medium |
| 1c | Wire outcome classification to lead status update | Backend | Small |
| 1d | Ghost mode toggle on recording screen | Mobile | Small |
| 1e | Auto-stop recording on geofence EXIT | Mobile | Small |

### Wave 2: Pre-Meeting Intelligence (Makes appointments valuable)
**Why second:** Reps go to appointments blind. Give them context.

| # | What | Where | Effort |
|---|------|-------|--------|
| 2a | `GET /appointments/{id}/context` endpoint (lead + calls + summaries + pending actions + briefing) | Backend | Medium |
| 2b | Enhanced AppointmentDetailModal with CSR conversation carousel + lead score + AI briefing | Mobile | Medium |
| 2c | Proxy intelligence lead scoring to mobile | Backend | Small |

### Wave 3: Smart Nudges & Follow-Up Engine (Makes the app proactive)
**Why third:** This is where Otto stops being a tool and becomes an autonomous revenue engine.

| # | What | Where | Effort |
|---|------|-------|--------|
| 3a | LeadNudgeService (staleness rules, anti-spam, WebSocket delivery) | Backend | Large |
| 3b | `lead_nudges` table + migration | Backend | Small |
| 3c | Nudge routes (list, acknowledge, action, dismiss) | Backend | Medium |
| 3d | Scheduler job (every 30 min) | Backend | Small |
| 3e | NudgeCard component + nudge section in sales dashboard | Mobile | Medium |
| 3f | `GET /leads/my-pipeline?rep_id={id}` (action required / follow-up / at-risk) | Backend | Medium |
| 3g | Leads pipeline section in mobile | Mobile | Medium |

### Wave 4: Masked Communications (Makes Otto the single comms layer)
**Why fourth:** Biggest infrastructure effort but critical for capturing all customer interactions.

| # | What | Where | Effort |
|---|------|-------|--------|
| 4a | Twilio Proxy Service integration | Backend | Large |
| 4b | `masked_call_sessions` table | Backend | Small |
| 4c | Communications routes (masked-call, masked-sms, complete) | Backend | Medium |
| 4d | Twilio webhook → recording pipeline integration | Backend | Medium |
| 4e | MaskedCallButton + MaskedSMSButton components | Mobile | Medium |
| 4f | Communication history per lead | Mobile | Medium |

### Wave 5: Coaching & Performance (Makes reps better over time)
**Why fifth:** High value but depends on sufficient data from Waves 1-4.

| # | What | Where | Effort |
|---|------|-------|--------|
| 5a | Per-rep objection breakdown (extend company-wide insights) | Intelligence | Medium |
| 5b | Proactive coaching recommendations (auto-flag weak areas) | Intelligence | Medium |
| 5c | Backend proxy for progression + coaching APIs | Backend | Small |
| 5d | PerformanceScreen (progression charts, compliance, coaching status) | Mobile | Large |
| 5e | Connect InsightsSection to real API (replace hardcoded cards) | Mobile | Small |

### Wave 6: Ask Otto Integration (Makes the AI assistant real)
**Why sixth:** UI exists, just needs to be connected.

| # | What | Where | Effort |
|---|------|-------|--------|
| 6a | Connect home screen chat to Ask Otto API | Mobile | Medium |
| 6b | Show sources + suggested follow-ups | Mobile | Small |
| 6c | Add suggestion chips that actually work ("Who should I call today?") | Mobile | Medium |

### Wave 7: Automation & Sequences (Makes follow-up autonomous)
**Why seventh:** Builds on nudge service + masked comms for full automation.

| # | What | Where | Effort |
|---|------|-------|--------|
| 7a | SequenceEngine (multi-step follow-ups, 3 automation levels) | Backend | Large |
| 7b | `sequence_templates` + `sequence_enrollments` tables | Backend | Small |
| 7c | Sequence routes (templates CRUD, enroll, cancel, stats) | Backend | Medium |
| 7d | DealRiskAlertService (score drops → nudges) | Backend | Medium |
| 7e | Re-engagement script generation | Intelligence | Medium |
| 7f | Default sequence templates (post-call, post-appointment, dormant) | Backend | Small |

### Wave 8: Intelligence Upgrades (Makes insights smarter)
**Why last:** Enhances quality of everything above but not blocking.

| # | What | Where | Effort |
|---|------|-------|--------|
| 8a | Extend Jaccard sub-objection grouping to all categories | Intelligence | Small |
| 8b | Proactive insight cards (standalone, prioritized, with action URLs) | Intelligence | Medium |
| 8c | Predictive lead scoring (multi-signal, continuous) | Intelligence | Large |
| 8d | Real-time objection detection (stretch) | Intelligence | Large |

---

## WHAT'S BLOCKING vs WHAT'S WIRING

A critical insight: **most of the intelligence already exists**. The biggest gaps are not in AI capabilities — they're in:

1. **Backend proxy endpoints** that make intelligence data available to the mobile app (the backend doesn't expose most intelligence endpoints to mobile yet)
2. **Mobile screens** that consume and display the intelligence (most screens are either mock data or don't exist)
3. **Operational services** in the backend (nudges, sequences, masked comms) that make the platform proactive rather than passive

The intelligence layer can already:
- Process any call and extract summary, objections, compliance, BANT, pending actions
- Track agent progression with trend detection and anomaly flagging
- Measure coaching impact with statistical rigor
- Answer natural language questions about calls, SOPs, and customers
- Score leads on a 0-100 scale with explainability
- Detect conversation phases and identify gaps
- Generate weekly insights with trends and recommendations

**The gap is the operational + interface layer that turns this intelligence into autonomous action.**

---

## VERIFICATION PLAN

After each wave, verify end-to-end:

**Wave 1**: Record a meeting → wait for processing → open analysis screen → see summary, objections, compliance score, pending actions
**Wave 2**: Open upcoming appointment → see CSR call history, lead score, AI briefing → go to meeting informed
**Wave 3**: Let a lead go stale → receive nudge in app within 30 min → see leads pipeline grouped by urgency
**Wave 4**: Call customer through app → customer sees proxy number → call recorded → call gets intelligence processing
**Wave 5**: View performance screen → see progression over 8 weeks → see objection handling trends → see coaching session impact
**Wave 6**: Ask "Who should I call today?" → get real answer based on pipeline data → tap suggestion → navigate to lead
**Wave 7**: Lead goes qualified_unbooked → auto-enrolled in sequence → step 1 fires (nudge or SMS based on automation level) → auto-cancels when rep contacts lead
**Wave 8**: View objection insights with sub-groups across all categories → see proactive insight cards with action buttons → lead scores update continuously
