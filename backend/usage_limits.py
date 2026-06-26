"""
Fixed message window for Jarvis (Personal + Business).

Each user gets DAILY_MESSAGE_LIMIT messages per FIXED WINDOW_MINUTES window.
The window is anchored at the user's first message in the window. Once the user
hits the limit, they are blocked until that window fully elapses — and then the
whole allowance resets at once. (A previous rolling-window design let the oldest
message expire within seconds of hitting the cap, so the limit appeared to reset
instantly and never actually held — this fixed window prevents that.)
"""

import json
import os
from datetime import datetime, timedelta, timezone

# ========== CONFIGURATION ==========
DAILY_MESSAGE_LIMIT = 32          # messages per fixed window
WINDOW_MINUTES = 240              # 4-hour fixed window (fully resets when it elapses)

# Owner / admin user IDs — unlimited, no cap, no counter shown. The owner's Supabase
# user id is included in BOTH the raw (dashed) and business ("user_" + hex) forms so
# the exemption holds regardless of which product / id format is in play. Additional
# ids can still be supplied via the ADMIN_USER_IDS env var (comma-separated).
_DEFAULT_ADMIN_IDS: set[str] = {
    "3363afdc-9bca-4b88-893c-f535c62a6687",
    "user_3363afdc9bca4b88893cf535c62a6687",
}
ADMIN_USER_IDS: set[str] = _DEFAULT_ADMIN_IDS | set(
    uid.strip()
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
)


def _window_label() -> str:
    """Human-friendly window size for limit messages (e.g. '4 hours')."""
    if WINDOW_MINUTES % 60 == 0:
        hours = WINDOW_MINUTES // 60
        return f"{hours} hour" + ("s" if hours != 1 else "")
    return f"{WINDOW_MINUTES} minutes"

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


def _parse_timestamps(raw) -> list[datetime]:
    """Parse the stored message_timestamps blob into a list of UTC datetimes."""
    timestamps_raw = json.loads(raw) if isinstance(raw, str) else (raw or [])
    parsed: list[datetime] = []
    for ts in timestamps_raw:
        try:
            parsed.append(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc))
        except Exception:
            pass
    return parsed


def _get_window_timestamps(user_id: str, supabase) -> list[datetime]:
    """
    Return this user's message timestamps for the CURRENT fixed window, newest first.

    The window is anchored at the earliest stored message. If WINDOW_MINUTES have
    elapsed since that anchor, the window is over and the count fully resets (returns
    []). Otherwise every stored timestamp counts toward the current window.
    """
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

        parsed = _parse_timestamps(result.data[0].get("message_timestamps") or "[]")
        if not parsed:
            return []

        anchor = min(parsed)
        # Fixed window: once the 4h window from the first message has elapsed, the
        # allowance resets entirely.
        if _now_utc() >= anchor + timedelta(minutes=WINDOW_MINUTES):
            return []

        return sorted(parsed, reverse=True)  # newest first

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


def get_usage(user_id: str, supabase, limit: int | None = None) -> dict:
    """
    Get current rolling window usage.
    Returns: { used, limit, remaining, is_admin, resets_in, window_minutes }

    `limit` overrides the base DAILY_MESSAGE_LIMIT — used by the OS1 Business path to apply
    the per-tier usage multiplier (Emperor = 5x). Defaults to the base limit (Personal path,
    unchanged).
    """
    effective_limit = DAILY_MESSAGE_LIMIT if limit is None else limit
    if is_admin(user_id):
        return {
            "used": 0,
            "limit": -1,
            "remaining": -1,
            "is_admin": True,
            "resets_in": "",
            "window_minutes": WINDOW_MINUTES,
            "window_label": _window_label(),
        }

    active_timestamps = _get_window_timestamps(user_id, supabase)
    used = len(active_timestamps)
    remaining = max(0, effective_limit - used)

    resets_in = ""
    if used >= effective_limit and active_timestamps:
        # Anchor = first message of the window; the allowance resets WINDOW_MINUTES later.
        anchor = min(active_timestamps)
        resets_in = _get_reset_in_display(anchor)

    return {
        "used": used,
        "limit": effective_limit,
        "remaining": remaining,
        "is_admin": False,
        "resets_in": resets_in,
        "window_minutes": WINDOW_MINUTES,
        "window_label": _window_label(),
    }


def check_limit(user_id: str, supabase, limit: int | None = None) -> tuple:
    """
    Check if user can send a message.
    Returns: (allowed: bool, usage_info: dict)
    """
    usage = get_usage(user_id, supabase, limit=limit)
    if usage["is_admin"]:
        return True, usage
    return usage["remaining"] > 0, usage


def increment_usage(user_id: str, supabase, limit: int | None = None) -> dict:
    """
    Record a new message timestamp. Prunes expired timestamps to keep the array lean.
    """
    if is_admin(user_id):
        return get_usage(user_id, supabase, limit=limit)

    now = _now_utc()

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
            parsed = _parse_timestamps(row.get("message_timestamps") or "[]")

            # Fixed window: keep the existing timestamps only while we're still inside
            # the current window (anchored at the earliest message). Once the window has
            # elapsed, start a fresh window containing just this message.
            if parsed and now < min(parsed) + timedelta(minutes=WINDOW_MINUTES):
                active = [dt.isoformat() for dt in parsed]
            else:
                active = []
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

    return get_usage(user_id, supabase, limit=limit)
