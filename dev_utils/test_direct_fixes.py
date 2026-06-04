"""Quick validation tests for Otto Direct Fixes (no live server required)."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

# Allow running from backend/
sys.path.insert(0, ".")


def test_pending_actions_response_schema():
    from app.domain.schemas.metrics import PendingActionsResponse

    payload = PendingActionsResponse(
        total_pending=10,
        follow_ups_needed=4,
        calls_to_make=3,
        appointments_to_schedule=2,
        start_date="2026-01-01T00:00:00+00:00",
        end_date="2026-01-31T23:59:59+00:00",
    )
    assert payload.total_pending == 10
    assert payload.follow_ups_needed == 4
    assert payload.calls_to_make == 3
    assert payload.appointments_to_schedule == 2
    print("PASS: PendingActionsResponse schema")


def test_metrics_service_return_keys():
    from app.domain.schemas.metrics import PendingActionsResponse

    service_return = {
        "total_pending": 0,
        "follow_ups_needed": 0,
        "calls_to_make": 0,
        "appointments_to_schedule": 0,
        "start_date": datetime.now(ZoneInfo("UTC")).isoformat(),
        "end_date": datetime.now(ZoneInfo("UTC")).isoformat(),
    }
    PendingActionsResponse(**service_return)
    print("PASS: metrics_service return shape matches schema")


async def test_create_missed_call_pending_action():
    from app.domain.enums import PendingActionStatus
    from app.services.pending_action_service import (
        MISSED_CALL_CALLBACK_MINUTES,
        MISSED_CALL_PRIORITY,
        create_missed_call_pending_action,
    )

    company_id = uuid4()
    call_id = uuid4()
    owner_id = uuid4()
    lead_id = uuid4()
    mock_repo = MagicMock()
    mock_repo.create = AsyncMock(side_effect=lambda pa: pa)

    with patch(
        "app.services.pending_action_service.PendingActionRepository",
        return_value=mock_repo,
    ):
        created = await create_missed_call_pending_action(
            MagicMock(),
            company_id=company_id,
            call_id=call_id,
            phone="+15551234567",
            lead_id=lead_id,
            owner_id=owner_id,
        )

    assert created.action_type == "call_back"
    assert created.status == PendingActionStatus.PENDING
    assert created.due_at is not None
    assert created.priority == MISSED_CALL_PRIORITY
    assert created.owner_id == owner_id
    assert created.lead_id == lead_id
    assert created.source == "manual"
    delta = created.due_at - datetime.now(ZoneInfo("UTC"))
    assert timedelta(minutes=MISSED_CALL_CALLBACK_MINUTES - 1) < delta < timedelta(
        minutes=MISSED_CALL_CALLBACK_MINUTES + 1
    )
    print("PASS: create_missed_call_pending_action defaults")


def test_presign_audio_url_fallback():
    from app.core.s3 import presign_audio_url_for_playback

    assert presign_audio_url_for_playback(None) is None
    url = "https://example.com/recording.mp3"
    with patch("app.core.s3.get_s3_service", return_value=None):
        assert presign_audio_url_for_playback(url) == url
    print("PASS: presign_audio_url_for_playback fallback")


def test_call_summary_item_property_fields():
    from app.domain.schemas.appointment import CallSummaryItem

    item = CallSummaryItem(
        call_id=uuid4(),
        call_type="csr_call",
        call_date=datetime.now(ZoneInfo("UTC")),
        duration_seconds=120,
        audio_url="https://example.com/a.mp3",
        service_requested="Roof replacement",
        property_details={"roof_type": "shingle", "square_footage": 2200},
    )
    assert item.service_requested == "Roof replacement"
    assert item.property_details["roof_type"] == "shingle"
    print("PASS: CallSummaryItem property fields")


def main() -> int:
    failures = 0
    for fn in (
        test_pending_actions_response_schema,
        test_metrics_service_return_keys,
        test_presign_audio_url_fallback,
        test_call_summary_item_property_fields,
    ):
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL: {fn.__name__}: {exc}")

    try:
        asyncio.run(test_create_missed_call_pending_action())
    except Exception as exc:
        failures += 1
        print(f"FAIL: test_create_missed_call_pending_action: {exc}")

    print(f"\n{5 - failures}/5 checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
