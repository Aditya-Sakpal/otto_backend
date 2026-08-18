# Rehash Workflow — Business Validation Report

**Run ID:** `rehash_validation_20260601_rehash3`
**Date:** 2026-06-01
**Environment:** Staging (live Postgres)
**Driver:** `dev_utils/rehash_validation.py` — exercises the real
`rehash_service.scan_and_sync_rehash` + `followup_notification_service` code paths
against a dedicated synthetic lead, scoped by `lead_id` so no real data is touched.

## Verdict: ✅ **GO**

All 15 lifecycle checks passed.

---

## Lifecycle results

| Step | Check | Result |
|------|-------|--------|
| 1 | Lead becomes eligible (qualified_unbooked, 10d stale → single category) | ✅ |
| 2 | Exactly one rehash row created, category `qualified_unbooked`, `owner_id` = assigned rep | ✅ |
| 3 | Notification fires once; payload `type=rehash_opportunity`; `notified_at` set; status → `completed` | ✅ |
| 4 | Re-scan creates **no duplicate** (completed row suppresses); 2nd tick does **not** re-fire | ✅ |
| 5 | Survives simulated process restart (in-memory cache cleared → still 0 sends) | ✅ |
| 6 | Active row exists before lead change | ✅ |
| 7 | Lead booked (ineligible) → episode **closed** (row cancelled), 0 active, stays closed on re-scan | ✅ |

### Evidence (in `validation.json`)
- **Created row:** `action_type=source="rehash"`, `priority=2`, `owner_id`=rep, metadata `{rehash_category, detected_at, rule_version}`.
- **Notification payload:** `type="rehash_opportunity"`, routed to the assigned rep (`target_role=owner`), with `rehash_category`.
- **Final row:** `status="cancelled"` with `notified_at` stamped — proving notify → suppress → episode-close transitions.

---

## Bugs found and fixed during validation

The harness caught **three real defects** before production. All fixed and re-validated GO.

1. **Daily re-notification (over-notification).** The idempotency check only looked
   at `status='pending'`. After a rehash fired (→ `completed`), the next daily scan
   re-created a fresh pending row and re-notified the rep **every day**. 
   **Fix:** suppression now considers `pending` OR `completed` rows
   (`exists_active_rehash`). A fired rehash is suppressed until the lead leaves
   eligibility, at which point `_cancel_ineligible` closes the episode (cancels
   pending + completed) so a genuine future re-eligibility can resurface it.
   *(Policy chosen with product owner: "suppress until lead changes.")*

2. **`asyncpg` parameter type ambiguity.** `:company_id IS NULL OR ...` against a
   uuid column failed with `AmbiguousParameterError` — this would have broken the
   **production daily job** (which passes `company_id=None`). 
   **Fix:** explicit `CAST(:param AS uuid)` in all candidate + cancel queries.

3. **Loop variable shadowing.** `lead_id = cand["lead_id"]` inside the scan loop
   (and again in `_cancel_ineligible`) reassigned the function's scope parameter,
   corrupting `lead_id`-scoped runs after the first row. 
   **Fix:** renamed loop locals (`cand_lead_id`, `row_lead_id`).

A `lead_id` scope parameter was also added to `scan_and_sync_rehash` (single-lead
re-sync), which doubles as the isolation mechanism for this harness.

---

## Non-destructive guarantees (verified post-run)

- Synthetic contact cards remaining: **0**
- Total `rehash` rows in DB: **0** (feature not yet deployed; harness scoped to its own lead)
- No pre-existing lead/appointment/pending_action rows modified (scan filtered by synthetic `lead_id`).

## Notes / not in this validation

- Only the `qualified_unbooked` category was driven end-to-end. `appointment_pending`
  and `stale_lead` share the same code path (same create/notify/suppress/cancel
  logic, only the candidate SQL differs) and their eligibility SQL was separately
  validated by `count_rehash_candidates.py` (205 and 1,870 staging candidates).
- Optional fast-path cancel hooks (appointment outcome / lead status) remain
  **deferred** per instruction — the daily scan handles cancellation correctly.
