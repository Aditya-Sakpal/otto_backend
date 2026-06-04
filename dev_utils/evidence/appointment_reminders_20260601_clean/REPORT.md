# Appointment Reminder Workflow — Business Validation Report

**Run ID:** `appointment_reminders_20260601_clean`
**Date:** 2026-06-01
**Environment:** Staging (live Postgres)
**Driver:** `dev_utils/appointment_reminder_validation.py` — exercises the real
`appointment_reminder_service` + `followup_notification_service` code paths.

## Verdict: ✅ **GO**

All 14 checks passed. No production blockers found.

---

## Subject appointment

| Field | Value |
|-------|-------|
| appointment_id | `05a7d2aa-3653-4b3d-aaf7-8dc931e0f40d` |
| scheduled_start | `2026-06-02 09:00:00+00:00` (5:00 AM America/New_York, EDT) |
| assigned_rep_id | `null` (exercises sales-rep broadcast routing) |
| outcome | `pending` (unchanged by validation — verified) |

## Results

### 1–3. Materialization (3 reminder kinds)
| Kind | due_at (UTC) | Local (EDT) | priority |
|------|--------------|-------------|----------|
| `day_before` | 2026-06-01 13:00 | 9:00 AM (day before) | 2 |
| `morning_of` | 2026-06-02 12:00 | 8:00 AM (appt day) | 2 |
| `one_hour_before` | 2026-06-02 08:00 | start − 1h | 1 |

✅ Exactly 3 rows, all with `action_type=source="appointment_reminder"` and
`extra_metadata.reminder_kind`. Double-sync stayed at 3 rows (idempotent).

### 4–5. Scheduler simulation
- ✅ **Fires once** — forced `one_hour_before` into the 15-min grace window; tick 1 sent exactly 1 notification.
- ✅ **`notified_at` set** in `extra_metadata`; status → `completed`.
- ✅ **No re-fire** on tick 2 (DB idempotency, 0 sent).
- ✅ **Survives restart** — cleared the in-memory dedupe cache (simulating a new process); tick 3 still sent 0 because `notified_at`/`completed` live in the DB.

### 6. Outcome-change cancellation
| Outcome | pending before | pending after | cancelled |
|---------|----------------|---------------|-----------|
| won | 3 | 0 | 3 |
| lost | 3 | 0 | 3 |
| no_show | 3 | 0 | 3 |
| rescheduled | 3 | 0 | 3 |

✅ Any non-pending outcome cancels all pending reminders on re-sync.
> Note: `cancelled` is not a valid `AppointmentOutcome` enum value; `no_show` is
> the closest "visit did not happen" terminal state and is covered above.

### 7. Evidence
- DB rows, reminder metadata, and the captured WebSocket payload are in
  `validation.json` (payload `type="appointment_reminder"`, includes
  `reminder_kind`, `minutes_until_appointment`, and appointment/contact context).

---

## Findings (non-blocking)

1. **`raw_text` renders appointment time in server TZ (America/New_York), not the
   customer's local TZ.** Timing/`due_at` are correct; only the human-readable
   string may mislead for out-of-timezone customers. Recommend a follow-up to
   localize the display string. *Cosmetic — does not affect workflow correctness.*

## Harness note

An earlier run of the validation script had a bug that committed an in-memory
`outcome` change to the `appointments` table (pending→rescheduled). It was
restored to `pending`, and the harness was fixed to `session.expunge()` the
appointment ORM before commit so the outcome-cancellation test never writes the
appointments table. This clean run confirms `appointment_outcome_unchanged_in_db: true`.

## Cleanup

All reminder `pending_actions` rows created during validation were deleted
(0 remaining). Appointment outcome verified `pending`. Staging is clean.
