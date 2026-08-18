"""Unit tests for RepPhoneRepository.update_push_token upsert (no real DB).

Regression: the old implementation issued a bare UPDATE WHERE is_primary=True and
silently wrote zero rows when the rep had no rep_phones record — leaving every
push token unpersisted. update_push_token is now an upsert: update primary, else
any row, else create one. A fake session captures execute() results and add()s so
we assert the three branches without touching Postgres.
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.orm import configure_mappers

from app.infrastructure.repositories.rep_phone import RepPhoneRepository
from app.infrastructure.database.models.rep_phone import RepPhoneORM
# Register every ORM class so SQLAlchemy can configure RepPhoneORM's mappers
# (which transitively reference CompanyIntegrationORM, not exported by the models
# package __init__) when we instantiate one in the create-branch test.
import app.infrastructure.database.models  # noqa: F401
import app.infrastructure.database.models.company_integration  # noqa: F401

configure_mappers()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Result:
    """Mimics the SQLAlchemy Result returned by session.execute()."""
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeSession:
    """Returns queued rows for successive execute() calls; records add()/flush().

    `rows` is a list, one entry per expected execute() call (the repo issues up to
    two selects before deciding to insert). Each entry is the object that select's
    scalar_one_or_none() should return (or None).
    """
    def __init__(self, rows):
        self._rows = list(rows)
        self.added = []
        self.flushed = 0

    async def execute(self, _query):
        obj = self._rows.pop(0) if self._rows else None
        return _Result(obj)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1


def _repo(session):
    # Bypass BaseRepository.__init__ (only `session` is used by update_push_token).
    repo = RepPhoneRepository.__new__(RepPhoneRepository)
    repo.session = session
    return repo


def test_creates_row_when_none_exists():
    """No primary row and no fallback row → a new RepPhoneORM is created."""
    user_id = uuid4()
    session = _FakeSession(rows=[None, None])  # primary lookup, fallback lookup
    repo = _repo(session)

    affected = _run(repo.update_push_token(user_id, "ExponentPushToken[new]"))

    assert affected == 1
    assert len(session.added) == 1
    created = session.added[0]
    assert isinstance(created, RepPhoneORM)
    assert created.user_id == user_id
    assert created.expo_push_token == "ExponentPushToken[new]"
    assert created.phone_number == ""        # NOT-NULL sentinel
    assert created.is_primary is True
    assert created.is_verified is False
    assert session.flushed == 1


def test_updates_existing_primary_in_place():
    """A primary row is updated in place; no new row is created."""
    user_id = uuid4()
    primary = SimpleNamespace(
        user_id=user_id, is_primary=True, expo_push_token=None, phone_number="+15551234567"
    )
    session = _FakeSession(rows=[primary])  # primary lookup hits immediately
    repo = _repo(session)

    affected = _run(repo.update_push_token(user_id, "ExponentPushToken[upd]"))

    assert affected == 1
    assert primary.expo_push_token == "ExponentPushToken[upd]"
    assert session.added == []               # nothing created
    assert session.flushed == 1


def test_updates_nonprimary_when_no_primary():
    """No primary row, but a non-primary row exists → update it, don't insert."""
    user_id = uuid4()
    nonprimary = SimpleNamespace(
        user_id=user_id, is_primary=False, expo_push_token=None, phone_number="+15559876543"
    )
    # First execute (primary lookup) → None; second (fallback any-row) → nonprimary.
    session = _FakeSession(rows=[None, nonprimary])
    repo = _repo(session)

    affected = _run(repo.update_push_token(user_id, "ExponentPushToken[np]"))

    assert affected == 1
    assert nonprimary.expo_push_token == "ExponentPushToken[np]"
    assert session.added == []
    assert session.flushed == 1
