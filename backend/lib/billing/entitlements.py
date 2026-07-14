"""Tier → capabilities. Single source of truth for server-side feature gating.

Effective plan:
  grandfathered            → 'emperor' (legacy users keep full access; nothing they use breaks)
  active paid 'emperor'    → 'emperor'
  active paid 'pro'        → 'pro'
  trialing                 → 'trial'  (tiny taste, NOT a full tier)
  otherwise                → None     (no access → pricing screen)

Capability matrix (Leads = Emperor only; white-label CRM = Emperor; Buffer 2-platform cap on
Pro vs unlimited on Emperor; customizable UI/moving-blocks = Emperor; usage = Emperor 5x Pro).
Flags exist for features not built yet — they're no-ops until those features read them.
"""
from . import config, store


def has_access(sub: dict) -> bool:
    """Does this user get INTO OS1 at all?"""
    if not sub:
        return False
    if sub.get("grandfathered"):
        return True
    return bool(sub.get("active_subscription"))


def is_trialing(sub: dict) -> bool:
    return bool(sub) and (sub.get("status") == "trialing")


def effective_plan(sub: dict) -> str:
    """Returns 'emperor' | 'pro' | 'trial' | None."""
    if not sub:
        return None
    if sub.get("grandfathered"):
        return "emperor"
    if not sub.get("active_subscription"):
        return None
    if is_trialing(sub):
        return "trial"
    plan = (sub.get("plan") or "").lower()
    return plan if plan in ("pro", "emperor") else "pro"


# capability matrix keyed by effective plan
#   usage_multiplier   scales the rolling message window (Pro = base, Emperor = 5x)
#   buffer_platform_cap max distinct Buffer platforms a user may post to (None = unlimited)
#   trial_cost_cap     hard cumulative API-cost ceiling for the trial taste (None = no cap)
_MATRIX = {
    "emperor": {
        "leads": True,
        "crm_whitelabel": True,
        "buffer_platform_cap": None,        # unlimited
        "ui_customization": True,           # moving-blocks view + brand customization
        "usage_multiplier": 5,              # 5x Pro
        "message_allowance": None,          # full-tier
        "trial_cost_cap": None,
        "autonomous_runs_monthly": config.EMPEROR_AUTONOMOUS_RUNS_MONTHLY,
    },
    "pro": {
        "leads": False,
        "crm_whitelabel": False,
        "buffer_platform_cap": 2,
        "ui_customization": False,
        "usage_multiplier": 1,
        "message_allowance": None,
        "trial_cost_cap": None,
        "autonomous_runs_monthly": config.PRO_AUTONOMOUS_RUNS_MONTHLY,
    },
    "trial": {
        "leads": False,                     # never any Leads on trial
        "crm_whitelabel": False,
        "buffer_platform_cap": 2,
        "ui_customization": False,
        "usage_multiplier": 1,
        "message_allowance": config.TRIAL_MESSAGE_ALLOWANCE,  # legacy (no longer gates)
        "trial_cost_cap": config.TRIAL_COST_CAP_USD,          # the real gate
        "autonomous_runs_monthly": 0,
    },
}


def capabilities(sub: dict) -> dict:
    plan = effective_plan(sub)
    caps = dict(_MATRIX.get(plan, {
        "leads": False, "crm_whitelabel": False, "buffer_platform_cap": 0,
        "ui_customization": False, "usage_multiplier": 0, "message_allowance": 0,
        "trial_cost_cap": None,
        "autonomous_runs_monthly": 0,
    }))
    caps["plan"] = plan
    caps["has_access"] = has_access(sub)
    caps["grandfathered"] = bool(sub and sub.get("grandfathered"))
    caps["trialing"] = is_trialing(sub)
    return caps


# ── Usage window multiplier (Pro = base, Emperor = 5x) ───────────────────────────────────
def message_limit_multiplier(sub: dict) -> int:
    """How many times the BASE rolling-window message ceiling this plan gets.

    Emperor (and grandfathered → emperor) = 5x; Pro/trial = base. Unknown/no-access plans
    fall back to 1x rather than 0 so we never accidentally zero out a user who slipped past
    the access gate — access is enforced separately by has_access()."""
    mult = capabilities(sub).get("usage_multiplier") or 0
    return mult if mult >= 1 else 1


def effective_message_limit(user_id: str, base_limit: int) -> int:
    sub = store.ensure_subscription(user_id)
    return base_limit * message_limit_multiplier(sub)


def for_user(user_id: str, email: str = None) -> dict:
    """Convenience: load (and lazily create) the row, return capabilities."""
    sub = store.ensure_subscription(user_id, email)
    return capabilities(sub)


# ── Leads gating (the one with real cash cost) ──────────────────────────────────────────
def leads_allowed(user_id: str) -> tuple:
    """Returns (allowed, reason). Emperor only, and within/over the metered allowance.

    Over-allowance is still allowed (it's billed as overage) but flagged so the caller can
    note it. Non-Emperor → blocked outright.
    """
    sub = store.ensure_subscription(user_id)
    caps = capabilities(sub)
    if not caps.get("leads"):
        return False, "Rue Leads is an Emperor-tier feature."
    used = store.get_leads_usage(user_id)
    over = used >= config.EMPEROR_LEADS_ALLOWANCE
    return True, ("overage" if over else "ok")


# ── Trial cost ceiling (the gate that replaces the message-count taste) ──────────────────
def trial_cost_status(user_id: str, sub: dict = None) -> dict:
    """Report a trial user's budget. Returns:

      { is_trial, cap, used, remaining, exceeded }

    For non-trial plans cap is None and exceeded is always False (no ceiling applies)."""
    sub = sub or store.ensure_subscription(user_id)
    caps = capabilities(sub)
    cap = caps.get("trial_cost_cap")
    is_trial = caps.get("plan") == "trial"
    if not is_trial or cap is None:
        return {"is_trial": is_trial, "cap": cap, "used": 0.0, "remaining": None, "exceeded": False}
    used = store.get_trial_cost(user_id)
    return {
        "is_trial": True,
        "cap": round(float(cap), 4),
        "used": round(used, 6),
        "remaining": round(max(float(cap) - used, 0.0), 6),
        "exceeded": used >= float(cap),
    }


# ── Buffer platform cap (Pro = 2 distinct platforms, Emperor = unlimited) ────────────────
def buffer_platform_check(user_id: str, target_services) -> tuple:
    """Decide whether this user may post to `target_services` (a set of Buffer service names).

    First-come-first-served: the first `cap` distinct platforms a user posts to become their
    allowed set; a post that would push the distinct count past the cap is blocked.

    Returns (allowed: bool, reason: str | None, services_to_record: set). On allow, the caller
    should record `services_to_record` so the user's platform set grows. Emperor (cap None) is
    always allowed and records nothing (no point tracking the unlimited tier)."""
    targets = {str(s).lower() for s in (target_services or []) if s}
    sub = store.ensure_subscription(user_id)
    cap = capabilities(sub).get("buffer_platform_cap")

    if cap is None:                       # Emperor / unlimited
        return True, None, set()
    if not targets:                       # nothing resolvable to gate on → fail open
        return True, None, set()

    existing = store.get_buffer_platforms(user_id)
    combined = existing | targets
    if len(combined) <= cap:
        return True, None, targets

    overflow = sorted(s for s in targets if s not in existing)
    using = sorted(existing) or ["none yet"]
    reason = (
        f"Your plan includes {cap} social platforms (you're using: {', '.join(using)}). "
        f"Posting to {', '.join(overflow)} would exceed that. "
        "Upgrade to Emperor to post to unlimited platforms."
    )
    return False, reason, set()
