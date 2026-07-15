import asyncio
import os
import time
from datetime import datetime

import pytz
from supabase import create_client

_PREFERENCE_CACHE: dict[str, tuple[float, dict]] = {}
_PREFERENCE_CACHE_TTL_SECONDS = 300


def _client():
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _get_user_preferences_sync(user_id: str) -> dict:
    cached = _PREFERENCE_CACHE.get(user_id)
    now = time.monotonic()
    if cached and now - cached[0] < _PREFERENCE_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        sb = _client()
        if not sb:
            return {}
        res = (
            sb.table("user_preferences")
            .select("timezone,preferred_name")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        data = res.data or {}
        _PREFERENCE_CACHE[user_id] = (now, data)
        return data
    except Exception:
        return {}


async def _get_user_preferences(user_id: str) -> dict:
    # supabase-py is synchronous; never block FastAPI's event loop with it.
    cached = _PREFERENCE_CACHE.get(user_id)
    if cached and time.monotonic() - cached[0] < _PREFERENCE_CACHE_TTL_SECONDS:
        return cached[1]
    return await asyncio.to_thread(_get_user_preferences_sync, user_id)


async def get_user_timezone(user_id: str) -> str:
    """Return the user's IANA timezone from user_preferences, defaulting to America/Toronto."""
    data = await _get_user_preferences(user_id)
    return data.get("timezone") or "America/Toronto"


async def get_user_preferred_name(user_id: str) -> str | None:
    """Return the user's preferred name from user_preferences, or None if not set."""
    data = await _get_user_preferences(user_id)
    return data.get("preferred_name") or None


async def format_user_time_context(user_id: str) -> str:
    """Return a time string for the system prompt in the user's local timezone."""
    # One cached query supplies both values; the previous implementation made
    # two sequential Supabase round-trips on every message.
    preferences = await _get_user_preferences(user_id)
    tz_name = preferences.get("timezone") or "America/Toronto"
    now = datetime.now(pytz.timezone(tz_name))
    time_str = f"User's current local time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({tz_name})"
    preferred_name = preferences.get("preferred_name")
    if preferred_name:
        time_str += f"\nUSER PREFERRED NAME: {preferred_name}. Address them by this name naturally in conversation."
    return time_str
