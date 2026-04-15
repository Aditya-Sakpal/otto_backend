# GoMotto Product Audit — Engineering Plan

**Source:** [`app/docs/Broken items, missing features from initial spec, future features.pdf`](./Broken%20items,%20missing%20features%20from%20initial%20spec,%20future%20features.pdf) — 47 bugs + 5 missing features.

This document is the living backend engineering plan. It is organised by what still needs to be done, what was fixed, and what the frontend team needs to act on.

---

## Constraints

**Preserve existing API contracts.** The frontend is tightly coupled to current response shapes; all backend fixes must leave field names, types, and nullability unchanged.

- Fix at the data-production layer, never the contract layer.
- Do not flip `int`/`float` → `Optional[X]` on metrics endpoints. Metrics currently return `0`/`0.0` for empty; keep it that way.
- Do not change existing string/enum values (e.g., `booking_status` stays `"booked" | "not_booked" | "service_not_offered" | None`).
- Extensions must be additive-only. New optional fields are fine; renaming/retyping/removing existing ones is not.
- If a fix genuinely requires a contract break, treat it as a coordinated frontend/backend migration — not part of backend work.

### Frontend is read-only to this plan

The frontend team owns everything under [`Otto-Frontend/`](../../Otto-Frontend). Backend work does not change frontend code. Where a fix requires frontend work (either to address a frontend-only bug or to opt into a new additive field), it is listed under **Frontend Tasks** below with exact file:line citations.

### Known contract quirks (do not "fix" without coordination)

1. **`objections` serialises differently across two endpoints** — both read from the same `CallAnalysisORM.objections: ARRAY(String)`:

   | Endpoint | Field type |
   |---|---|
   | `GET /api/v1/calls/logs` (Call Logs) | `Optional[str]` — comma-separated |
   | `GET /api/v1/leads/{id}/details` (Lead Details) | `List[str]` |

   Unifying would break one of the two frontends. Flag as tech debt; leave shapes alone.

2. **Call Logs renders `is_booked`, not `booking_status`** — the Booked column in the frontend's Call Logs table (`call-log/page.tsx:1054-1075`) reads the boolean `is_booked` + `is_service_offered`. The string `booking_status` is received but never rendered. Any backend fix for booking detection must target `is_booked`.

---

## Root causes — 47 bugs → 7 RCs

| RC | Root cause | PDF issues it explains |
|----|------------|------------------------|
| **RC-1** | Multi-tenant data leak — `/metrics/*` accepted `company_id` query without validating caller | #45 |
| **RC-2** | Shoonya summary pipeline silently fails — downstream fields default to `None`/`"not_booked"`/`"Unassigned"` with no flag | #7, #10, #15, #19 → #5, #6, #14, #16, #18, #20, #44 |
| **RC-3** | No shared source of truth — Lead Insights / Pipeline / Call Logs / Sales Insights compute independently | #2, #3, #29, #42, #44 |
| **RC-4** | Classification has no confidence floor, no review queue, no call-type taxonomy | #1, #2, #4, #8, #11, #12, #21 |
| **RC-5** | Pipeline is not event-/time-aware — nothing advances CSR Booked → Sales Rep Appt Scheduled → Appt Ran | #14, #17, #18, #26, #27, #31, #32, #33, #34, #37 |
| **RC-6** | No deduplication at ingest | #4, #22, #35, #39 |
| **RC-7** | No QA/validation layer between AI output and UI | #25, #38, #40, #47 |

**Frontend-only root cause** (not in backend scope):

| RC-F1 | Frontend ships placeholder/fallback data in prod | #41, #46 |
|---|---|---|

---

## Shipped (backend)

### Sales Insights + Call Logs

- **#45 — Multi-tenant leak (LAUNCH-BLOCKER).** New [app/core/tenant.py](../core/tenant.py) exposes `require_company_access` (router-level dependency) and `assert_user_access` (in-route helper). Applied to `/api/v1/metrics/*` (all routes via `include_router` dependency), `/api/v1/users` (list), `/api/v1/users/sales-reps`. Team-stats query in `SalesRepDashboardService` was already filtering by `company_id` correctly. Regression tests at [tests/test_tenant_isolation.py](../../tests/test_tenant_isolation.py).
- **#42 — Call Logs missing objections.** `/calls/logs` now falls back to `CallAnalysisORM.objection_texts` when the classified `objections` array is empty, matching `/leads/{id}/details` behaviour. Gated on `analysis_status=="completed"` so failed analyses don't render misleading strings.
- **#43 — Impossible qualified+unbooked+no-objection combo.** Resolves as a cascade from #42 + #44.
- **#44 — Every call shows "Not Booked".** Rewrote the `is_booked` / `is_qualified` derivation in [call_service.py:1689-1725](../services/call_service.py#L1689-L1725) — returns `None` (not `False`) when analysis is missing/pending/failed. New additive field `analysis_status` on `CallLogEntry` schema surfaces the explicit state (`not_analyzed | pending | processing | completed | failed`).
- **#47 — Suspicious KPI values (Follow-up Rate, Script Adherence, Total Conversations).** Added `CallAnalysisORM.status == "completed"` filter to both follow-up rate queries and the script-adherence AVG in [sales_rep_dashboard_service.py](../services/sales_rep_dashboard_service.py). Values stay `int`/`float`.

### Shoonya failure visibility (call + sales audio)

- **`_mark_call_analysis_failed` helper** in [webhooks.py](../routes/v1/webhooks.py) — when the Shoonya summary fetch fails, writes `CallAnalysisORM.status="failed"` + `CallProcessingJobORM.status="failed"` (with `failed_at`, `error`).
- **`_mark_appointment_analysis_failed` helper** — parallel path for sales audio. Writes `AppointmentORM.analysis_status="failed"` + `extra_metadata.analysis_failure` (source, detail, timestamp), and transitions any matching `CallProcessingJobORM`.
- **Webhook outer exception handler** routes to the matching helper by inspecting `found_appointment`, so parsing/DB-write failures never leave a tracker stuck in `"processing"`.
- **`POST /recordings/complete`** now flips `appointment.analysis_status="failed"` (and response `status="failed"`) when Shoonya is unavailable or the submission raises.
- **`GET /recordings/{id}/analysis`** returns 200 with the existing schema when `analysis_status="failed"` (previously 404). Pending/processing/unknown still 404.

### `analysis_status` surfaced on every lookup endpoint

So the frontend can always tell "analysis failed / pending" from "call genuinely has no data", the additive `analysis_status` field is now available on every read path that could otherwise be ambiguous:

| Endpoint | Response field | Source |
|---|---|---|
| `GET /api/v1/calls/logs` | `CallLogEntry.analysis_status` | `CallAnalysisORM.status` |
| `GET /api/v1/calls/{call_id}` | `Call.analysis_status` | `CallAnalysisORM.status` (joined in the route) |
| `GET /api/v1/appointments` (list) | `AppointmentResponse.analysis_status` | `AppointmentORM.analysis_status` |
| `GET /api/v1/appointments/{id}` | `AppointmentResponse.analysis_status` | `AppointmentORM.analysis_status` |
| `GET /api/v1/appointments/{id}/context` | `appointment_analysis.analysis_status` | existed previously |
| `GET /api/v1/recordings/{id}/analysis` | top-level `analysis_status` | existed previously |

Values are uniform across all endpoints: `"not_analyzed" | "pending" | "processing" | "completed" | "failed" | null`. For sales-audio rows, `AppointmentORM.extra_metadata.analysis_failure` carries the structured failure reason.

### Pipeline → Appointments List View

- **#36 — Unassigned sales rep.** `_upsert_appointment_from_call` in [call_service.py](../services/call_service.py) now inherits `assigned_rep_id` from `lead.assigned_rep_id` when the lead has one.
- **#37 — Pending outcome never updated.** New [`AppointmentService.transition_stale_pending_appointments`](../services/appointment_service.py) sweeps `pending` appointments past a 24h grace into `no_show` when no recording has been uploaded. Called opportunistically from both list paths. No new enum values.
- **#38 — Impossible appointment times.** New [`appointment_quality.check_time_quality`](../services/appointment_quality.py) flags times outside 06:00–21:00 via `extra_metadata.time_quality="low_confidence"`. No rejection.
- **#39 — Duplicate appointments.** New `AppointmentRepository.find_for_lead_within_window(lead_id, scheduled_start, ±120min)` dedup check before creating a new row.
- **#40 — Generic locations.** `appointment_quality.check_location_quality` drops state-only addresses (e.g. "AZ, US") and marks `extra_metadata.location_quality="low"`.

Tests: 29 cases across [tests/test_tenant_isolation.py](../../tests/test_tenant_isolation.py) (8) and [tests/test_appointment_quality.py](../../tests/test_appointment_quality.py) (20 + helper).

### Cascading partial resolutions

The #44/#42 work also partially resolves the Unbooked Leads and Kanban Pending clusters that share the same upstream root cause (RC-2):

| PDF # | Status |
|---|---|
| #5 Amanda booked-as-unbooked | `is_booked` now honours explicit state; full fix needs upstream Shoonya booking detection |
| #7, #10, #15, #19 "Call summary unavailable" | Failure now explicit via `analysis_status="failed"`; summary regeneration is its own follow-up |
| #14, #18 Booked lead stuck in Pending | Partially resolved; full fix needs pipeline stage automation (#31) |

---

## Frontend Tasks

The following items require frontend work. Backend will not touch these.

### Required (frontend-only bugs)

| PDF # | Task | Location | Recommended fix |
|---|---|---|---|
| **#41** | DD/MM/YYYY date format on Call Logs | [`Otto-Frontend/src/app/(executive)/executive/call-log/page.tsx:227`](../../Otto-Frontend/src/app/(executive)/executive/call-log/page.tsx#L227) | Change `date-fns` format string from `"dd/MM/yyyy h:mm a"` to `"MM/dd/yyyy h:mm a"` (or a locale-aware formatter). Backend already sends ISO 8601. |
| **#46** | `DEFAULT_TEAM` placeholder leaks into prod when API is empty — shows Brandon Ludewig / Bradley Cohurst / Andrew Munoz on every empty tenant | [`Otto-Frontend/src/components/sections/SalesTeamStats.tsx:9-40, 88-90`](../../Otto-Frontend/src/components/sections/SalesTeamStats.tsx#L9-L40) | Remove the `DEFAULT_TEAM` constant (or gate behind `process.env.NODE_ENV !== "production"`). Render an empty-state UI when `stats.length === 0`. |

### Opt-in opportunities (backend added new additive data the frontend can surface)

These are not blocking, but the backend work above created new signals the frontend can render to improve UX. Partial-fix behavior today is unchanged; opting in turns partial fixes into full fixes.

#### Call Logs — opt into `analysis_status` (CL-44 / PDF #44 follow-through)

`GET /api/v1/calls/logs` now returns an additional field per row:

```ts
analysis_status: "not_analyzed" | "pending" | "processing" | "completed" | "failed" | null
```

Current rendering (`log.is_booked ? "Yes" : "No"` and `log.objections || "None Detected"`) continues to work and treats null/failed as "No" / "None Detected", which is the pre-fix behavior. To complete the fix:

- In [`call-log/page.tsx:1054-1075`](../../Otto-Frontend/src/app/(executive)/executive/call-log/page.tsx#L1054-L1075), add a new visual state when `log.analysis_status !== "completed"` — e.g., a "Pending" / "Failed" pill instead of "No".
- In the objections column ([`call-log/page.tsx:1089-1125`](../../Otto-Frontend/src/app/(executive)/executive/call-log/page.tsx#L1089-L1125)), when `log.analysis_status === "failed"`, show a dedicated "Analysis failed" state instead of "No objections".

Backend contract summary:
- `is_booked` will be `null` (not `false`) when the call's analysis is missing/pending/failed.
- `analysis_status` is the authoritative state field.

#### Sales Insights → Leads page — "None Detected" vs null objections

`leads/page.tsx:1592` renders the literal string `"None Detected"` when `lead.objection` is null. Once the Lead Insights page also exposes an analysis state (future work, not Sprint 1), the frontend should distinguish "analysis complete, no objections" from "analysis pending/failed". No change required today.

#### Sales Audio Analysis — handle the new 200 `failed` response (follow-through for CL-44 parity on sales audio)

`GET /api/v1/recordings/{appointment_id}/analysis` previously always returned 404 when analysis wasn't complete. It now returns:

- **200 with `analysis_status="failed"`** and all analytical fields null — show a "Retry analysis" affordance instead of a permanent spinner.
- **200 with `analysis_status="completed"`** — render as before.
- **404** for pending/processing/unknown — existing behavior, show a spinner.

Similarly, `POST /api/v1/recordings/complete` response's `status` field may now return `"failed"` (in addition to the previous `"processing"`). Frontend should surface a retry button immediately on `"failed"`.

#### Appointments list — surface `analysis_status` + data-quality flags (Pipeline → Appointments List follow-through)

`AppointmentResponse` now carries two sources of truth for analysis state:

```ts
analysis_status: "pending" | "processing" | "completed" | "failed" | null

extra_metadata: {
  // Existing keys unchanged (created_from_call, source, ...)
  time_quality?: "low_confidence"       // #38: scheduled_start outside 06:00–21:00
  location_quality?: "low"              // #40: location_address was dropped as state-only
  analysis_failure?: {                  // only on sales audio that has failed
    source: string
    detail: string
    recorded_at: string
  }
}
```

Recommended UI:
- When `analysis_status === "failed"`, render a "Retry analysis" affordance on the appointment row (the cause is typically in `extra_metadata.analysis_failure.detail`).
- When `analysis_status === "pending"` or `"processing"`, render a spinner — don't treat the appointment as "no data".
- When `extra_metadata?.time_quality === "low_confidence"`, render a small warning icon next to the scheduled time with a tooltip like "Time may be incorrect — please verify".
- When `extra_metadata?.location_quality === "low"`, render a placeholder like "Address needed — click to edit" instead of a blank field. (Note: `location_address` is now `null` for these, not "AZ, US".)

#### Call detail — same `analysis_status` semantics

`GET /api/v1/calls/{call_id}` now returns `Call.analysis_status` with the same value set as Call Logs. Any call detail UI that renders transcript / summary / objections should check `analysis_status === "completed"` before treating empty fields as genuine "no data". When failed, show the same retry affordance pattern.

---

## Remaining backend work

Prioritised by blast radius and launch readiness.

### P0 — Launch blockers still open

| PDF # | Plan ID | Work |
|---|---|---|
| #31 | PL-31 | Automatic stage transition: on `Appointment.created` with `booking_status="booked"` → `PipelineStage.APPOINTMENT`; on `scheduled_start < now()` → `APPOINTMENT_RAN`. New `app/services/pipeline_advance_service.py`. |
| #32, #35 | OC-32/35 | Duplicate wins (5/8 in audit). Unique constraint on `appointments(company_id, lead_id, scheduled_start)`; reject closed-won transitions without `appointment_outcome` + `recording_status`; one-time dedup script. |

### P1 — Near-launch

| PDF # | Plan ID | Work |
|---|---|---|
| #6, #9, #16, #20, #36 | CSR-ATTR | Populate `CallORM.csr_user_id` from telephony webhook (`agent_name`/extension → user map); backfill job. (Appointment side partially addressed by #36 fix above.) |
| #2 | OBJ-TAX | Extend `CSRObjectionType`: `WRITTEN_QUOTE_FIRST`, `WARRANTY_VERIFICATION_PENDING`, `PRICE_NEGOTIATION_IN_PROGRESS`, `EXISTING_CUSTOMER_QUESTION`, `VENDOR_SOLICITATION`, `STATUS_CHECK`. Update Shoonya prompt + tests for Tweedy/Sutton/Regera/Miranda/Rincon. |
| #1 | OBJ-1 | Michael Tweedy miscategorization — unit test case within #2. |
| #8, #11, #12, #21 | CALL-TYPE | Expose `CallAnalysisORM.detected_call_type` as first-class filter; route vendor/existing-customer/status-check calls to "Non-Lead Calls" view; exclude from Unbooked. |
| #26, #27 | APPT-STAGE (ext.) | Past-date appointments stuck in Booked; introduce `APPOINTMENT_NO_DATA` stage (or equivalent) for "ran but no recording". #37 already handles the no_show case. |
| #4, #22 | DEDUP (leads) | Composite unique index `leads(company_id, contact_card_id)` + merge-on-ingest logic. |
| #33 | LOST-EMPTY | Outcome classifier: `AppointmentOutcome.LOST` → `LeadStatus.CLOSED_LOST`. Classify 30-day-no-response leads as `DORMANT`. |
| #2 (bucket), #3, #29 | DATA-SOT | Consolidate on single `LeadDetailService` facade / materialized view so Lead Insights / Pipeline / Call Logs / Sales Insights agree on the same lead. |

### P2 — Medium priority

| PDF # | Plan ID | Work |
|---|---|---|
| #28 | NAME-RECONCILE | Reconcile Shoonya summary name vs contact card; prefer contact card unless AI confidence > threshold. |
| #30 | BOOK-APPT-MERGE | Merge redundant Booked vs Appt Scheduled columns (coordinated with frontend). |
| #17, #23, #24, #34 | EMPTY-CARDS | Hide leads with no summary AND no contact card from user-facing views; move to admin "incomplete records" queue. |
| #13 | CHART-FLAT | Left-join calendar table to backfill missing days on booking-rate chart instead of implicit zeros. |
| #25 | DEAL-SIZE | Deal size capture — investigate whether value field is populated at close. |

### P3 — Post-launch

- #3 (Ethylene Regera bucket/card) — falls out of DATA-SOT.
- Taxonomy refinements from real call data.

---

## Missing features (MV1 spec)

| PDF # | Feature | Complexity | Dependencies |
|---|---|---|---|
| F1 | Unbooked Lead Rehash — auto SMS follow-up | Medium | Needs RC-2 (reliable summary) + #2 OBJ-TAX. `masked_comms_service` has outbound SMS scaffolding. |
| F2 | Post-Appointment Buyer Follow-Up — SMS after no-close | Medium | Needs #33 LOST-EMPTY + outcome classification. Reuses F1 template engine. |
| F3 | AI Receptionist Fail-Safe (voice) | High | No existing IVR scaffolding. Separate PRD. |
| F4 | Voice-Based Role-Play (replace chat-only Ask Otto) | High | Voice I/O infra shareable with F3. Separate PRD. |
| F5 | Clickable Objection Bookmarks on Customer Card | Medium-High | **Blocked:** `CallAnalysisORM.objections` has no per-objection timestamps. Needs new `objection_timeline` table + Shoonya timestamp support + frontend seek API. |

Plus: Enterprise Agency Dashboard — separate product surface, scope via the [linked PRD](https://www.notion.so/Enterprise-Agency-Dashboard-Product-Requirements-33573610ef3381c9b6cbda84441df2f9).
