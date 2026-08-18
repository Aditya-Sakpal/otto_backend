"""
Database URL normalisation and driver connect arguments.

Single place where the async driver is chosen and, for PostgreSQL, where the TLS
policy handed to asyncpg is decided.

Why the TLS policy has to live here
-----------------------------------
SQLAlchemy's asyncpg dialect forwards every unrecognised URL query parameter
straight into ``asyncpg.connect()`` (``opts.update(url.query)`` in
``PGDialect_asyncpg.create_connect_args``). asyncpg has no ``sslmode`` keyword --
it spells it ``ssl`` -- so a libpq-style ``?sslmode=require`` in ``DATABASE_URL``
raises ``TypeError`` instead of turning TLS on, and a URL with no SSL parameter
at all leaves asyncpg on its own default of ``sslmode=prefer``.

``prefer`` is the one that hurts: asyncpg opens a TLS connection first, and if
the server refuses *that* connection it silently retries in plaintext
(``connect_utils._connect_addr``, second attempt). The error surfaced to the
caller then comes from the plaintext attempt::

    no pg_hba.conf entry for host "...", user "...", database "...", no encryption

which names an unencrypted connection the application never intended to make,
hides the encrypted attempt that actually mattered, and would put credentials on
the wire in the clear against any server that did accept it.

Defaulting remote PostgreSQL to ``require`` removes the plaintext fallback, so
the reported error describes the connection the application actually wants.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.engine import URL, make_url

# libpq sslmode values, in the spelling asyncpg's ``ssl`` argument accepts.
SSL_MODES = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)

# Query parameters that describe TLS rather than the connection itself. They are
# stripped from the URL so the dialect cannot forward them to asyncpg.connect().
_SSL_QUERY_KEYS = ("sslmode", "ssl")

# Hosts reachable without leaving the machine, where demanding TLS would break
# local development against a stock PostgreSQL install.
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})

DEFAULT_REMOTE_SSL_MODE = "require"
DEFAULT_LOCAL_SSL_MODE = "prefer"


@dataclass(frozen=True)
class DatabaseTarget:
    """A connection-ready database URL plus the connect args the driver needs."""

    url: str
    connect_args: Dict[str, Any]
    description: str  # credential-free, safe to log
    is_sqlite: bool


def _apply_async_driver(raw_url: str) -> str:
    """Qualify a bare URL with the async driver the app uses for that backend."""
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("sqlite://"):
        return raw_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return raw_url


def _pop_ssl_mode(url: URL) -> Tuple[URL, Optional[str]]:
    """Remove the TLS query parameters from ``url``, returning (url, mode)."""
    query = dict(url.query)
    mode: Optional[str] = None
    for key in _SSL_QUERY_KEYS:
        value = query.pop(key, None)
        if value is None or mode is not None:
            continue
        # SQLAlchemy represents a repeated query parameter as a tuple.
        mode = value if isinstance(value, str) else value[0]
    return url.set(query=query), mode


def _resolve_ssl_mode(requested: Optional[str], host: Optional[str]) -> str:
    """Pick the sslmode to use, falling back to a host-appropriate default."""
    if requested:
        mode = requested.strip().lower().replace("_", "-")
        if mode not in SSL_MODES:
            raise ValueError(
                f"Invalid PostgreSQL SSL mode {requested!r}. Expected one of: "
                f"{', '.join(sorted(SSL_MODES))}."
            )
        return mode

    if (host or "").lower() in _LOCAL_HOSTS:
        return DEFAULT_LOCAL_SSL_MODE
    return DEFAULT_REMOTE_SSL_MODE


def build_database_target(
    raw_url: str,
    *,
    ssl_mode: Optional[str] = None,
) -> DatabaseTarget:
    """
    Turn a raw ``DATABASE_URL`` into an async-driver URL and connect arguments.

    Args:
        raw_url: Connection string as configured in the environment. May carry a
            libpq-style ``?sslmode=`` / ``?ssl=`` parameter, which is translated
            rather than forwarded to the driver.
        ssl_mode: Explicit override (e.g. from ``DB_SSL_MODE``). Wins over any
            mode in the URL. ``None`` or empty falls back to the URL, then to
            ``require`` for remote hosts and ``prefer`` for localhost.

    Returns:
        A DatabaseTarget the caller can hand to ``create_async_engine``.

    Raises:
        ValueError: If the requested SSL mode is not a libpq sslmode value.
    """
    url = make_url(_apply_async_driver(raw_url))

    if url.get_backend_name() == "sqlite":
        return DatabaseTarget(
            url=url.render_as_string(hide_password=False),
            connect_args={"check_same_thread": False},
            description=f"sqlite ({url.database or ':memory:'})",
            is_sqlite=True,
        )

    url, url_ssl_mode = _pop_ssl_mode(url)
    resolved = _resolve_ssl_mode(ssl_mode or url_ssl_mode, url.host)

    return DatabaseTarget(
        url=url.render_as_string(hide_password=False),
        # asyncpg accepts the libpq mode names directly on its ``ssl`` argument.
        connect_args={"ssl": resolved},
        description=(
            f"{url.get_backend_name()}://{url.host or 'localhost'}:"
            f"{url.port or 5432}/{url.database} (sslmode={resolved})"
        ),
        is_sqlite=False,
    )


def connection_failure_hint(error_msg: str, target: DatabaseTarget) -> Optional[str]:
    """
    Explain a driver-level connection failure, or None if it is not a known one.

    Args:
        error_msg: ``str(exception)`` from the failed connection attempt.
        target: The target that was being connected to.

    Returns:
        A multi-line operator-facing hint, or None.
    """
    lowered = error_msg.lower()

    if "no pg_hba.conf entry" in lowered:
        return (
            "PostgreSQL was reached but refused the connection at the pg_hba.conf "
            "stage, meaning no server-side rule matches this client. Check:\n"
            "  1. This service's outbound IP is allow-listed on the database "
            "(on Render, egress IPs are only fixed if a static outbound IP is enabled)\n"
            "  2. The pg_hba.conf rule covers this database and user pair\n"
            "  3. DB_SSL_MODE matches the server: hostssl rules need TLS, and a "
            "server with no TLS support needs DB_SSL_MODE=disable\n"
            f"  Connecting to: {target.description}"
        )

    if "getaddrinfo failed" in lowered or "11001" in error_msg:
        return (
            "Database host could not be resolved. Possible issues:\n"
            "  1. Database server is not running\n"
            "  2. DATABASE_URL is incorrect or points to an unreachable host\n"
            "  3. Network/DNS resolution issue\n"
            f"  Connecting to: {target.description}\n"
            "  For local development, consider SQLite: sqlite+aiosqlite:///./otto.db"
        )

    if "authentication failed" in lowered:
        return (
            "Database authentication failed. Check:\n"
            "  1. Database username and password in DATABASE_URL\n"
            "  2. Database user has proper permissions\n"
            f"  Connecting to: {target.description}"
        )

    if "does not exist" in lowered:
        return (
            "Database does not exist. Create the database first:\n"
            "  For PostgreSQL: CREATE DATABASE your_db_name;\n"
            f"  Connecting to: {target.description}"
        )

    return None
