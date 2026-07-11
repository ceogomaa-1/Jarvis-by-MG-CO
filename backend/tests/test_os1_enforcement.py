"""OS1 tier-cap ENFORCEMENT tests (batch 64).

Pins the four enforcement points the brief asked for:
  1. Usage window scales by tier — Emperor 5x, Pro/trial base.
  2. Trial is gated by a hard API-COST ceiling (not a message count); a single oversized
     turn can't breach it because output + input are bounded.
  3. Buffer is capped at 2 distinct platforms for Pro; the 3rd is blocked; Emperor unlimited.
  4. Rue Leads stays Emperor-only.

Entitlements are pure functions over a `sub` dict plus a few store reads, so we monkeypatch
the store reads and never touch Supabase.
"""
import pytest

from backend.lib.billing import entitlements, config
from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.model_router import HAIKU


# ── sub-dict builders (match os1_subscriptions rows) ─────────────────────────────────────
def _emperor():
    return {"active_subscription": True, "status": "active", "plan": "emperor"}


def _pro():
    return {"active_subscription": True, "status": "active", "plan": "pro"}


def _trial():
    # trialing status → effective plan 'trial' regardless of the underlying plan id
    return {"active_subscription": True, "status": "trialing", "plan": "pro"}


def _grandfathered():
    return {"grandfathered": True, "active_subscription": True, "status": "grandfathered"}


def _none():
    return {"active_subscription": False, "status": "none"}


# ── 1) Tiered usage window ───────────────────────────────────────────────────────────────
def test_emperor_window_is_5x_pro_is_base():
    assert entitlements.message_limit_multiplier(_emperor()) == 5
    assert entitlements.message_limit_multiplier(_grandfathered()) == 5
    assert entitlements.message_limit_multiplier(_pro()) == 1
    assert entitlements.message_limit_multiplier(_trial()) == 1
    # no-access / unknown never zeroes out — clamps to base
    assert entitlements.message_limit_multiplier(_none()) == 1


def test_effective_message_limit_scales(monkeypatch):
    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _emperor())
    assert entitlements.effective_message_limit("u", 32) == 160
    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _pro())
    assert entitlements.effective_message_limit("u", 32) == 32


# ── 2) Trial COST ceiling ────────────────────────────────────────────────────────────────
def test_trial_cost_status_blocks_at_cap(monkeypatch):
    cap = config.TRIAL_COST_CAP_USD
    # under cap → not exceeded
    monkeypatch.setattr(entitlements.store, "get_trial_cost", lambda uid: cap - 0.5)
    s = entitlements.trial_cost_status("u", _trial())
    assert s["is_trial"] and not s["exceeded"]
    assert s["cap"] == round(cap, 4)
    assert s["remaining"] == pytest.approx(0.5, abs=1e-6)

    # at/over cap → exceeded
    monkeypatch.setattr(entitlements.store, "get_trial_cost", lambda uid: cap)
    assert entitlements.trial_cost_status("u", _trial())["exceeded"] is True

    monkeypatch.setattr(entitlements.store, "get_trial_cost", lambda uid: cap + 1.0)
    blown = entitlements.trial_cost_status("u", _trial())
    assert blown["exceeded"] is True
    assert blown["remaining"] == 0.0


def test_non_trial_has_no_cost_ceiling(monkeypatch):
    monkeypatch.setattr(entitlements.store, "get_trial_cost", lambda uid: 999.0)
    for sub in (_pro(), _emperor(), _grandfathered()):
        s = entitlements.trial_cost_status("u", sub)
        assert s["exceeded"] is False
        assert s["cap"] is None


def test_trial_turn_cost_is_small_and_single_turn_cannot_breach():
    """A trial turn runs on Haiku with output capped at TRIAL_MAX_TOKENS, so the cap buys
    many turns and no single turn (even a huge paste) can blow the ceiling."""
    cap = config.TRIAL_COST_CAP_USD

    # A typical trial turn: small uncached input, big cached prefix, capped output.
    acc = UsageAccumulator(HAIKU)
    acc.add_message_start({"input_tokens": 600, "cache_read_input_tokens": 4000})
    acc.add_round_output(800)
    per_turn = acc.cost()["total_usd"]
    assert per_turn < 0.01                      # cents, not dollars
    assert cap / per_turn > 100                 # generous: hundreds of turns

    # Worst case single turn: input truncated to TRIAL_CONTEXT_CHAR_CAP (~4 chars/token) and
    # output pinned to the trial max. Still nowhere near the cap.
    worst_in = config.TRIAL_CONTEXT_CHAR_CAP // 4
    worst = UsageAccumulator(HAIKU)
    worst.add_message_start({"input_tokens": worst_in, "cache_read_input_tokens": 8000})
    worst.add_round_output(config.TRIAL_MAX_TOKENS)
    assert worst.cost()["total_usd"] < cap

    # Cumulative billing across a simulated trial never exceeds the cap until many turns in.
    used, turns = 0.0, 0
    while used < cap:
        used += per_turn
        turns += 1
    assert turns > 100


# ── 3) Buffer platform cap ───────────────────────────────────────────────────────────────
def test_buffer_pro_blocks_third_platform(monkeypatch):
    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _pro())
    monkeypatch.setattr(entitlements.store, "get_buffer_platforms", lambda uid: {"twitter", "instagram"})

    # Re-posting to an already-used platform → allowed, nothing new to record.
    allowed, reason, rec = entitlements.buffer_platform_check("u", {"twitter"})
    assert allowed and reason is None

    # A 3rd, new platform → blocked with an upgrade prompt.
    allowed, reason, rec = entitlements.buffer_platform_check("u", {"facebook"})
    assert not allowed
    assert "facebook" in reason and "Emperor" in reason


def test_buffer_pro_allows_within_cap(monkeypatch):
    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _pro())
    monkeypatch.setattr(entitlements.store, "get_buffer_platforms", lambda uid: set())
    allowed, reason, rec = entitlements.buffer_platform_check("u", {"twitter", "instagram"})
    assert allowed and reason is None
    assert rec == {"twitter", "instagram"}

    # First post already used the 2 platforms; a single new one is then over the cap.
    monkeypatch.setattr(entitlements.store, "get_buffer_platforms", lambda uid: {"twitter", "instagram"})
    allowed, _, _ = entitlements.buffer_platform_check("u", {"linkedin"})
    assert not allowed


def test_buffer_emperor_unlimited(monkeypatch):
    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _emperor())
    monkeypatch.setattr(entitlements.store, "get_buffer_platforms",
                        lambda uid: {"twitter", "instagram", "facebook"})
    allowed, reason, rec = entitlements.buffer_platform_check("u", {"linkedin", "tiktok", "youtube"})
    assert allowed and reason is None
    assert rec == set()   # unlimited tier records nothing


# ── 4) Leads stays Emperor-only ──────────────────────────────────────────────────────────
def test_leads_emperor_only(monkeypatch):
    monkeypatch.setattr(entitlements.store, "get_leads_usage", lambda uid: 0)

    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _emperor())
    allowed, reason = entitlements.leads_allowed("u")
    assert allowed and reason == "ok"

    monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, **k: _grandfathered())
    assert entitlements.leads_allowed("u")[0] is True

    for sub in (_pro(), _trial(), _none()):
        monkeypatch.setattr(entitlements.store, "ensure_subscription", lambda uid, *a, _s=sub, **k: _s)
        allowed, reason = entitlements.leads_allowed("u")
        assert not allowed
        assert "Emperor" in reason
