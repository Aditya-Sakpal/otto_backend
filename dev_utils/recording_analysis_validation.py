#!/usr/bin/env python3
"""
Recording analysis state-surfacing validation (Phase 1: Fix #1 + Fix #2).

Proves the GET /recordings/{appointment_id}/analysis behaviour change:
  Fix #1 — non-completed recordings surface their actual state (not 404).
  Fix #2 — playback URL is presigned via presign_audio_url_for_playback, never
           the raw private S3 URL.

Exercises the REAL endpoint via TestClient (DB/S3 boundaries stubbed) for the
state cases, and the REAL presign helper against the REAL S3 config for the
playback cases. Produces evidence JSON + GO/NO-GO, mirroring
appointment_reminder_validation.py / rehash_validation.py.

Usage:
    cd backend
    python dev_utils/recording_analysis_validation.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.auth import get_current_user  # noqa: E402
from app.core.dependencies import get_db  # noqa: E402
from app.core.s3 import get_s3_service, presign_audio_url_for_playback  # noqa: E402
import app.routes.v1.recordings as rec  # noqa: E402
from app.domain.enums import UserRole  # noqa: E402

EVIDENCE = Path(__file__).resolve().parent / "evidence"
S3_URL = "https://otto-audio.s3.us-east-1.amazonaws.com/recordings/appt_demo.wav"


def _user():
    return SimpleNamespace(id=uuid4(), role=UserRole.SALES_REP, company_id=uuid4())


async def _db():
    yield None


def _appt(**kw):
    base = dict(
        id=uuid4(), recording_status=None, analysis_status=None, audio_url=None,
        extra_metadata=None, summary=None, key_points=None, action_items=None,
        next_steps=None, objections=None, objection_texts=None,
        objections_total_count=None, qualification_status=None, booking_status=None,
        sentiment_score=None, sop_compliance_score=None, sop_compliance_rate=None,
        sop_stages_completed=None, sop_stages_missed=None, sop_compliance_issues=None,
        sop_compliance_positive_behaviors=None, compliance_target_role=None,
        transcript=None, duration_seconds=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _call_endpoint(client, appt) -> dict:
    """Patch the repo to return `appt`, hit the real endpoint, return JSON."""
    async def fake_get_by_id(self, _id):
        return appt
    orig = rec.AppointmentRepository.get_by_id
    rec.AppointmentRepository.get_by_id = fake_get_by_id
    try:
        r = client.get(f"/api/v1/recordings/{appt.id}/analysis")
        return {"status_code": r.status_code, "body": r.json() if r.content else None}
    finally:
        rec.AppointmentRepository.get_by_id = orig


def run() -> dict:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "s3_configured": get_s3_service() is not None,
        "checks": {},
        "evidence": {},
    }

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    # For the endpoint state cases, use a deterministic presign stub so the
    # assertion is about ROUTING through the helper, not S3 availability.
    orig_presign = rec.presign_audio_url_for_playback
    rec.presign_audio_url_for_playback = lambda url, expiration=14400: (
        f"PRESIGNED::{url}" if url else None
    )

    try:
        with TestClient(app) as client:
            # Case 1 — uploaded
            res = _call_endpoint(client, _appt(recording_status="uploaded", audio_url=S3_URL))
            report["evidence"]["case1_uploaded"] = res
            b = res["body"] or {}
            report["checks"]["case1_uploaded_state"] = (
                res["status_code"] == 200 and b.get("recording_state") == "uploaded"
                and b.get("ready") is False and bool(b.get("failure_reason"))
            )

            # Case 2 — processing
            res = _call_endpoint(client, _appt(recording_status="uploaded", analysis_status="processing"))
            report["evidence"]["case2_processing"] = res
            b = res["body"] or {}
            report["checks"]["case2_processing_state"] = (
                res["status_code"] == 200 and b.get("recording_state") == "processing"
                and b.get("ready") is False and b.get("failure_reason") is None
            )

            # Case 3 — failed + reason
            res = _call_endpoint(client, _appt(
                analysis_status="failed", extra_metadata={"analysis_error": "Shunya timeout"}))
            report["evidence"]["case3_failed"] = res
            b = res["body"] or {}
            report["checks"]["case3_failed_state_and_reason"] = (
                res["status_code"] == 200 and b.get("recording_state") == "failed"
                and b.get("failure_reason") == "Shunya timeout"
            )

            # Case 4 — completed + playback url + analysis
            res = _call_endpoint(client, _appt(
                analysis_status="completed", audio_url=S3_URL,
                summary="Roof inspection done", next_steps=["Send proposal"]))
            report["evidence"]["case4_completed"] = res
            b = res["body"] or {}
            report["checks"]["case4_completed_with_playback"] = (
                res["status_code"] == 200 and b.get("recording_state") == "completed"
                and b.get("ready") is True and b.get("summary") == "Roof inspection done"
                and str(b.get("audio_url", "")).startswith("PRESIGNED::")
            )

            # Regression — missing appointment still 404
            async def none_get(self, _id):
                return None
            orig = rec.AppointmentRepository.get_by_id
            rec.AppointmentRepository.get_by_id = none_get
            try:
                r = client.get(f"/api/v1/recordings/{uuid4()}/analysis")
                report["checks"]["missing_appointment_404"] = r.status_code == 404
            finally:
                rec.AppointmentRepository.get_by_id = orig
    finally:
        rec.presign_audio_url_for_playback = orig_presign
        app.dependency_overrides.clear()

    # Case 5 / 6 — REAL presign helper against REAL S3 config (no stub).
    s3_available = get_s3_service() is not None
    real_out = presign_audio_url_for_playback(S3_URL)
    non_s3_out = presign_audio_url_for_playback("https://cdn.example.com/x.mp3")
    none_out = presign_audio_url_for_playback(None)
    report["evidence"]["case56_presign"] = {
        "s3_available": s3_available,
        "s3_url_in": S3_URL,
        "s3_url_out": real_out,
        "non_s3_url_out": non_s3_out,
        "none_out": none_out,
    }

    if s3_available:
        # Case 5 — private S3 object → a presigned (signed) URL is produced.
        report["checks"]["case5_private_s3_presigned"] = (
            real_out != S3_URL and "X-Amz-Signature" in (real_out or "")
        )
        report["case5_note"] = "S3 configured: live presigned URL generated."
    else:
        # Case 6 — no AWS creds → graceful fallback (original URL, no exception).
        report["checks"]["case6_graceful_fallback"] = real_out == S3_URL
        report["case5_note"] = (
            "S3 NOT configured in this environment — Case 5 (live signed URL) "
            "cannot be demonstrated here; requires S3_AUDIO_BUCKET + AWS creds. "
            "Case 6 (graceful fallback) is demonstrated live instead. The "
            "completed-state routing through the helper is proven by Case 4."
        )

    # Helper invariants that always hold (documents Case 6 fallback contract).
    report["checks"]["presign_passthrough_non_s3"] = non_s3_out == "https://cdn.example.com/x.mp3"
    report["checks"]["presign_none_returns_none"] = none_out is None

    all_passed = all(bool(v) for v in report["checks"].values())
    report["verdict"] = "GO" if all_passed else "NO-GO"
    report["failed_checks"] = [k for k, v in report["checks"].items() if not v]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    report = run()

    out_dir = EVIDENCE / f"recording_analysis_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 64)
    for k, v in report["checks"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\n  s3_configured: {report['s3_configured']}")
    print(f"  note: {report.get('case5_note','')}")
    print(f"\nVERDICT: {report['verdict']}")
    if report["failed_checks"]:
        print(f"FAILED: {report['failed_checks']}")
    print(f"Evidence: {out_dir / 'validation.json'}")
    print("=" * 64)
    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
