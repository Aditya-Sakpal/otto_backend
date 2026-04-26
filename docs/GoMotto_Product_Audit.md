# GoMotto Product Audit

Rules: max **3 lines** under **Issue**. Only five fields per item: **Issue**, **Shoonya** (Yes/No), **Resolved**, **How** (only if Resolved = Yes), **Your suggested change** (only when you ask to record it).

---

## 1 — Michael Tweedy miscategorized (Scheduling conflicts vs “wants written quote first”)

**Issue:** Lead shown under wrong objection vs expected “wants written quote first”. Otto has no enum for that phrase; mapping is Shunya raw strings + `ObjectionClassifier` keywords.

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** — shoonya should make one more category for objections classifications with name - wants written quote first

---

## 2 — “Other” bucket overuse (~53% unbooked)

**Issue:** Most unbooked objections roll into `other` because many Shunya strings don’t hit `ObjectionClassifier` keywords and default to `other`.

**Shoonya:** YES  
**Resolved:** No  
**How:** —  
**Your suggested change:** — 

---

## 3 — Call logs “Other” vs Lead Insights “Other → Customer needs time to decide” (Ethelind Rivera)

**Issue:**  **Same call, two ways of showing objections.**  
           Call Logs only show the **Otto bucket** after keyword rules → it landed on `other`.  
           Lead Insights also uses Otto, but for `other` it **breaks out sub-rows using the raw Shunya string** — so you see **“Customer needs  time to decide”** under **Other**. So it’s not two different “truths”; it’s **different UI + mapping**: raw line didn’t match `customer_needs_time_to_decide` keywords (e.g. wording like **“needs time”** vs rule **“need time”**), so both screens are consistent with `other`, Insights just **shows the raw label** underneath.

**Shoonya:** maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** — would be automatically resolved if we fix objection classification , in bug no 2

---

## 4 — Duplicate lead entries (Michael Tweedy twice)

**Issue:** Same person appears twice in lead-type views because one lead can have multiple objections , that 's why it is shown in multiple catgories

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 5 — Amanda Gattenby (“booked” vs unbooked list)

**Issue:** Booked lead showing as unbooked (Amanda Gattenby)

**Shoonya:** YES  
**Resolved:** no  
**How:** —  
**Your suggested change:** —

---

## 6 — CSR not assigned (Amanda Gattenby)

**Issue: we are not sending anything related to csr in pipeline detail api**

**Shoonya:** no  
**Resolved:** YES  
**How:** —  
**Your suggested change:** now front end guy needs to map it.

---

## 7 — Call summary unavailable (Amanda Gattenby)

**Issue:** **Shoonya's issue** —  summary not in db

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 8 — Existing customer misclassified as unbooked lead (Joshua Crosby)

**Issue:** Lead `4aa3cc6f-e18c-4b12-bf6a-2119d3f564a1`: `is_existing_customer` is stored on the call analysis (Shoonya, optionally overridden by `contact_cards.extra_metadata.is_customer`) and used for **filters / metrics**, not for choosing qualified vs unbooked.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 9 — CSR not assigned — recurring (Joshua Crosby)

**Issue:** we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** YES  
**How:** —  
**Your suggested change:** —now front end guy needs to map it.

---

## 10 — Call summary unavailable (Joshua Crosby)

**Issue:** Same lead/call: `call_analyses.summary` is **not NULL** but holds the literal **"Call summary unavailable"** (24 chars) from upstream — **no usable summary in practice**; same pattern as §7 (Shoonya payload).

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 11 — Subcontractor solicitation misclassified as unbooked lead (Miranda)

**Issue:** **Shoonya’s** — `is_existing_customer` comes from their qualification payload; Otto just stores it.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 12 — Existing customer status check misclassified (Rincon Partners)

**Issue:** **Shoonya’s** — `is_existing_customer` comes from their qualification payload; Otto just stores it.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 13 — Booking rate chart flat lines

**Issue:** In `MetricsService.get_booking_rate_improvement()` (dual-period path), daily values are computed from **current** `leads` **table state**, not immutable booking events.

Key problems:

- It counts daily using `LeadORM.status` / `LeadORM.deal_status` **as they are now**.
- It filters a day by `LeadORM.created_at` OR `LeadORM.updated_at`.
- `updated_at` is only the **latest** timestamp (overwritten over time), so historical day attribution is lost.
- So a lead booked on Day X but updated later gets moved off Day X; Day X can show 0 later.
- Also this endpoint returns **rate %** series (`y`), not booking-event counts; tooltip text saying “bookings” can be misleading.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 14 — Booked lead stuck in Pending (Gary Aull)

**Issue:** Gary Aull — Kanban / audit: booked lead appears **stuck in Pending** (per GoMotto list).

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 15 — Call summary unavailable (Gary Aull)

**Issue:** Gary Aull (`7155fc87-a1ad-45d5-925f-edfb09fded38`) — completed analysis uses literal **“Call summary unavailable”** (same placeholder pattern as §7 / §10).

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 16 — CSR not assigned (Gary Aull)

**Issue:** we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** YES  
**How:** —  
**Your suggested change:** — now front end guy needs to map it.

---

## 17 — Lead marked fully complete with no underlying data (Unknown Customer)

**Issue:** **Cannot find** any lead with **Unknown** in **Lead Insights** (checked **Pending** and **Booked** columns / views) — no matching row to repro.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 18 — Booked lead stuck in Pending (Pareem Shah)

**Issue:** Pareem Shah — Kanban / audit: booked lead appears **stuck in Pending** (per GoMotto list).

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 19 — Call summary unavailable (Pareem Shah)

**Issue:** Pareem Shah — call summary **unavailable** / placeholder in analysis (per audit).

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** —

---

## 20 — CSR not assigned (Pareem Shah)

**Issue:** Pareem Shah —we are not sending anything related to csr in pipeline detail api

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** — now front end guy needs to map it.

---

## 21 — Unqualified column only contains abandoned calls

**Issue:** Pipeline board **Unqualified** column (`pipeline_stage = unqualified`) is observed to show **only** leads with `**abandoned`** status, not other “not qualified” outcomes. Repo mapping treats `**abandoned` → `unqualified`**, so the column behaves like **Abandoned** while the label says **Unqualified**.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** —  what else do you expect to be in unqualified other than abandoned calls

---

## 22 — Duplicate lead entries (same contact, pipeline / Unqualified)

**Issue:** Same person appears **multiple times** as **separate `leads` rows** (different `lead_id`, same `contact_card_id` / name / phone). **ServiceTitan** exports **multiple ST lead ids** per customer; Otto **creates one Otto lead per `st_lead_id`** (`extra_metadata.st_lead_id`) and does **not** collapse on contact, so the pipeline **Unqualified** column (and elsewhere) lists duplicates.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** On ST lead upsert, **reuse** an existing lead for `(company_id, contact_card_id)` (or store multiple `st_lead_id`s on one lead) instead of always inserting a new row per ST lead id.

---

## 23 — Empty cards when opening a lead under Unqualified (pipeline)

**Issue:** Pipeline **detail** is built from **calls + `call_analyses`** (and appointments). Many **Unqualified** leads—especially **ST `st_lead_id` rows** and **duplicate leads on the same contact**—have **no `calls` linked to that `lead_id`**, so tabs/conversations are **empty** (not missing Shoonya output). For **GoMotto** company `d481d226-2791-4652-b080-b6b2c6c4f662`, **~63%** of Unqualified leads had **zero calls** in DB check; example `11c533bc-a77a-428b-ae48-6bc25847969f` (Adam Bergman): `**st_lead_id` only, `calls_count` = 0**. A **smaller** subset **does** have analysis but `**summary` = “Call summary unavailable”** / empty **key_points** → treat as **upstream/Shoonya** for **that** subset only.

**Shoonya:** Maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** **Otto:** dedupe ST leads + attach/link calls to the **canonical** lead per contact (or show explicit **“No conversations on this lead”** when `calls` = 0). **Shoonya:** reduce placeholder / empty analysis payloads where calls exist.

---

## 24 — “Unknown Lead” name recurring (Pipeline)

**Issue:** Cards and lists show **“Unknown Lead”** (or **Unknown**) when `**contact_cards`** name is **missing**, **not joined**, or **lead has no contact** yet (ST placeholder lead, broken link). **Otto** display fallbacks + data hygiene — not Shoonya naming.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Require `**contact_card_id`** before pipeline surface; **backfill** name from ST/GHL; single fallback string + **telemetry** when name still null.

---

## 25 — Pipeline header shows $0k total value with 8 Won deals (Pipeline)

**Issue:** Header **deal value / pipeline total** reads **$0k** while **multiple Won** cards exist — `**leads.deal_size`** (or equivalent) **not set** from CRM (**ServiceTitan job value / invoice** not synced), so **sum is zero** despite real revenue. **Otto + ST integration**, not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Ingest **job total / opportunity amount** into `**deal_size`** on win; manual **edit** until sync exists; header uses **same field** as card detail.

---

## 26 — Past-date appointments stuck in Booked column (Carla Woods)

**Issue:** Lead still appears under **Booked** (`pipeline_stage = booked`) while the linked **appointment is already in the past** (scheduled time passed) and the card does **not** advance to **appointment** / **appointment ran** (or another terminal state). Example called out in audit: **Carla Woods**. **Our side** — missing or late **integration** (e.g. ServiceTitan / calendar sync) plus **Otto** not reliably **reconciling** or **auto-transitioning** stage when `scheduled_start` is past.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Reconcile appointments from ST on a schedule or webhook; optionally **auto-move** leads from **booked** → **appointment** when `scheduled_start` is set and in the future, and flag or advance **past-due** rows so they do not sit in **Booked** indefinitely.

---

## 27 — No “Appointment Not Recorded” stage exists

**Issue:** Pipeline board has **no column / `PipelineStage`** for **“appointment happened (or should have) but was never recorded in Otto / CRM”** — leads get forced into **Booked**, **Appointment**, or other stages instead. **100% Otto** — **product + schema** (`PipelineStage` / board); **Shoonya does not own pipeline stage taxonomy.**

**Shoonya:** Maybe  
**Resolved:** No  
**How:** —  
**Your suggested change:** Add an explicit stage (or flag + filter), migration + API + UI rules for when to use it (e.g. after past `scheduled_start` with no outcome row, or manual rep mark “not recorded”).

---

## 28 — Customer name inconsistency within same lead (Carla Woods / Karla Capichorto)

**Issue:** can't find this bug, maybe already resolved

**Shoonya:** No  
**Resolved:** no  
**How:** —  
**Your suggested change:** —

---

## 29 — Booking status null / “Not Booked” on a Booked-column lead (e.g. Don Ainley)

**Issue:**i think booking status is null becuase for one lead , there are may be 3 conversation , out of which one is actual , and second and third are totally empty records , created by i think service titan , that's why two records are completely empty 

**Shoonya:** NO  
**Resolved:** No  
**How:** —  
**Your suggested change:** Shoonya should **always** return a **non-null `booking_status`** on completed analyses when inferable from the call; align with CRM when booking exists off-call.

---

## 30 — Redundant Booked vs. Appt Scheduled columns

**Issue:** Pipeline board treats **Booked** and **Appointment** (scheduled / “Appt scheduled”) as **separate columns**, but for users they **read as the same job** (“we have a time on the calendar”) — **two stops for one concept**, extra drag moves, and confusion on **where a card should live**. **100% Otto** — **product / UX + `PipelineStage` model**; not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** **Rename** and **sharpen** definitions (e.g. Booked = intent/CSR outcome, Appointment = confirmed slot + rep), **merge** into one column with **sub-status**, or **hide** one column for roles that do not need both.

---

## 31 — Sales Rep stage has zero leads — entire half of pipeline is dead

**Issue:** because leads are moved to sales rep stage manually

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Auto-assign or **require** rep at handoff (Booked → Appointment); backfill `**assigned_rep_id`** from ST / round-robin; hide rep-specific columns until assignment workflow exists.

---

## 32 — Won leads have no underlying data (Pipeline → Outcome)

**Issue:** **probably because its dummy**

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Sync **job/invoice/opportunity** outcome from ST (or source of truth); block or flag **Won** without backing **appointment** / **closed** record.

---

## 33 — Lost column is empty (“impossible”) (Pipeline → Outcome)

**Issue:** **Lost** pipeline column stays **empty** while business expects **some** closed-lost volume — `**pipeline_stage` / `status`** not updated from CRM, filters hide them, or reps never mark lost in Otto. **Integration + product rules**, not transcript AI.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Ingest `**closed_lost`** / lost jobs from ST; allow **manual** lost from pipeline; verify board query includes `**lost`** stage with correct company scope.

---

## 34 — Review column full of empty cards (Pipeline → Outcome)

**Issue:** Many cards in **Review** open to **empty** pipeline detail — same class as Unqualified empties: `**review`** `pipeline_stage` with **no `calls`** or **no usable** linked rows (seed/ST/manual). **Otto data + linking**, not missing Shoonya on a non-existent call.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Do not set `**review`** without a **call** or explicit reason; **migrate** orphan review leads; UI copy when **no conversations**.

---

## 35 — Duplicate Won leads (5 of 8 are duplicates) (Pipeline → Outcome)

**Issue:** **Won** column shows **the same customer / deal multiple times** (e.g. **5 of 8** rows duplicates) — **multiple `leads`** for one contact (see **§22** ST `**st_lead_id`** pattern) or **same lead** surfaced twice in UI. **Otto + ST ingest**, not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Same as **§22**: **one lead per contact** for ST; **dedupe** Won board by `**contact_card_id`** or canonical lead; merge duplicate rows.

---

## 36 — Appointments list: all show “Unassigned” sales rep (Pipeline → Appointments)

**Issue:** List/enriched appointments expose `**assigned_rep_id` / rep name** only when set on the row; **ServiceTitan** `_upsert_appointment` creates appointments **without** `assigned_rep_id` (no technician→Otto user mapping). UI shows **Unassigned** for **null** rep. **Otto + ST integration**, not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Map **ST technician / job resource** to `**users.id`** (`sales_rep` role) on ingest; allow **manual assign** in Otto; default display rule when null.

---

## 37 — Appointments stuck in “Pending” outcome (Pipeline → Appointments)

**Issue:** `appointments.outcome` defaults `**pending`**; ST `**new**` / `**accepted**` map to **pending** in `ST_BOOKING_STATUS_MAP` until `**converted`** / `**dismissed**` — if **re-sync never arrives** or job completes only in ST, rows stay **pending** forever. **Otto mapping + ST sync cadence**, not call AI.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Poll / webhook **job completion**; map more ST statuses; **job-age** rule to flip stale pending; manual **complete / no-show** in app.

---

## 38 — Impossible appointment times (1 AM, 3 AM, etc.) (Pipeline → Appointments)

**Issue:** `**scheduled_start`** wrong wall-clock — typical causes: **UTC vs local** mishandled on display, **bad `start` string** from ST `fromisoformat`, or (historically) using **ingest time** instead of real slot when building appointments. **Otto parse/display + ST payload**; Shoonya does not own `**appointments.scheduled_start`** from ST booking export.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Store **IANA timezone** from ST; render in **company TZ**; validate absurd hours; reject rows missing a real slot (pattern already used for call-created appointments: do not fabricate from `call.created_at`).

---

## 39 — Duplicate appointments (Pipeline → Appointments)

**Issue:** Same booking / customer appears **more than once** — known risk from **double ingest** (e.g. ST **re-exports** + Otto create paths) despite `**st_booking_id`** lookup; or **two IDs** for one job. **Otto dedupe + integration idempotency**, not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Harden **unique** constraint on `**extra_metadata.st_booking_id`** + upsert; merge duplicates in cleanup job.

---

## 40 — Generic locations (“AZ, US”) (Pipeline → Appointments)

**Issue:** `**location_address`** built from **sparse ST address** (`state` / country only) or **contact fallback** when street missing — reads as useless **“AZ, US”**. **Otto string build + ST data quality** (+ geocode fallback if any); Shoonya does not fill appointment list addresses.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Prefer **full structured address** from ST; hide generic-only strings; enrich via **geocode** when only lat/lng or partial.

---

## 41 — Wrong date on every call in Call Logs (e.g. 07/04/2026) (Call Logs)

**Issue:** `**can't find this bug , maybe already resolved`**

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Expose **business date** in **company TZ** (or call-start from recording metadata); document that `**call_received`** is ingest timestamp unless renamed.

---

## 42 — Every call says “No Objection Detected” (Call Logs)

**Issue:** `**get_call_logs`** maps empty `**call_analyses.objections**` (or empty after `**ObjectionClassifier**`) to the **explicit string `None Detected`** (REQ-032 style — see `call_service.py`). **Root empty arrays** usually **upstream analysis (Shoonya)** not extracting objections; **exact label** is **Otto** presentation.

**Shoonya:** Yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** Shoonya: improve **objection extraction** coverage. Otto: show **“No objections in payload”** vs **“Classifier found none”**; optional **re-run** analysis for legacy rows.

---

## 43 — “Qualified + Unbooked + No Objection” feels contradictory (Call Logs)

**Issue:** UI stacks `**lead.status`** tag **“Qualified, unbooked”** with call log **“None Detected”** — looks contradictory but is **not strict logic error** (unbooked does **not** require a spoken objection). **Otto copy / tag composition**; not Shoonya “bug”.

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** Soften copy (“No objections captured”) or **suppress** objection chip when **empty**; explain **unbooked ≠ objection required** in tooltip.

---

## 44 — Every call shows “Not Booked” (Call Logs)

**Issue:** `**zero data in recent calls`** 

**Shoonya:** yes  
**Resolved:** No  
**How:** —  
**Your suggested change:** Otto: if **lead** or **ST** says booked, **backfill** or **overlay** booking on call log row; FE: distinguish **unknown** vs **not_booked**. Shoonya: align `**booking_status`** with CRM when integration provides it.

---

## 45 — Sales Insights: wrong company’s sales reps visible (Sales Insights)

**Issue:** **Sales Insights / team** UI lists **reps that belong to another company** or **wrong roster** for the selected tenant — **P0 if true cross-tenant read**; in this audit track treat as **Otto bug**: `**company_id` scoping**, **session**, **cached org**, or **seed/demo users** leaking into query — **not** Shoonya. *(Separate issue class from **§46–§47** “blank baselines” — that is **empty state vs zeros**, not rep roster.)*

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Audit **all** Sales Insights queries with `**company_id = current_user.company_id`**; add **tests**; remove **global** rep fetches; if ever DB RLS gap, fix **infra**.

---

## 46 — Placeholder data instead of empty state in Team cards (Sales Insights)

**Issue:** **Team** cards show **zeros / blanks** as if they were real **baselines** instead of a clear **“no data yet”** empty state (confusing vs **dummy** demo targets). **Otto product / FE** — not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Use **empty state** copy + **skeleton** until N≥**min sample**; hide **0%** team compare rows; optional **demo** toggle for canned baselines.

---

## 47 — Placeholder / inaccurate Core KPI metrics (Sales Insights)

**Issue:** **Core KPI** tiles show **0**, **dash**, or **static placeholder** values that read as **live** metrics — same class as **§46**: **insufficient data** or **stub pipeline** wired as numbers. **Otto analytics + FE**, not Shoonya.

**Shoonya:** No  
**Resolved:** No  
**How:** —  
**Your suggested change:** Gate KPIs on **data availability**; label **“insufficient sample”**; wire KPIs to **real** `metrics_service` / DB aggregates per **company_id** only.

---

---

