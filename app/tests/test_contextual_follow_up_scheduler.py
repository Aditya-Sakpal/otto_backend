"""Unit tests for the scheduled contextual follow-up job (no DB / no LLM).

The job (_contextual_follow_up_job in app.core.scheduler) wires the existing
contextual_follow_up_agent into the scheduler in PROPOSE-ONLY mode. These tests
monkeypatch the agent's orchestrator.run + local-db helpers and the scheduler's
PG session factory, so nothing touches Postgres, SQLite, or Anthropic. We assert:
propose-only settings are forced + the PG session is committed; graceful no-op
when the API key is missing or the feature is disabled; errors are swallowed.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

# The agent package lives under app/agents; make it importable (the job does the
# same insert lazily, but the test patches agent modules directly).
_AGENTS_ROOT = str(Path(__file__).resolve().parents[1] / "agents")
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

import app.core.scheduler as scheduler
from app.core.config import settings as app_settings
from contextual_follow_up_agent.config.settings import settings as fu_settings


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakePgSession:
    """Async-context PG session that records whether commit() was awaited."""
    def __init__(self):
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.committed = True


class _FakeLocalSession:
    """Async-context local (SQLite) session stub."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _patch_common(monkeypatch, *, run_fake):
    """Patch the lazily-imported agent pieces + scheduler PG session factory."""
    import contextual_follow_up_agent.orchestrator as orch
    import contextual_follow_up_agent.db.local as local

    monkeypatch.setattr(orch, "run", run_fake)

    async def _init():
        return None

    async def _get_session():
        return _FakeLocalSession()

    monkeypatch.setattr(local, "init_local_db", _init)
    monkeypatch.setattr(local, "get_local_session", _get_session)

    pg = _FakePgSession()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: pg)
    return pg


def test_job_runs_proposal_only_and_commits(monkeypatch):
    monkeypatch.setattr(app_settings, "CONTEXTUAL_FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(fu_settings, "ANTHROPIC_API_KEY", "test-key")
    # Start from a non-propose-only state to prove the job forces it.
    monkeypatch.setattr(fu_settings, "DRY_RUN", False)
    monkeypatch.setattr(fu_settings, "AUTO_EXECUTE", True)

    captured = {}

    async def _run_fake(*, pg_session, local_session, lead_id_filter):
        captured["lead_id_filter"] = lead_id_filter
        captured["dry_run"] = fu_settings.DRY_RUN
        captured["auto_execute"] = fu_settings.AUTO_EXECUTE
        captured["called"] = True
        return {"processed": 3, "actions_created": 2}

    pg = _patch_common(monkeypatch, run_fake=_run_fake)

    _run(scheduler._contextual_follow_up_job())

    assert captured.get("called") is True
    assert captured["lead_id_filter"] is None
    # Propose-only forced regardless of the starting .env values.
    assert captured["dry_run"] is True
    assert captured["auto_execute"] is False
    assert pg.committed is True


def test_job_noops_without_api_key(monkeypatch):
    monkeypatch.setattr(app_settings, "CONTEXTUAL_FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(fu_settings, "ANTHROPIC_API_KEY", "")

    called = {"v": False}

    async def _run_fake(**_kw):
        called["v"] = True
        return {}

    _patch_common(monkeypatch, run_fake=_run_fake)
    _run(scheduler._contextual_follow_up_job())

    assert called["v"] is False  # graceful no-op, run never invoked


def test_job_noops_when_disabled(monkeypatch):
    monkeypatch.setattr(app_settings, "CONTEXTUAL_FOLLOWUP_ENABLED", False)
    monkeypatch.setattr(fu_settings, "ANTHROPIC_API_KEY", "test-key")

    called = {"v": False}

    async def _run_fake(**_kw):
        called["v"] = True
        return {}

    _patch_common(monkeypatch, run_fake=_run_fake)
    _run(scheduler._contextual_follow_up_job())

    assert called["v"] is False  # disabled → never runs


def test_job_swallows_errors(monkeypatch):
    monkeypatch.setattr(app_settings, "CONTEXTUAL_FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(fu_settings, "ANTHROPIC_API_KEY", "test-key")

    async def _run_fake(**_kw):
        raise RuntimeError("simulated agent failure")

    _patch_common(monkeypatch, run_fake=_run_fake)

    # Must not raise — job logs and returns (non-fatal, like other scheduler jobs).
    _run(scheduler._contextual_follow_up_job())
