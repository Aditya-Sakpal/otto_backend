# Issues That Need Shunya (Upstream) Fixes

Audit items whose root cause is inside Shunya's pipeline, not Otto. Otto has surfaced, flagged, or worked around each one — but the actual data-quality fix has to ship on Shunya's side. Share this list with the Shunya team.

Companion reading:
- [plan.md](./plan.md) — full engineering plan
- [AUDIT_CHANGELOG.md](./AUDIT_CHANGELOG.md) — what Otto has shipped
- [AUDIT_FRONTEND_INTEGRATION.md](./AUDIT_FRONTEND_INTEGRATION.md) — frontend integration

---

## P0 — Reliability (blocks trustworthy analytics)

### S1. Summary generation fails silently
**Audit:** #7, #10, #15, #19 (Amanda Gattenby, Joshua Crosby, Gary Aull, Pareem Shah all show "Call summary unavailable" despite real calls of 5–12 minutes). Root cause `RC-2` in the engineering plan.

**What Shunya does today:**
- On some calls the webhook fires with `status: "completed"`, but `GET /api/v1/call-processing/summary/{call_id}` returns an empty body, 4xx, or times out.
- No hint in the response that Shunya itself hit an internal failure — Otto can only infer it from a missing payload.

**What we need from Shunya:**
- A reliable path from successful webhook to a populated summary — either the summary is ready when the webhook fires, or the webhook waits / retries internally.
- If Shunya's own processing failed, the Summary API should return an explicit failure payload (e.g., `status: "failed", error: {...}`) instead of empty data.
- A backend retry endpoint that re-submits the original audio and re-runs the whole pipeline (not just the summary step). See S11 below.

**Otto's workaround:**
Otto now writes `CallAnalysisORM.status = "failed"` and `AppointmentORM.analysis_status = "failed"` whenever the Summary API returns nothing usable, and surfaces that state via the new `analysis_status` field. The frontend shows "Retry analysis" for these. But we're only papering over Shunya's silence; the underlying summary is still missing.

---

### S2. Booking detection misses clearly-booked calls
**Audit:** #44, #5 (Amanda Gattenby booked an appointment for April 14th 10am–12pm on a live call, system marked her "Not Booked").

**What Shunya does today:**
- Transcribes the call, then sets `booking_status = "not_booked"` even when the transcript text clearly contains a confirmed appointment time ("see you Tuesday at 2").
- Precision/recall of the booking detector is the authoritative bottleneck — Otto has no independent booking signal to reconcile against.

**What we need from Shunya:**
- Improved booking-intent classifier — should score "booking confirmed" vs "booking proposed" vs "customer declined" with confidence.
- Confidence scores per decision so Otto can send low-confidence rows to a manual-review queue rather than silently default.
- Optional: expose the text span(s) that led to the decision so we can debug disagreements.

**Otto's workaround:**
`is_booked` is now `null` (not `false`) when analysis hasn't completed, so the frontend can distinguish "pending" from "confirmed no". But for a case like Amanda where Shunya's classifier got it wrong on a completed analysis, there's nothing Otto can do.

---

### S3. Call-type misclassification
**Audit:** #2 (53% of unbooked leads land in "Other"), #8 (Joshua Crosby — existing customer misread as unbooked lead), #11 (Miranda from Contracting Miles — B2B vendor treated as qualified lead), #12 (Rincon Partners — status-check call treated as unbooked lead), #21 (Unqualified column only has abandoned calls).

**What Shunya does today:**
- `detected_call_type` today emits a small set: `fresh_sales`, `follow_up_inquiry`, `existing_customer_service`.
- Vendor solicitations, status-check calls, warranty questions, subcontractor inquiries all fall into `fresh_sales` by default.
- Objection categorisation collapses anything ambiguous into "Other"; 53% of unbooked leads end up there, which makes the analytics unusable.

**What we need from Shunya:**
- Expand `detected_call_type` with at least: `vendor_solicitation`, `status_check_existing_job`, `warranty_inquiry`, `complaint`.
- Expand CSR objection categories with real-world patterns we've seen: `written_quote_requested`, `warranty_verification_pending`, `price_negotiation_in_progress`, `existing_customer_question`.
- Prompt / model tuning so the existing-customer classifier actually picks up obvious signals ("I already had the roof done", "calling about my last job").

**Otto's workaround:**
Otto exposes `detected_call_type` and `is_existing_customer` on the API and filters them out of metrics. The new categories will need to be added on both sides — backend work is tracked as `OBJ-TAX` and `CALL-TYPE` in the plan.

---

## P1 — Data quality

### S4. Customer name extraction frequently missing
**Audit:** #17, #24 ("Unknown Customer" / "Unknown Lead" recurring on multiple leads).

**What Shunya does today:**
- `customer_name` is often null on otherwise-analysed calls.
- Even when it extracts a name, `customer_name_confidence` is not always populated.

**What we need from Shunya:**
- More robust name-extraction prompt (especially for calls where the rep greets the customer by first name — lots of signal).
- Always populate `customer_name_confidence` so Otto can decide whether to trust the AI name or fall back to the contact card.

**Otto's workaround:**
Frontend renders "Unknown Customer" as a planned fallback (confirmed with product). Not a bug, but the user experience is worse the more often Shunya returns null.

---

### S5. Customer name inconsistency across calls
**Audit:** #28 (Carla Woods / "Karla Capichorto" same lead).

**What Shunya does today:**
- Different calls for the same customer can produce different STT transcriptions of the name — Otto then pushes both into the analysis and the UI shows two names for the same person.

**What we need from Shunya:**
- Return the raw name + a normalised/phonetic form so Otto can reconcile across calls.
- Confidence scoring per name extraction (see S4).

**Otto's workaround:**
Tracked under `NAME-RECONCILE` in the engineering plan (P2). Otto-side fix will prefer the contact-card name unless Shunya confidence is high.

---

### S6. Impossible appointment times
**Audit:** #38 (1 AM, 3 AM, 4 AM, 5 AM, 7 AM appointments — no roofing company books at 1 AM).

**What Shunya does today:**
- Extracts time mentions from ambiguous transcripts ("Tuesday at 1" without AM/PM context) and defaults to the wrong half of the day.
- No confidence score on the extracted datetime, so Otto can't tell a high-confidence 10 AM from a guessed 1 AM.

**What we need from Shunya:**
- `appointment_time_confidence` populated reliably (the field exists in the schema but is usually null).
- Conservative defaults when AM/PM is ambiguous — prefer business-hours interpretation or return null/low-confidence.
- Ideally: the raw transcript span that triggered the time so we can show it in a review UI.

**Otto's workaround:**
Otto flags times outside 06:00–21:00 with `extra_metadata.time_quality = "low_confidence"` — the frontend can surface a warning. But the underlying wrong-time problem needs to be fixed upstream.

---

### S7. Incomplete addresses ("AZ, US")
**Audit:** #40 (multiple appointments show only "AZ, US" instead of a real address).

**What Shunya does today:**
- Extracts whatever address fragments it hears. If the call didn't include a full street address, Shunya returns just state + country and Otto was previously writing that to `location_address`.

**What we need from Shunya:**
- Return `service_address_structured` with an explicit `line1` field; don't return just `state` + `country` as if it were a complete address.
- `address_confidence` populated reliably.

**Otto's workaround:**
Otto now drops state-only addresses from `location_address` and flags them via `extra_metadata.location_quality = "low"`. Frontend shows "Address needed — click to edit". But the real fix is Shunya actually extracting the street address when it's spoken.

---

## P2 — Feature blockers

### S8. No per-objection timestamps
**Spec reference:** F5 — "Clickable Objection Bookmarks on Customer Card" (PDF MV1 spec).

**What Shunya does today:**
- Returns `objections` as an array of strings. Each objection has a category and text, but no `start_ms` / `end_ms` anchoring it to the audio.

**What we need from Shunya:**
- Per-objection timestamps (start + end, milliseconds) so the frontend can seek the audio player to the moment the objection was raised.
- Ideally: aligned with the existing conversation-phases endpoint so the two sources are consistent.

**Otto's workaround:**
None. F5 is currently blocked on this exact upstream work — see plan.md "Missing features" section.

---

### S9. SOP compliance score quality
**Related:** Sales Insights page, #47 (Team Script Adherence at 15% looked suspicious).

**What Shunya does today:**
- `sop_compliance_score` is averaged across all calls; there's no breakdown of why a rep scored low, no stage-by-stage reasoning we can render.
- The score is sensitive to audio quality — short or noisy calls can skew the tenant-wide average heavily.

**What we need from Shunya:**
- Per-stage scoring with text evidence.
- Minimum-duration threshold or confidence cap so 30-second calls don't dominate the team average.
- Optional: separate scores for CSR vs Sales-Rep calls (Otto already partially controls this via `compliance_target_role`, but the model output should respect it).

**Otto's workaround:**
Otto filters `CallAnalysisORM.status = "completed"` from the AVG so failed analyses don't skew it. But the underlying score quality is Shunya's.

---

## P3 — Integration ergonomics

### S10. Status-API polling vs webhook mismatch
**Related:** `POST /api/v1/call-processing/retry/{job_id}` exists but is rarely useful.

**What Shunya does today:**
- Webhook fires on job completion. Separately, `GET /api/v1/call-processing/status/{job_id}` can be polled for state transitions.
- The two sources don't always agree — the webhook can say "completed" while the status endpoint is still "processing" for a few seconds.

**What we need from Shunya:**
- Webhook-at-least-once semantics: if the webhook fires with "completed", the Summary API should be guaranteed ready on the next call from the same request scope.
- Consistent `failed_at`, `error`, `retry_available` fields populated on status responses (`retry_available` is frequently missing).

**Otto's workaround:**
Otto polls the Summary API inside the webhook handler, and writes `CallProcessingJobORM.status="failed"` + `failed_at` ourselves if Shunya doesn't.

---

### S11. No native retry for "submission never landed"
**Context:** When Otto's `POST /recordings/complete` gets a 5xx or a connection error from Shunya, there is no Shunya `job_id`. Shunya's existing `/retry/{job_id}` endpoint cannot help — there's nothing to retry against.

**What we need from Shunya:**
- Either an idempotent submit endpoint (re-sending the same `call_id` is safe and deduplicated on their side), or
- A "retry by call_id" endpoint that doesn't require an existing `job_id`.

**Otto's workaround:**
Otto's new `POST /recordings/{id}/retry` and `POST /calls/{id}/retry` (shipped) just re-call Shunya's `process_call` with the same `call_id` and rely on Shunya accepting a duplicate. If Shunya rejects duplicates, those retries will fail — please confirm the dedup behaviour on your side.

---

## Summary by priority

| Priority | Shunya issue | Audit items |
|---|---|---|
| P0 | S1 Summary generation fails silently | #7, #10, #15, #19 + RC-2 |
| P0 | S2 Booking detection misses clear bookings | #44, #5 |
| P0 | S3 Call-type + objection classification too coarse | #2, #8, #11, #12, #21 |
| P1 | S4 Customer name extraction missing | #17, #24 |
| P1 | S5 Customer name inconsistency | #28 |
| P1 | S6 Impossible appointment times | #38 |
| P1 | S7 Incomplete addresses | #40 |
| P2 | S8 No per-objection timestamps | F5 blocker |
| P2 | S9 SOP compliance score quality | #47 (indirect) |
| P3 | S10 Webhook vs status endpoint mismatch | integration ergonomics |
| P3 | S11 No "retry by call_id" for lost submissions | integration ergonomics |
