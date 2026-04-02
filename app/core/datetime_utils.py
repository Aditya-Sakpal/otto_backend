from datetime import datetime, timezone
from typing import Optional


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure the given datetime is timezone-aware in UTC.
    - If dt is None -> returns None
    - If dt.tzinfo is None (naive) -> assume UTC and attach tzinfo
    - Otherwise convert to UTC
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Return an ISO 8601 string in UTC (with +00:00) for the provided datetime,
    or None if input is None.
    """
    d = ensure_utc(dt)
    return d.isoformat() if d is not None else None

