"""
Regression tests for the fixed-window message limit (usage_limits.py).

Guards the exact bug that was burning API credits: the limit must HOLD once hit
and only reset when the 4-hour window genuinely elapses — not "any moment" later.
Also pins the owner-id admin exemption (unlimited).
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend import usage_limits as ul


# ── Minimal in-memory stand-in for the supabase client call chains used by
#    usage_limits: table().select().eq().limit().execute(), .insert(), .update().eq()
class _Result:
    def __init__(self, data):
        self.data = data


class _Tbl:
    def __init__(self, store):
        self.store = store
        self._filters = {}
        self._mode = None
        self._payload = None

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def insert(self, payload):
        self._mode, self._payload = "insert", payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, n):
        return self

    def execute(self):
        if self._mode == "select":
            rows = [r for r in self.store.values()
                    if all(r.get(c) == v for c, v in self._filters.items())]
            return _Result(rows[:1])
        if self._mode == "insert":
            rid = str(len(self.store) + 1)
            row = dict(self._payload, id=rid)
            self.store[rid] = row
            return _Result([row])
        if self._mode == "update":
            for r in self.store.values():
                if all(r.get(c) == v for c, v in self._filters.items()):
                    r.update(self._payload)
            return _Result([])
        return _Result([])


class _FakeSB:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _Tbl(self.store)


def _freeze(monkeypatch, when):
    monkeypatch.setattr(ul, "_now_utc", lambda: when)


def test_limit_holds_after_32_and_reports_real_wait(monkeypatch):
    sb = _FakeSB()
    uid = "regular_user_1"
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    _freeze(monkeypatch, t0)

    for i in range(ul.DAILY_MESSAGE_LIMIT):
        allowed, _ = ul.check_limit(uid, sb)
        assert allowed, f"message {i+1} should be allowed"
        ul.increment_usage(uid, sb)

    # 33rd message must be blocked — the bug was this resetting instantly.
    allowed, info = ul.check_limit(uid, sb)
    assert not allowed
    assert info["used"] == ul.DAILY_MESSAGE_LIMIT
    assert info["remaining"] == 0
    # A real wait close to the full 4h window — never empty / "any moment".
    assert info["resets_in"] and info["resets_in"] != "any moment"


def test_window_fully_resets_after_4h(monkeypatch):
    sb = _FakeSB()
    uid = "regular_user_2"
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    _freeze(monkeypatch, t0)
    for _ in range(ul.DAILY_MESSAGE_LIMIT):
        ul.increment_usage(uid, sb)
    assert not ul.check_limit(uid, sb)[0]

    # Just before the window ends → still blocked.
    _freeze(monkeypatch, t0 + timedelta(minutes=ul.WINDOW_MINUTES - 1))
    assert not ul.check_limit(uid, sb)[0]

    # After the window elapses → full reset, all messages available again.
    _freeze(monkeypatch, t0 + timedelta(minutes=ul.WINDOW_MINUTES + 1))
    allowed, info = ul.check_limit(uid, sb)
    assert allowed
    assert info["used"] == 0
    assert info["remaining"] == ul.DAILY_MESSAGE_LIMIT


def test_owner_id_is_unlimited():
    sb = _FakeSB()
    owner = "3363afdc-9bca-4b88-893c-f535c62a6687"
    assert ul.is_admin(owner)
    for _ in range(100):
        allowed, info = ul.check_limit(owner, sb)
        assert allowed
        assert info["is_admin"] is True
        ul.increment_usage(owner, sb)


def test_owner_id_business_form_is_unlimited():
    assert ul.is_admin("user_3363afdc9bca4b88893cf535c62a6687")


def test_window_is_four_hours():
    assert ul.WINDOW_MINUTES == 240
    assert ul.DAILY_MESSAGE_LIMIT == 32
    assert ul._window_label() == "4 hours"
