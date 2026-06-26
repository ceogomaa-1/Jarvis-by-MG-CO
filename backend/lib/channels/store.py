"""Supabase data access for messaging channels (service-role).

Tables (see supabase/migrations/batch65_os1_channels.sql):
  os1_channel_links        — messaging identity ⇄ OS1 user
  os1_channel_link_codes   — one-time link codes generated in the web app
  os1_channel_messages     — per-link recent conversation history
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import create_client

from backend.lib.billing.store import canonical_user_id
from backend.lib.channels import config

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Unambiguous alphabet for codes (no 0/O/1/I) so they're easy to read & type on a phone.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── links ────────────────────────────────────────────────────────────────────────────────
def get_link(channel: str, channel_user_id: str) -> Optional[dict]:
    sb = _client()
    res = (sb.table("os1_channel_links").select("*")
           .eq("channel", channel).eq("channel_user_id", str(channel_user_id))
           .maybe_single().execute())
    return res.data if res and res.data else None


def list_links_for_user(user_id: str) -> list:
    sb = _client()
    res = (sb.table("os1_channel_links").select("*")
           .eq("user_id", canonical_user_id(user_id)).execute())
    return res.data or []


def create_link(user_id: str, channel: str, channel_user_id: str, username: str = None) -> dict:
    sb = _client()
    payload = {
        "user_id": canonical_user_id(user_id),
        "channel": channel,
        "channel_user_id": str(channel_user_id),
        "channel_username": username,
        "last_seen_at": _now().isoformat(),
    }
    sb.table("os1_channel_links").upsert(payload, on_conflict="channel,channel_user_id").execute()
    return get_link(channel, channel_user_id)


def delete_link(user_id: str, channel: str) -> None:
    sb = _client()
    (sb.table("os1_channel_links").delete()
     .eq("user_id", canonical_user_id(user_id)).eq("channel", channel).execute())


def touch_link(link_id: str) -> None:
    try:
        sb = _client()
        sb.table("os1_channel_links").update({"last_seen_at": _now().isoformat()}).eq("id", link_id).execute()
    except Exception:
        pass


# ── one-time link codes ──────────────────────────────────────────────────────────────────
def create_link_code(user_id: str, channel: str = "telegram") -> dict:
    """Mint a fresh one-time code for this user. Supersedes any prior unused code (we just
    insert a new one; old ones expire on their own)."""
    sb = _client()
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    expires = _now() + timedelta(minutes=config.LINK_CODE_TTL_MINUTES)
    row = {
        "code": code,
        "user_id": canonical_user_id(user_id),
        "channel": channel,
        "expires_at": expires.isoformat(),
    }
    sb.table("os1_channel_link_codes").insert(row).execute()
    return {"code": code, "expires_at": expires.isoformat()}


def redeem_link_code(code: str, channel: str, channel_user_id: str, username: str = None) -> tuple:
    """Redeem a code from a channel DM. Returns (ok, user_id_or_reason).

    Validates: exists, right channel, not expired, not already used. On success, marks the code
    used and creates/updates the identity link."""
    code = (code or "").strip().upper()
    if not code:
        return False, "empty code"
    sb = _client()
    res = sb.table("os1_channel_link_codes").select("*").eq("code", code).maybe_single().execute()
    row = res.data if res and res.data else None
    if not row:
        return False, "not found"
    if row.get("channel") and row["channel"] != channel:
        return False, "wrong channel"
    if row.get("used_at"):
        return False, "already used"
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if _now() > exp:
            return False, "expired"
    except Exception:
        return False, "expired"

    user_id = row["user_id"]
    sb.table("os1_channel_link_codes").update({
        "used_at": _now().isoformat(),
        "channel_user_id": str(channel_user_id),
    }).eq("id", row["id"]).execute()
    create_link(user_id, channel, channel_user_id, username)
    return True, user_id


# ── per-link conversation history ────────────────────────────────────────────────────────
def add_message(link_id: str, role: str, content: str) -> None:
    if not content:
        return
    try:
        sb = _client()
        sb.table("os1_channel_messages").insert({
            "link_id": link_id, "role": role, "content": content[:8000],
        }).execute()
    except Exception as e:
        print(f"[CHANNELS] add_message error: {e}")


def recent_history(link_id: str, turns: int = None) -> list:
    """Return the last ~2*turns messages (user+assistant) oldest-first, as {role, content}."""
    n = (turns or config.HISTORY_TURNS) * 2
    sb = _client()
    res = (sb.table("os1_channel_messages").select("role, content, created_at")
           .eq("link_id", link_id).order("created_at", desc=True).limit(n).execute())
    rows = list(reversed(res.data or []))
    return [{"role": r["role"], "content": r["content"]} for r in rows if r.get("content")]
