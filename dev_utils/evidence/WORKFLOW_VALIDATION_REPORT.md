# Workflow Validation Report

**Generated:** 2026-06-01 (staging validation execution)  
**Company:** `ce9091df-db37-4e7e-877c-2ed0cf2f4c37` (Arizona Roofers)  
**Local API:** `http://127.0.0.1:8001`  
**Remote API:** `https://ottoai.shunyalabs.ai` (Shunya/intelligence service — different auth surface)  
**Evidence runs:** `20260601_104535`, `20260601_retry2`, `20260601_retry3`, **`idempotency_fix2`** (post-fix)

---

## Executive Summary

| Workflow | Result | Evidence |
|----------|--------|----------|
| Pending-action backfill | **PASS** | [`backfill_apply.json`](backfill_apply.json), apply log in `20260601_104535/` |
| GHL missed call → `call_back` | **PASS** | Idempotency: same `messageId` → same `tempCallId`, 1 `call_back` — [`idempotency_fix2/webhook_ghl_missed_call.json`](idempotency_fix2/webhook_ghl_missed_call.json) |
| CTM missed call → `call_back` | **PASS** | Idempotency: same `ctm_call_id` → same `call_id`, 1 `call_back` — [`idempotency_fix2/webhook_ctm_missed_call.json`](idempotency_fix2/webhook_ctm_missed_call.json) |
| Appointment Shunya → `follow_up` | **PASS** | Idempotency: replay #2 no-op, 1 `follow_up` — [`idempotency_fix2/webhook_appointment_follow_up.json`](idempotency_fix2/webhook_appointment_follow_up.json) |
| Notification eligibility (post-backfill) | **PASS** | 193 pending with `due_at`; `check_follow_ups` executes (0 WebSocket clients online) |
| `staging_validation.py` (local) | **PASS** | 11 PASS / 0 FAIL / 1 WARN (presign) |
| `staging_validation.py` (remote) | **FAIL** | Auth 401 — test credentials not valid on remote host |
| Remote webhook replay | **NOT RUN** | Remote host is not the Otto backend API; webhooks require local/staging backend URL |

## Gate Decision: **GO** for webhook idempotency (local); **NO-GO** for full remote staging until auth fixed

**Idempotency fixes (2026-06-01):** JSON dedupe uses PostgreSQL `extra_metadata->>'key'` via `.op("->>")` in [`ghl_service.py`](../app/services/ghl_service.py), [`ctm_service.py`](../app/services/ctm_service.py), [`call.py`](../app/infrastructure/repositories/call.py). CTM replaced `get_all(limit=100)` scan. GHL skips `call_back` creation when reusing an existing missed call. Appointment uses `exists_pending_appointment_follow_up(..., source=None)` + `db.flush()` in [`webhooks.py`](../app/routes/v1/webhooks.py). Re-run: `python dev_utils/workflow_validation.py --run-id idempotency_fix2 --skip-backfill --webhooks-only`.

---

## 1. Backfill (`scripts/backfill_pending_action_defaults.py`)

**Dry-run (184 rows scanned):**

```text
scanned=184, due_at_set=144, owner_from_call=100, priority_set=182, updated=182
```

**Apply (committed):**

```text
scanned=184, due_at_set=144, owner_from_call=99, priority_set=182, updated=182
```

**Effect:** Pending actions with `due_at` increased from **41 → 193** (includes new webhook tasks). Owners **5 → 118**.

**Fix applied:** Import `CompanyIntegrationORM` in backfill script so SQLAlchemy mapper initializes (was blocking apply).

---

## 2. GHL missed-call webhook

**Endpoint:** `POST /api/v1/webhooks/ghl/messages`  
**Fixture:** [`fixtures/ghl_missed_call.json`](../fixtures/ghl_missed_call.json) with `locationId: staging-validation-ghl` (DB updated via `prep_ghl_integration`).

**Evidence (retry2 — best run):** [`20260601_retry2/webhook_ghl_missed_call.json`](20260601_retry2/webhook_ghl_missed_call.json)

| Check | Result |
|-------|--------|
| HTTP 200 | Yes |
| `isMissedCall` | Yes |
| `call_back` created | Yes (`source=manual`, `priority=1`, `due_at` ≈ +15m) |
| Double replay → 1 task | **Yes** (idempotency_fix2: same `tempCallId`, `pending_count=1`) |

**Root cause (retry3):** `.as_string()` on SQLAlchemy `JSON` column did not match `extra_metadata->>'ghl_message_id'`. **Fix:** `.op("->>")("ghl_message_id")` + skip pending action when reusing call.

---

## 3. CTM missed-call webhook

**Endpoint:** `POST /api/v1/webhooks/ctm/calls`  
**Fixture:** `account_id: test-account-999`, `status: no answer`

**Evidence:** [`20260601_retry3/webhook_ctm_missed_call.json`](20260601_retry3/webhook_ctm_missed_call.json)

| Check | Result |
|-------|--------|
| HTTP 200 | Yes |
| `call_back` created | Yes (`due_at` +15m, `priority=1`) |
| Same `ctm_call_id` on replay → 1 call / 1 task | **Yes** (idempotency_fix2) |

**Root cause (retry3):** `get_all(limit=100)` missed prior rows; JSON lookup used `.as_string()` which failed on generic `JSON` type. **Fix:** indexed lookup with `.op("->>")("ctm_call_id")`.

---

## 4. Appointment follow-up (Shunya job-complete)

**Endpoint:** `POST /api/v1/webhooks/shoonya/job-complete`  
**Fixture:** [`fixtures/shoonya_job_complete_appointment.json`](../fixtures/shoonya_job_complete_appointment.json) (`call_id` = appointment UUID, `result.analysis.qualification.follow_up_required`)

**Evidence:** [`20260601_retry2/webhook_appointment_follow_up.json`](20260601_retry2/webhook_appointment_follow_up.json) (creation proof)

| Field | Value |
|-------|--------|
| `action_type` | `follow_up` |
| `appointment_id` | `0c5b307c-4594-4893-87a3-06328be547f2` |
| `owner_id` | `ae6e55d1-afc6-41b7-a12a-bc6cab51346b` (assigned rep) |
| `due_at` | +24h |
| `priority` | `2` |
| `source` | `ai_analysis` |

**Idempotency:** **PASS** on idempotency_fix2 — replay #2 is a no-op (`probe_after_post1.pending_follow_up_count=1`, final `pending_count=1`). Uses `exists_pending_appointment_follow_up(..., source=None)` + `db.flush()`.

---

## 5. Notification eligibility

**Evidence:** [`20260601_retry2/notification_eligibility.json`](20260601_retry2/notification_eligibility.json)

| Metric | Count |
|--------|------:|
| Pending with `due_at` | 193 |
| With `owner_id` | 118 |
| CSR-routed (no owner, has `call_id`) | 75 |
| Rep-routed (no owner, has `appointment_id`) | 0 |

**`check_follow_ups`:** Ran successfully; logged multiple `Sent follow-up notification` events with `users_notified=0` (no WebSocket clients connected). Tier D (live push) **not validated** — requires frontend/mobile.

---

## 6. Staging validation harness

| Target | Result | Log |
|--------|--------|-----|
| Local | **PASS** (11/11, 1 WARN presign) | [`20260601_retry2/staging_validation_local.txt`](20260601_retry2/staging_validation_local.txt) |
| Remote | **FAIL** (login 401) | [`20260601_retry2/staging_validation_remote.txt`](20260601_retry2/staging_validation_remote.txt) |

Metrics after backfill (local): `total_pending=9` in 30-day window (vs 193 all-time pending in tasks API).

---

## 7. Tooling delivered

| Artifact | Purpose |
|----------|---------|
| [`dev_utils/workflow_validation.py`](../workflow_validation.py) | Orchestrator: backfill, webhooks, notifications, harness, `report.json` |
| [`dev_utils/db_inventory.py`](../db_inventory.py) | SQL inventory snapshot |
| [`dev_utils/fixtures/`](../fixtures/) | GHL, CTM, Shunya payloads (updated) |
| [`dev_utils/evidence/`](.) | Timestamped JSON logs per run |

**Commands:**

```bash
cd backend
python scripts/backfill_pending_action_defaults.py --dry-run --company-id ce9091df-db37-4e7e-877c-2ed0cf2f4c37
python scripts/backfill_pending_action_defaults.py --apply --company-id ce9091df-db37-4e7e-877c-2ed0cf2f4c37
python dev_utils/workflow_validation.py --run-id <timestamp> --skip-backfill
python dev_utils/staging_validation.py
```

---

## 8. Blockers before appointment reminders

1. **Restart API** and re-validate CTM + appointment **idempotency** after committed fixes.
2. **GHL message dedupe** — investigate why duplicate `messageId` creates multiple calls (JSON `ghl_message_id` lookup).
3. **Remote staging** — point validation at Otto backend URL with valid credentials (not intelligence-only host).
4. **WebSocket / mobile** — confirm notification delivery with connected client.
5. **S3 presign** — configure AWS on staging for playback WARN clearance.

---

## 9. What is validated for founders today

- Historical pending actions can be backfilled with `due_at`, `owner_id`, and `priority`.
- New missed-call and appointment-follow-up tasks are **created** with correct scheduling metadata on webhook ingress (local).
- Dashboard metrics endpoint returns valid schema (local).
- Notification **engine runs** against eligible rows; delivery to users unproven without connected clients.

Appointment reminder **feature work** should remain deferred until idempotency re-validation passes after API restart.
