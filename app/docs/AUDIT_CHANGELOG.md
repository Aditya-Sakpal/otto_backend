# Audit Changelog

Issues from the [GoMotto product audit PDF](./Broken%20items,%20missing%20features%20from%20initial%20spec,%20future%20features.pdf) resolved so far. Numbers match the PDF's issue IDs. See [plan.md](./plan.md) for architectural context and remaining work.

## Fully resolved

### Call Logs Page
- **#42** — "Every call says No Objection Detected": Call Logs now falls back to `CallAnalysisORM.objection_texts` when the classified `objections` array is empty (matches Lead Details).
- **#43** — "Qualified + Unbooked + No Objection" impossible combo: resolved by #42 + #44 cascade.
- **#44** — "Every call shows Not Booked": `is_booked` / `is_qualified` now return `null` (not `false`) when analysis is missing/pending/failed. New additive `analysis_status` field surfaces the explicit state.

### Sales Insights Page
- **#45** — Multi-tenant leak: new `require_company_access` FastAPI dependency applied to `/api/v1/metrics/*`, `/api/v1/users`, `/api/v1/users/sales-reps`. Cross-tenant reads now 403.
- **#47** — Placeholder/inaccurate KPI metrics: follow-up rate and script-adherence queries now filter `CallAnalysisORM.status="completed"` so failed analyses don't skew the averages.

### Pipeline → Appointments List View
- **#36** — Unassigned sales rep: appointments ingested from call analysis now inherit `assigned_rep_id` from the lead.
- **#37** — Pending outcome never updated: pending appointments past 24h grace with no recording auto-transition to `no_show` on list reads.
- **#38** — Impossible appointment times (1 AM, 3 AM): times outside 06:00–21:00 flagged via `extra_metadata.time_quality="low_confidence"`.
- **#39** — Duplicate appointments: ingest dedup via new `(lead_id, scheduled_start ±2h)` window check before creating a new row.
- **#40** — Generic locations ("AZ, US"): state-only addresses dropped from `location_address`; `extra_metadata.location_quality="low"` set instead.

## Partially resolved (cascading from #44 infrastructure)

These become fully resolved once (a) Shoonya's upstream summary/booking detection improves and (b) frontend opts into `analysis_status` for rendering.

- **#5** Amanda Gattenby booked-as-unbooked — `is_booked` honours explicit state; full fix needs upstream detection
- **#7, #10, #15, #19** "Call summary unavailable" — failure now explicit via `analysis_status="failed"`; summary regeneration is separate follow-up
- **#14, #18** Booked lead stuck in Pending — partially resolved; full fix requires pipeline stage automation (#31)

## Closed as by-design

After review with product:

- **#12 rendering** — "None Detected" on the Leads page when `lead.objection` is null is a planned fallback. The backend classification side of #12 (existing-customer misclassification) is still tracked under CALL-TYPE in [plan.md](./plan.md).
- **#17, #24** — "Unknown Lead" / "Unknown Customer" when the name is null are planned fallbacks. 

## Needs product decision

- **#14, #17, #18** (the "Pending column" aspect) — no `"pending"` stage exists in the pipeline config or the `PipelineStage` enum. Not part of the agreed lifecycle. If product wants one, the enum + config need to change before any backend work.
