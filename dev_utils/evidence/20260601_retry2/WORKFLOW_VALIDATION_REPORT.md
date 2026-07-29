# Workflow Validation Report

**Generated:** 2026-06-01T05:34:02.659829+00:00
**Company:** `ce9091df-db37-4e7e-877c-2ed0cf2f4c37`
**Evidence directory:** `R:\devfuzzion\otto_backend\backend\dev_utils\evidence\20260601_retry2`

## Executive Summary

- **Backfill dry-run:** SKIP
- **Backfill apply:** SKIP
- **GHL missed call + idempotency:** PASS
- **CTM missed call + idempotency:** FAIL
- **Appointment follow-up + idempotency:** FAIL
- **Notification eligibility:** PASS
- **staging_validation local:** PASS
- **staging_validation remote:** FAIL

## Gate Decision: **NO-GO** for appointment reminder implementation

See `report.json` and per-step JSON logs in this directory for full evidence.