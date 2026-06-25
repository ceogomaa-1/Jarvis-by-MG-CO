"""Supabase data access for the OS1 paywall (service-role).

Tables (see supabase/migrations/batch63_os1_paywall.sql):
  os1_subscriptions      — one row per user; source of truth for access + tier
  os1_trial_fingerprints — one-trial-per-identity anti-abuse signals
  os1_leads_usage        — metered Jarvis Leads lookups (Emperor overage)
"""
import os
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── subscriptions ───────────────────────────────────────────────────────────────────────
def get_subscription(user_id: str) -> Optional[dict]:
    sb = _client()
    res = sb.table("os1_subscriptions").select("*").eq("user_id", user_id).maybe_single().execute()
    return res.data if res and res.data else None


def get_by_customer(customer_id: str) -> Optional[dict]:
    sb = _client()
    res = sb.table("os1_subscriptions").select("*").eq("stripe_customer_id", customer_id).maybe_single().execute()
    return res.data if res and res.data else None


def ensure_subscription(user_id: str, email: str = None) -> dict:
    """Return the user's row, creating a default (unsubscribed, NOT grandfathered) one if
    none exists. Absence of a row means a post-cutoff (new) user → must subscribe."""
    row = get_subscription(user_id)
    if row:
        # keep email fresh if we learned it
        if email and not row.get("email"):
            row = upsert_subscription(user_id, {"email": email})
        return row
    return upsert_subscription(user_id, {
        "email": email,
        "active_subscription": False,
        "grandfathered": False,
        "status": "none",
    })


def upsert_subscription(user_id: str, fields: dict) -> dict:
    sb = _client()
    payload = {"user_id": user_id, "updated_at": "now()", **{k: v for k, v in fields.items() if v is not None}}
    sb.table("os1_subscriptions").upsert(payload, on_conflict="user_id").execute()
    return get_subscription(user_id) or payload


# ── trial anti-abuse ────────────────────────────────────────────────────────────────────
def trial_seen(email_normalized: str = None, card_fingerprint: str = None, ip: str = None) -> bool:
    """True if ANY of these identity signals already started a trial before."""
    sb = _client()
    checks = []
    if email_normalized:
        checks.append(("email_normalized", email_normalized))
    if card_fingerprint:
        checks.append(("card_fingerprint", card_fingerprint))
    if ip:
        checks.append(("ip", ip))
    for col, val in checks:
        res = sb.table("os1_trial_fingerprints").select("id").eq(col, val).limit(1).execute()
        if res.data:
            return True
    return False


def record_trial_fingerprint(user_id: str, email_normalized: str = None,
                             card_fingerprint: str = None, ip: str = None) -> None:
    sb = _client()
    sb.table("os1_trial_fingerprints").insert({
        "user_id": user_id,
        "email_normalized": email_normalized,
        "card_fingerprint": card_fingerprint,
        "ip": ip,
    }).execute()


# ── leads metered usage ─────────────────────────────────────────────────────────────────
def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_leads_usage(user_id: str) -> int:
    sb = _client()
    res = (sb.table("os1_leads_usage").select("lookups")
           .eq("user_id", user_id).eq("period", _period()).maybe_single().execute())
    return (res.data or {}).get("lookups", 0) if res and res.data else 0


def add_leads_usage(user_id: str, n: int = 1) -> int:
    current = get_leads_usage(user_id)
    sb = _client()
    sb.table("os1_leads_usage").upsert(
        {"user_id": user_id, "period": _period(), "lookups": current + n, "updated_at": "now()"},
        on_conflict="user_id,period",
    ).execute()
    return current + n
