from datetime import datetime, timezone
from app.main import UTCJSONResponse
from app.core.datetime_utils import isoformat_utc


def test_utc_json_response_renders_datetime_with_offset():
    content = {"now": datetime(2026, 2, 20, 4, 57, 1, tzinfo=timezone.utc)}
    resp = UTCJSONResponse(content)
    body = resp.body.decode("utf-8")
    assert "+00:00" in body or body.endswith("Z"), "Datetime not serialized with UTC offset"


def test_isoformat_utc_naive_and_aware():
    naive = datetime(2026, 2, 20, 4, 57, 1)
    aware = datetime(2026, 2, 20, 4, 57, 1, tzinfo=timezone.utc)
    assert isoformat_utc(naive).endswith("+00:00")
    assert isoformat_utc(aware).endswith("+00:00")

