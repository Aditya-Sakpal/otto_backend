"""
Database credential resolution.

The RDS master password for this instance is managed by AWS Secrets Manager
and rotates automatically (every 7 days). A password baked into DATABASE_URL
therefore expires on its own. This module fetches the current password on
demand and caches it briefly, so a rotation is picked up by new connections
without a redeploy or restart.

Enabled by setting DB_SECRET_ARN. When it is unset the application keeps using
the password embedded in DATABASE_URL, so local development is unaffected.
"""
import json
import os
import threading
import time
from typing import Optional

from sqlalchemy.engine import URL, make_url

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not installed. Managed database credentials unavailable.")


# Short enough that a rotation is picked up quickly, long enough that we are
# not calling Secrets Manager on every new pool connection.
CACHE_TTL_SECONDS = int(os.getenv("DB_SECRET_CACHE_TTL", "60"))

_lock = threading.Lock()
_cached_password: Optional[str] = None
_cached_at: float = 0.0

# Password taken from DATABASE_URL at import time. Used only as a fallback if
# Secrets Manager is unreachable, so a transient AWS failure does not take the
# database down with it.
_fallback_password: Optional[str] = None


def is_enabled() -> bool:
    """Whether the database password should come from Secrets Manager."""
    return bool(settings.DB_SECRET_ARN) and BOTO3_AVAILABLE


def set_fallback_password(password: Optional[str]) -> None:
    """Register the DATABASE_URL password as a fallback credential."""
    global _fallback_password
    _fallback_password = password


def strip_password(url: str) -> str:
    """
    Return url with the password removed.

    Keeps the password out of the engine URL entirely, so it cannot be logged
    or reused after a rotation.
    """
    parsed = make_url(url)
    if parsed.password is None:
        return url

    # URL.set() treats None as "leave unchanged", so the URL is rebuilt instead.
    return URL.create(
        drivername=parsed.drivername,
        username=parsed.username,
        password=None,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
        query=parsed.query,
    ).render_as_string(hide_password=False)


def extract_password(url: str) -> Optional[str]:
    """
    Return the password embedded in url, decoded, if any.

    Parsed with SQLAlchemy rather than urllib: SQLAlchemy renders a URL with the
    password unescaped, so a password containing '#' or '?' makes urlsplit read
    the remainder of the URL as a fragment and report no password at all.
    make_url handles both the escaped form from the environment and the
    unescaped form SQLAlchemy produces, and returns the password decoded.
    """
    return make_url(url).password


def _fetch_from_secrets_manager() -> str:
    client = boto3.client(
        "secretsmanager",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        region_name=settings.AWS_REGION,
    )
    response = client.get_secret_value(SecretId=settings.DB_SECRET_ARN)
    payload = json.loads(response["SecretString"])

    password = payload.get("password")
    if not password:
        raise RuntimeError(
            f"Secret {settings.DB_SECRET_ARN} contains no 'password' field"
        )
    return password


def get_password(force_refresh: bool = False) -> str:
    """
    Return the current database password.

    Served from cache unless the entry has expired or force_refresh is set.
    Falls back to the DATABASE_URL password if Secrets Manager cannot be
    reached and a fallback is available.
    """
    global _cached_password, _cached_at

    with _lock:
        is_fresh = (
            _cached_password is not None
            and not force_refresh
            and (time.monotonic() - _cached_at) < CACHE_TTL_SECONDS
        )
        if is_fresh:
            return _cached_password

        try:
            password = _fetch_from_secrets_manager()
        except Exception as exc:
            if _fallback_password:
                logger.error(
                    "Could not read database password from Secrets Manager (%s: %s). "
                    "Falling back to the DATABASE_URL password.",
                    type(exc).__name__, exc,
                )
                return _fallback_password
            raise

        _cached_password = password
        _cached_at = time.monotonic()
        logger.info(
            "Loaded database password from Secrets Manager (forced refresh: %s)",
            force_refresh,
        )
        return password


def invalidate() -> None:
    """Drop the cached password so the next connection refetches it."""
    global _cached_password, _cached_at

    with _lock:
        was_cached = _cached_password is not None
        _cached_password = None
        _cached_at = 0.0

    if was_cached:
        logger.warning(
            "Discarded cached database password; next connection will refetch it"
        )
