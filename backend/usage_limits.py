"""
Rolling message window for Jarvis (Personal + Business).

Each user gets DAILY_MESSAGE_LIMIT messages per WINDOW_MINUTES rolling window.
As each message ages past WINDOW_MINUTES, that slot frees up automatically.
Max wait is always WINDOW_MINUTES — no timezone dependency.
"""

import json
import os
from datetime import datetime, timedelta, timezone

# ========== CONFIGURATION ==========
DAILY_MESSAGE_LIMIT = 32          # messages per rolling window
WINDOW_MINUTES = 90               # 1.5 hours rolling window

# Admin user IDs — unlimited, no cap, no counter shown
ADMIN_USER_IDS: set[str] = set(
    uid.strip()
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
)

# Admin emails as fallback (checked against Supabase auth when needed)
ADMIN_EMAILS: set[str] = {
    e.strip()
    for e in os.getenv("ADMIN_EMAILS", "gomaawork04@gmail.com").split(",")
    if e.strip()
}


def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_USER_IDS


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _window_start() -> datetime:
    """Messages sent before this timestamp no longer count."""
    return _now_utc() - timedelta(minutes=WINDOW_MINUTES)


def _get_window_timestamps(user_id: str, supabase) -> list[datetime]:
    """
    Fetch all message timestamps for this user within the rolling window.
    Returns list of UTC datetimes, newest first.
    """
    window_start = _window_start()

    try:
        result = (
            supabase.table("business_daily_usage")
            .select("message_timestamps")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            return []

        raw = result.data[0].get("message_timestamps") or "[]"
        if isinstance(raw, str):
            timestamps_raw = json.loads(raw)
        else:
            timestamps_raw = raw  # already parsed by driver

        active: list[datetime] = []
        for ts in timestamps_raw:
            try:
                dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
                if dt >= window_start:
                    active.append(dt)
            except Exception:
                pass

        return sorted(active, reverse=True)  # newest first

    except Exception as e:
        print(f"[USAGE] Error fetching timestamps for {user_id}: {e}")
        return []


def _get_reset_in_display(oldest_ts: datetime) -> str:
    """Return how long until the oldest active slot frees up."""
    frees_at = oldest_ts + timedelta(minutes=WINDOW_MINUTES)
    diff = frees_at - _now_utc()

    if diff.total_seconds() <= 0:
        return "any moment"

    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def get_usage(user_id: str, supabase) -> dict:
    """
    Get current rolling window usage.
    Returns: { used, limit, remaining, is_admin, resets_in, window_minutes }
    """
    if is_admin(user_id):
        return {
            "used": 0,
            "limit": -1,
            "remaining": -1,
            "is_admin": True,
            "resets_in": "",
            "window_minutes": WINDOW_MINUTES,
        }

    active_timestamps = _get_window_timestamps(user_id, supabase)
    used = len(active_timestamps)
    remaining = max(0, DAILY_MESSAGE_LIMIT - used)

    resets_in = ""
    if used >= DAILY_MESSAGE_LIMIT and active_timestamps:
        oldest = min(active_timestamps)
        resets_in = _get_reset_in_display(oldest)

    return {
        "used": used,
        "limit": DAILY_MESSAGE_LIMIT,
        "remaining": remaining,
        "is_admin": False,
        "resets_in": resets_in,
        "window_minutes": WINDOW_MINUTES,
    }


def check_limit(user_id: str, supabase) -> tuple:
    """
    Check if user can send a message.
    Returns: (allowed: bool, usage_info: dict)
    """
    usage = get_usage(user_id, supabase)
    if usage["is_admin"]:
        return True, usage
    return usage["remaining"] > 0, usage


def increment_usage(user_id: str, supabase) -> dict:
    """
    Record a new message timestamp. Prunes expired timestamps to keep the array lean.
    """
    if is_admin(user_id):
        return get_usage(user_id, supabase)

    now = _now_utc()
    window_start = _window_start()

    try:
        result = (
            supabase.table("business_daily_usage")
            .select("id, message_timestamps")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if result.data:
            row = result.data[0]
            raw = row.get("message_timestamps") or "[]"
            existing = json.loads(raw) if isinstance(raw, str) else raw

            # Prune expired + append new
            active = [
                ts for ts in existing
                if datetime.fromisoformat(ts).replace(tzinfo=timezone.utc) >= window_start
            ]
            active.append(now.isoformat())

            supabase.table("business_daily_usage").update({
                "message_timestamps": json.dumps(active),
                "message_count": len(active),
                "updated_at": now.isoformat(),
            }).eq("id", row["id"]).execute()

        else:
            supabase.table("business_daily_usage").insert({
                "user_id": user_id,
                "usage_date": now.date().isoformat(),
                "message_count": 1,
                "message_timestamps": json.dumps([now.isoformat()]),
            }).execute()

    except Exception as e:
        print(f"[USAGE] Error incrementing usage for {user_id}: {e}")

    return get_usage(user_id, supabase)
