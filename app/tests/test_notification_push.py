"""Unit tests for Expo push dispatch in FollowUpNotificationService (no DB/network).

The service's _send_push and _push_title are exercised with stubbed rep-phone repo
and Expo client, so we assert push behavior without touching the DB or Expo.
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.followup_notification_service import FollowUpNotificationService


def _svc():
    # Bypass __init__ (which builds repos from a session); set only what we test.
    svc = FollowUpNotificationService.__new__(FollowUpNotificationService)
    svc.db = None
    return svc


class _RepRepo:
    """Stub: maps user_id → token (or None for missing)."""
    def __init__(self, tokens):
        self._tokens = tokens

    async def get_by_user(self, uid):
        tok = self._tokens.get(uid)
        if tok is None:
            return None
        return SimpleNamespace(expo_push_token=tok)


class _Expo:
    def __init__(self, raise_err=False):
        self.calls = []
        self._raise = raise_err

    async def send_push(self, *, expo_push_token, title, body, data=None):
        if self._raise:
            raise RuntimeError("Expo unavailable (simulated)")
        self.calls.append({"token": expo_push_token, "title": title, "body": body, "data": data})
        return {"status": "ok"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── push attempted for each workflow type (Cases 1-5) ────────────────────
@pytest.mark.parametrize("ntype,expected_title", [
    ("appointment_reminder", "Appointment reminder"),
    ("rehash_opportunity", "Re-engagement opportunity"),
    ("follow_up_reminder", "Task reminder"),   # covers callback / follow-up / post-meeting
])
def test_push_attempted_per_type(ntype, expected_title):
    svc = _svc()
    uid = uuid4()
    svc._rep_phone_repo = _RepRepo({uid: "ExponentPushToken[abc]"})
    svc._expo_push = _Expo()
    notif = {"type": ntype, "pending_action_id": "p1", "appointment_id": "a1", "lead_id": "l1"}

    attempted = _run(svc._send_push([uid], notif, message="Do the thing"))

    assert attempted == 1
    assert len(svc._expo_push.calls) == 1
    call = svc._expo_push.calls[0]
    assert call["title"] == expected_title
    assert call["body"] == "Do the thing"
    assert call["token"] == "ExponentPushToken[abc]"
    assert call["data"]["type"] == ntype


def test_callback_and_post_meeting_use_followup_title():
    # callback + post-meeting tasks are follow_up_reminder type → "Task reminder"
    assert FollowUpNotificationService._push_title({"type": "follow_up_reminder"}) == "Task reminder"


# ── Case 6: missing token → skipped, no push attempted ───────────────────
def test_missing_token_skips_gracefully():
    svc = _svc()
    uid = uuid4()
    svc._rep_phone_repo = _RepRepo({uid: None})  # no token
    svc._expo_push = _Expo()
    attempted = _run(svc._send_push([uid], {"type": "follow_up_reminder"}, "x"))
    assert attempted == 0
    assert svc._expo_push.calls == []


def test_mixed_tokens_only_attempts_present():
    svc = _svc()
    u1, u2 = uuid4(), uuid4()
    svc._rep_phone_repo = _RepRepo({u1: "ExponentPushToken[x]", u2: None})
    svc._expo_push = _Expo()
    attempted = _run(svc._send_push([u1, u2], {"type": "follow_up_reminder"}, "x"))
    assert attempted == 1


# ── Case 7: Expo error is isolated (does not raise) ──────────────────────
def test_expo_failure_does_not_raise():
    svc = _svc()
    uid = uuid4()
    svc._rep_phone_repo = _RepRepo({uid: "ExponentPushToken[x]"})
    svc._expo_push = _Expo(raise_err=True)
    # Must not raise; returns 0 attempts that succeeded-without-error path.
    attempted = _run(svc._send_push([uid], {"type": "follow_up_reminder"}, "x"))
    assert attempted == 0  # the dispatch raised and was swallowed


# ── Case 8: push uses the SAME recipient list (routing unchanged) ────────
def test_push_uses_same_user_ids():
    svc = _svc()
    u1, u2, u3 = uuid4(), uuid4(), uuid4()
    svc._rep_phone_repo = _RepRepo({u1: "ExponentPushToken[1]", u2: "ExponentPushToken[2]", u3: "ExponentPushToken[3]"})
    svc._expo_push = _Expo()
    _run(svc._send_push([u1, u2, u3], {"type": "rehash_opportunity"}, "x"))
    tokens = {c["token"] for c in svc._expo_push.calls}
    assert tokens == {"ExponentPushToken[1]", "ExponentPushToken[2]", "ExponentPushToken[3]"}


def test_empty_recipients_no_push():
    svc = _svc()
    svc._rep_phone_repo = _RepRepo({})
    svc._expo_push = _Expo()
    attempted = _run(svc._send_push([], {"type": "follow_up_reminder"}, "x"))
    assert attempted == 0
