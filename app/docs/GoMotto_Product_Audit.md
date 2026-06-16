# GoMotto Product Audit

---

## 1 — Michael Tweedy miscategorized (Scheduling conflicts vs “wants written quote first”)

**Issue:** Lead shown under wrong objection vs expected “wants written quote first”. Otto has no enum for that phrase; mapping is Shunya raw strings + `ObjectionClassifier` keywords.

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** shoonya should make one more category for objections classifications with name - wants written quote first

---

## 2 — “Other” bucket overuse (~53% unbooked)

**Issue:** Most unbooked objections roll into `other` because many Shunya strings don’t hit `ObjectionClassifier` keywords and default to `other`.

**Shoonya:** YES  
**Resolved:** No  
**How:** —  
**Your suggested change:** — 

---

## 3 — Call logs “Other” vs Lead Insights “Other → Customer needs time to decide” (Ethelind Rivera)

**Issue:** Same call, two ways of showing objections. Call Logs only show the **Otto bucket** after keyword rules → it landed on `other`. Lead Insights also uses Otto, but for `other` it breaks out sub-rows using the raw Shunya string.

**Shoonya:** maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** would be automatically resolved if we fix objection classification, in bug no 2

---

## 4 — Duplicate lead entries (Michael Tweedy twice)

**Issue:** Same person appears twice in lead-type views because one lead can have multiple objections, that's why it is shown in multiple categories.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 5 — Amanda Gattenby (“booked” vs unbooked list)

**Issue:** Booked lead showing as unbooked (Amanda Gattenby)

**Shoonya:** YES  
**Resolved:** Partial  
**How:** `is_booked` now honours explicit state and returns `null` (not `false`) when analysis is missing/pending/failed — prevents false “Not Booked” display. Full fix requires Shoonya upstream booking detection improvement.  
**Your suggested change:** —

---

## 6 — CSR not assigned (Amanda Gattenby)

**Issue:** we are not sending anything related to csr in pipeline detail api

**Shoonya:** no  
**Resolved:** YES  
**How:** The front end now maps the CSR field from the pipeline detail data.  
**Your suggested change:** —

---

## 7 — Call summary unavailable (Amanda Gattenby)

**Issue:** Shoonya's issue — summary not in db

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** Analysis failure is now explicit via `analysis_status="failed"` field on call log responses — frontend can distinguish "no data yet" from a failed analysis. Full fix (actual summary regeneration) requires Shoonya upstream resolution.  
**Your suggested change:** —

---

## 8 — Existing customer misclassified as unbooked lead (Joshua Crosby)

**Issue:** Lead `4aa3cc6f-e18c-4b12-bf6a-2119d3f564a1`: `is_existing_customer` is stored on the call analysis and used for filters / metrics, not for choosing qualified vs unbooked.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 9 — CSR not assigned — recurring (Joshua Crosby)

**Issue:** we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** YES  
**How:** The front end now maps the CSR field from the pipeline detail data.  
**Your suggested change:** —

---

## 10 — Call summary unavailable (Joshua Crosby)

**Issue:** Same lead/call: `call_analyses.summary` is not NULL but holds the literal "Call summary unavailable" (24 chars) from upstream — no usable summary in practice.

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** Analysis failure is now explicit via `analysis_status="failed"` field — frontend can render a clear failure state rather than the placeholder string. Full fix requires Shoonya to stop returning placeholder strings.  
**Your suggested change:** —

---

## 11 — Subcontractor solicitation misclassified as unbooked lead (Miranda)

**Issue:** Shoonya’s — `is_existing_customer` comes from their qualification payload; Otto just stores it.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 12 — Existing customer status check misclassified (Rincon Partners)

**Issue:** Shoonya’s — `is_existing_customer` comes from their qualification payload; Otto just stores it.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 13 — Booking rate chart flat lines

**Issue:** In `MetricsService.get_booking_rate_improvement()`, daily values are computed from current `leads` table state, not immutable booking events, causing historical attribution loss.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 14 — Booked lead stuck in Pending (Gary Aull)

**Issue:** Gary Aull — Kanban / audit: booked lead appears stuck in Pending (per GoMotto list).

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** `is_booked` now honours explicit state and returns `null` when analysis is missing/pending/failed, reducing false stuck-in-pending cases. Full fix requires pipeline stage automation (auto-advance on booking event).  
**Your suggested change:** —

---

## 15 — Call summary unavailable (Gary Aull)

**Issue:** Gary Aull (`7155fc87-a1ad-45d5-925f-edfb09fded38`) — completed analysis uses literal “Call summary unavailable” (same placeholder pattern as §7 / §10).

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** Analysis failure is now explicit via `analysis_status=”failed”` field — frontend can render a clear failure state rather than the placeholder string. Full fix requires Shoonya to stop returning placeholder strings.  
**Your suggested change:** —

---

## 16 — CSR not assigned (Gary Aull)

**Issue:** we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** YES  
**How:** The front end now maps the CSR field from the pipeline detail data.  
**Your suggested change:** —

---

## 17 — Lead marked fully complete with no underlying data (Unknown Customer)

**Issue:** Cannot find any lead with Unknown in Lead Insights (checked Pending and Booked columns / views) — no matching row to repro.

**Shoonya:** No  
**Resolved:** By design  
**How:** "Unknown Customer" display when `contact_cards.name` is null is a planned fallback. No backend data loss — the lead exists but the contact name is genuinely missing from the CRM source.  
**Your suggested change:** —

---

## 18 — Booked lead stuck in Pending (Pareem Shah)

**Issue:** Pareem Shah — Kanban / audit: booked lead appears stuck in Pending (per GoMotto list).

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** `is_booked` now honours explicit state and returns `null` when analysis is missing/pending/failed, reducing false stuck-in-pending cases. Full fix requires pipeline stage automation (auto-advance on booking event).  
**Your suggested change:** —

---

## 19 — Call summary unavailable (Pareem Shah)

**Issue:** Pareem Shah — call summary unavailable / placeholder in analysis (per audit).

**Shoonya:** Yes  
**Resolved:** Partial  
**How:** Analysis failure is now explicit via `analysis_status="failed"` field — frontend can render a clear failure state rather than the placeholder string. Full fix requires Shoonya to stop returning placeholder strings.  
**Your suggested change:** —

---

## 20 — CSR not assigned (Pareem Shah)

**Issue:** Pareem Shah — we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 21 — Unqualified column only contains abandoned calls

**Issue:** Pipeline board Unqualified column (`pipeline_stage = unqualified`) is observed to show only leads with `abandoned` status, not other “not qualified” outcomes.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** what else do you expect to be in unqualified other than abandoned calls

---

## 22 — Duplicate lead entries (same contact, pipeline / Unqualified)

**Issue:** Same person appears multiple times as separate `leads` rows (different `lead_id`, same `contact_card_id`). Otto creates one Otto lead per `st_lead_id` and does not collapse on contact.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** On ST lead upsert, reuse an existing lead for `(company_id, contact_card_id)` (or store multiple `st_lead_id`s on one lead) instead of always inserting a new row per ST lead id.

---

## 23 — Empty cards when opening a lead under Unqualified (pipeline)

**Issue:** Pipeline detail is built from calls + `call_analyses`. Many Unqualified leads have no `calls` linked to that `lead_id`, so tabs/conversations are empty.

**Shoonya:** Maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** Otto: dedupe ST leads + attach/link calls to the canonical lead per contact (or show explicit “No conversations on this lead” when `calls` = 0). Shoonya: reduce placeholder / empty analysis payloads where calls exist.

---

## 24 — “Unknown Lead” name recurring (Pipeline)

**Issue:** Cards and lists show “Unknown Lead” (or Unknown) when `contact_cards` name is missing, not joined, or lead has no contact yet.

**Shoonya:** No  
**Resolved:** By design  
**How:** “Unknown Lead” display when `contact_cards.name` is null is a planned fallback. No backend data loss — the contact name is genuinely missing from the CRM source.  
**Your suggested change:** Require `contact_card_id` before pipeline surface; backfill name from ST/GHL; single fallback string + telemetry when name still null.

---

## 25 — Pipeline header shows $0k total value with 8 Won deals (Pipeline)

**Issue:** Header deal value / pipeline total reads $0k while multiple Won cards exist — `leads.deal_size` not set from CRM (ServiceTitan job value / invoice not synced).

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Ingest job total / opportunity amount into `deal_size` on win; manual edit until sync exists; header uses same field as card detail.

---

## 26 — Past-date appointments stuck in Booked column (Carla Woods)

**Issue:** Lead still appears under Booked while the linked appointment is already in the past and the card does not advance. Missing integration or auto-transitioning.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Reconcile appointments from ST on a schedule or webhook; optionally auto-move leads from booked → appointment when `scheduled_start` is set and in the future.

---

## 27 — No “Appointment Not Recorded” stage exists

**Issue:** Pipeline board has no column / `PipelineStage` for “appointment happened but was never recorded” — leads get forced into Booked, Appointment, or other stages.

**Shoonya:** Maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** Add an explicit stage (or flag + filter), migration + API + UI rules for when to use it.

---

## 28 — Customer name inconsistency within same lead (Carla Woods / Karla Capichorto)

**Issue:** can't find this bug, maybe already resolved

**Shoonya:** No  
**Resolved:** no  
**How:** —  
**Your suggested change:** —

---

## 29 — Booking status null / “Not Booked” on a Booked-column lead (e.g. Don Ainley)

**Issue:** Booking status is null likely because Service Titan creates multiple empty records for one lead.

**Shoonya:** NO  
**Resolved:** No  
**How:** —  
**Your suggested change:** Shoonya should always return a non-null `booking_status` on completed analyses when inferable from the call; align with CRM when booking exists off-call.

---

## 30 — Redundant Booked vs. Appt Scheduled columns

**Issue:** Pipeline board treats Booked and Appointment as separate columns, causing confusion on where a card should live and extra drag moves.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Rename and sharpen definitions, merge into one column with sub-status, or hide one column for roles that do not need both.

---

## 31 — Sales Rep stage has zero leads — entire half of pipeline is dead

**Issue:** because leads are moved to sales rep stage manually

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Auto-assign or require rep at handoff (Booked → Appointment); backfill `assigned_rep_id` from ST; hide rep-specific columns until assignment workflow exists.

---

## 32 — Won leads have no underlying data (Pipeline → Outcome)

**Issue:** probably because its dummy

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Sync job/invoice/outcome from ST (or source of truth); block or flag Won without backing appointment / closed record.

---

## 33 — Lost column is empty (“impossible”) (Pipeline → Outcome)

**Issue:** Lost pipeline column stays empty while business expects some closed-lost volume — `pipeline_stage` / `status` not updated from CRM.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Ingest `closed_lost` / lost jobs from ST; allow manual lost from pipeline; verify board query includes `lost` stage with correct company scope.

---

## 34 — Review column full of empty cards (Pipeline → Outcome)

**Issue:** Many cards in Review open to empty pipeline detail — `review` pipeline_stage with no calls or no usable linked rows.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Do not set `review` without a call or explicit reason; migrate orphan review leads; UI copy when no conversations.

---

## 35 — Duplicate Won leads (5 of 8 are duplicates) (Pipeline → Outcome)

**Issue:** Won column shows the same customer / deal multiple times — multiple `leads` for one contact or same lead surfaced twice in UI.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Same as §22: one lead per contact for ST; dedupe Won board by `contact_card_id` or canonical lead; merge duplicate rows.

---

## 36 — Appointments list: all show “Unassigned” sales rep (Pipeline → Appointments)

**Issue:** ServiceTitan `_upsert_appointment` creates appointments without `assigned_rep_id`. UI shows Unassigned for null rep.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Appointments ingested from call analysis now inherit `assigned_rep_id` from the associated lead, so the rep is correctly populated on the Appointments list.  
**Your suggested change:** Map ST technician / job resource to `users.id` on ingest; allow manual assign in Otto; default display rule when null.

---

## 37 — Appointments stuck in “Pending” outcome (Pipeline → Appointments)

**Issue:** `appointments.outcome` defaults `pending`; ST `new` / `accepted` map to pending until `converted` / `dismissed` — rows stay pending if re-sync never arrives.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Pending appointments that are more than 24 hours past their scheduled time and have no associated recording now automatically transition to `no_show` on list reads, clearing the stuck-pending backlog.  
**Your suggested change:** Poll / webhook job completion; map more ST statuses; job-age rule to flip stale pending; manual complete / no-show in app.

---

## 38 — Impossible appointment times (1 AM, 3 AM, etc.) (Pipeline → Appointments)

**Issue:** `scheduled_start` wrong wall-clock — typical causes: UTC vs local mishandled on display, bad `start` string from ST, or using ingest time instead of real slot.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Times outside the 06:00–21:00 window are now flagged via `extra_metadata.time_quality="low_confidence"` so the frontend can surface a warning rather than display a misleading off-hours time.  
**Your suggested change:** Store IANA timezone from ST; render in company TZ; validate absurd hours; reject rows missing a real slot.

---

## 39 — Duplicate appointments (Pipeline → Appointments)

**Issue:** Same booking / customer appears more than once — known risk from double ingest despite `st_booking_id` lookup.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Ingest now deduplicates via a `(lead_id, scheduled_start ±2h)` window check before creating a new appointment row, preventing re-ingested or near-duplicate bookings from appearing twice.  
**Your suggested change:** Harden unique constraint on `extra_metadata.st_booking_id` + upsert; merge duplicates in cleanup job.

---

## 40 — Generic locations (“AZ, US”) (Pipeline → Appointments)

**Issue:** `location_address` built from sparse ST address or contact fallback when street missing — reads as useless “AZ, US”.

**Shoonya:** No  
**Resolved:** Yes  
**How:** State-only addresses (e.g. “AZ, US”) are now dropped from `location_address` and `extra_metadata.location_quality=”low”` is set instead, so the UI can show a clear “address unavailable” state rather than a misleading partial string.  
**Your suggested change:** Prefer full structured address from ST; hide generic-only strings; enrich via geocode when only lat/lng or partial.

---

## 41 — Wrong date on every call in Call Logs (e.g. 07/04/2026) (Call Logs)

**Issue:** can't find this bug, maybe already resolved

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Expose business date in company TZ; document that `call_received` is ingest timestamp unless renamed.

---

## 42 — Every call says “No Objection Detected” (Call Logs)

**Issue:** `get_call_logs` maps empty `call_analyses.objections` to the explicit string `None Detected`.

**Shoonya:** Yes  
**Resolved:** Yes  
**How:** Call Logs now falls back to `CallAnalysisORM.objection_texts` (raw Shoonya strings) when the classified `objections` array is empty, matching the same behaviour as Lead Details and significantly reducing false “No Objection Detected” entries.  
**Your suggested change:** Shoonya: improve objection extraction coverage. Otto: show “No objections in payload” vs “Classifier found none”; optional re-run analysis for legacy rows.

---

## 43 — “Qualified + Unbooked + No Objection” feels contradictory (Call Logs)

**Issue:** UI stacks `lead.status` tag “Qualified, unbooked” with call log “None Detected” — looks contradictory but is not strict logic error.

**Shoonya:** yes  
**Resolved:** Yes  
**How:** Resolved as a cascade of fixes #42 (objection fallback) and #44 (null booking state) — objections now show raw Shoonya text when available, and booking status no longer falsely reads “Not Booked” when data is simply missing.  
**Your suggested change:** Soften copy (“No objections captured”) or suppress objection chip when empty; explain unbooked ≠ objection required in tooltip.

---

## 44 — Every call shows “Not Booked” (Call Logs)

**Issue:** zero data in recent calls

**Shoonya:** yes  
**Resolved:** Yes  
**How:** `is_booked` and `is_qualified` now return `null` (not `false`) when analysis is missing, pending, or failed. A new additive `analysis_status` field on each call log row surfaces the explicit state (`”pending”`, `”failed”`, `”completed”`), allowing the frontend to distinguish “not booked” from “booking status unknown”.  
**Your suggested change:** Otto: if lead or ST says booked, backfill or overlay booking on call log row; FE: distinguish unknown vs not_booked. Shoonya: align `booking_status` with CRM when integration provides it.

---

## 45 — Sales Insights: wrong company’s sales reps visible (Sales Insights)

**Issue:** Sales Insights / team UI lists reps that belong to another company or wrong roster for the selected tenant.

**Shoonya:** No  
**Resolved:** Yes  
**How:** A `require_company_access` FastAPI dependency is now applied to all `/api/v1/metrics/*`, `/api/v1/users`, and `/api/v1/users/sales-reps` endpoints. Cross-tenant reads now return 403.  
**Your suggested change:** Audit all Sales Insights queries with `company_id = current_user.company_id`; add tests; remove global rep fetches.

---

## 46 — Placeholder data instead of empty state in Team cards (Sales Insights)

**Issue:** Team cards show zeros / blanks as if they were real baselines instead of a clear “no data yet” empty state.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Use empty state copy + skeleton until N≥min sample; hide 0% team compare rows; optional demo toggle for canned baselines.

---

## 47 — Placeholder / inaccurate Core KPI metrics (Sales Insights)

**Issue:** Core KPI tiles show 0, dash, or static placeholder values that read as live metrics — insufficient data or stub pipeline wired as numbers.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Follow-up rate and script-adherence queries now filter `CallAnalysisORM.status=”completed”`, ensuring failed or pending analyses no longer skew the averages or produce misleading zeros.  
**Your suggested change:** Gate KPIs on data availability; label “insufficient sample”; wire KPIs to real metrics_service / DB aggregates per company_id only.

---

## 48 — S3 Link Accessibility

**Issue:** S3 links were not public, preventing access to resources.

**Shoonya:** No  
**Resolved:** Yes  
**How:** RCA identified it as an account-level configuration issue; Tushar re-logged into the account, which resolved the issue.  
**Your suggested change:** —

---

## 49 — CTM Webhook Data Retrieval

**Issue:** CTM webhooks occasionally fail to return the call URL in the payload.

**Shoonya:** No  
**Resolved:** Yes  
**How:** Added retry logic that calls the separate CTM call API three times to attempt to retrieve the data.  
**Your suggested change:** —
