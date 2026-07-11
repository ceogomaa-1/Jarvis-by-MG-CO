"""Tests for the OS1 messaging-channel layer (batch 65).

Covers the gating that matters: unlinked users are prompted to link (never get free Rue),
link codes redeem, an inactive subscriber is told to reactivate, a linked subscriber's message
runs an OS1 turn, and channel turns are metered/short-circuited exactly like the web app
(tier usage limit + trial cost ceiling). Store + network are monkeypatched — no Supabase, no
Anthropic.
"""
import asyncio

import backend.routes.channels as ch
import backend.lib.channels.agent as agent


def _run(coro):
    return asyncio.run(coro)


class _Capture:
    def __init__(self):
        self.sent = []
        self.added = []

    async def send(self, to, text):
        self.sent.append((to, text))

    async def extract(self, message):
        return []

    async def typing(self, to):
        pass


# ── code parsing ─────────────────────────────────────────────────────────────────────────
def test_extract_code():
    assert ch._extract_code("/start ABC23456") == "ABC23456"
    assert ch._extract_code("abc23def") == "ABC23DEF"      # bare code, upper-cased
    assert ch._extract_code("/start") == ""
    assert ch._extract_code("hello there how are you") == ""


# ── unlinked DMs never get free Rue ───────────────────────────────────────────────────
def test_unlinked_is_prompted_to_link(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: None)
    cap = _Capture()
    _run(ch._handle_inbound("telegram", 111, "joe", "tell me a joke", {},
                            cap.send, cap.extract))
    assert len(cap.sent) == 1
    assert "link your OS1 account" in cap.sent[0][1].lower() or "link" in cap.sent[0][1].lower()
    assert "jarvismgco.com/os1" in cap.sent[0][1]


def test_unlinked_redeems_valid_code(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: None)
    monkeypatch.setattr(ch.store, "redeem_link_code", lambda code, channel, cuid, user: (True, "user_abc"))
    cap = _Capture()
    _run(ch._handle_inbound("telegram", 111, "joe", "ABC23456", {}, cap.send, cap.extract))
    assert "Linked" in cap.sent[0][1]


def test_unlinked_bad_code_via_start_is_rejected(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: None)
    monkeypatch.setattr(ch.store, "redeem_link_code", lambda *a, **k: (False, "expired"))
    cap = _Capture()
    # Explicit /start <code> (e.g. from a stale deep link) → tell them it failed.
    _run(ch._handle_inbound("telegram", 111, "joe", "/start ZZZ99999", {}, cap.send, cap.extract))
    assert "invalid or expired" in cap.sent[0][1]


def test_unlinked_bare_wordlike_code_falls_through_to_prompt(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: None)
    monkeypatch.setattr(ch.store, "redeem_link_code", lambda *a, **k: (False, "not found"))
    cap = _Capture()
    # A random 6-10 letter word that isn't a real code shouldn't be accused — guide to link.
    _run(ch._handle_inbound("telegram", 111, "joe", "Rue", {}, cap.send, cap.extract))
    assert "jarvismgco.com/os1" in cap.sent[0][1]


# ── linked-but-inactive subscriber ───────────────────────────────────────────────────────
def test_linked_inactive_told_to_reactivate(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: {"id": "L1", "user_id": "user_abc"})
    monkeypatch.setattr(ch.billing_store, "ensure_subscription",
                        lambda uid, *a, **k: {"active_subscription": False, "status": "canceled"})
    cap = _Capture()
    _run(ch._handle_inbound("telegram", 111, "joe", "hi", {}, cap.send, cap.extract))
    assert cap.sent[0][1] == ch.INACTIVE_TEXT


# ── linked subscriber runs an OS1 turn ───────────────────────────────────────────────────
def test_linked_subscriber_runs_turn(monkeypatch):
    monkeypatch.setattr(ch.store, "get_link", lambda *a, **k: {"id": "L1", "user_id": "user_abc"})
    monkeypatch.setattr(ch.billing_store, "ensure_subscription",
                        lambda uid, *a, **k: {"grandfathered": True, "active_subscription": True})
    monkeypatch.setattr(ch.store, "touch_link", lambda *a, **k: None)
    monkeypatch.setattr(ch.store, "recent_history", lambda *a, **k: [])
    added = []
    monkeypatch.setattr(ch.store, "add_message", lambda link_id, role, content: added.append((role, content)))

    async def fake_turn(user_id, text, attachments, history):
        assert user_id == "user_abc"
        return {"ok": True, "kind": "reply", "reply": "Here's your answer."}
    monkeypatch.setattr(ch, "run_channel_turn", fake_turn)

    cap = _Capture()
    _run(ch._handle_inbound("telegram", 111, "joe", "what's my revenue?", {},
                            cap.send, cap.extract, cap.typing))
    assert cap.sent[-1][1] == "Here's your answer."
    # both the user message and the assistant reply are persisted to channel history
    assert ("user", "what's my revenue?") in added
    assert ("assistant", "Here's your answer.") in added


# ── metering: same tier caps as the web app ──────────────────────────────────────────────
def test_turn_blocked_when_trial_cost_exceeded(monkeypatch):
    monkeypatch.setattr(agent.entitlements, "for_user",
                        lambda uid, *a, **k: {"plan": "trial", "usage_multiplier": 1})
    monkeypatch.setattr(agent.entitlements, "trial_cost_status",
                        lambda uid, *a, **k: {"exceeded": True})
    out = _run(agent.run_channel_turn("user_abc", "hello", [], []))
    assert out["kind"] == "trial_limit"
    assert "trial limit is reached" in out["reply"]


def test_turn_blocked_when_usage_limit_hit(monkeypatch):
    monkeypatch.setattr(agent.entitlements, "for_user",
                        lambda uid, *a, **k: {"plan": "pro", "usage_multiplier": 1})
    monkeypatch.setattr(agent, "_supabase", lambda: object())
    monkeypatch.setattr(agent, "check_limit",
                        lambda uid, sb, limit: (False, {"limit": limit, "window_label": "4 hours", "resets_in": "2h"}))
    out = _run(agent.run_channel_turn("user_abc", "hello", [], []))
    assert out["kind"] == "limit"
    assert "hit your limit" in out["reply"]
