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
_MATRIX = {
    "emperor": {
        "leads": True,
        "crm_whitelabel": True,
        "buffer_platform_cap": None,        # unlimited
        "ui_customization": True,           # moving-blocks view + brand customization
        "usage_multiplier": 5,              # 5x Pro
        "message_allowance": None,          # full-tier
    },
    "pro": {
        "leads": False,
        "crm_whitelabel": False,
        "buffer_platform_cap": 2,
        "ui_customization": False,
        "usage_multiplier": 1,
        "message_allowance": None,
    },
    "trial": {
        "leads": False,                     # never any Leads on trial
        "crm_whitelabel": False,
        "buffer_platform_cap": 2,
        "ui_customization": False,
        "usage_multiplier": 1,
        "message_allowance": config.TRIAL_MESSAGE_ALLOWANCE,  # tiny taste
    },
}


def capabilities(sub: dict) -> dict:
    plan = effective_plan(sub)
    caps = dict(_MATRIX.get(plan, {
        "leads": False, "crm_whitelabel": False, "buffer_platform_cap": 0,
        "ui_customization": False, "usage_multiplier": 0, "message_allowance": 0,
    }))
    caps["plan"] = plan
    caps["has_access"] = has_access(sub)
    caps["grandfathered"] = bool(sub and sub.get("grandfathered"))
    caps["trialing"] = is_trialing(sub)
    return caps


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
        return False, "Jarvis Leads is an Emperor-tier feature."
    used = store.get_leads_usage(user_id)
    over = used >= config.EMPEROR_LEADS_ALLOWANCE
    return True, ("overage" if over else "ok")
