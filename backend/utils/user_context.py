import os
from datetime import datetime

import pytz
from supabase import create_client


def _client():
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


async def get_user_timezone(user_id: str) -> str:
    """Return the user's IANA timezone from user_preferences, defaulting to America/Toronto."""
    try:
        sb = _client()
        if not sb:
            return "America/Toronto"
        res = (
            sb.table("user_preferences")
            .select("timezone")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if res.data and res.data.get("timezone"):
            return res.data["timezone"]
    except Exception:
        pass
    return "America/Toronto"


async def format_user_time_context(user_id: str) -> str:
    """Return a time string for the system prompt in the user's local timezone."""
    tz_name = await get_user_timezone(user_id)
    now = datetime.now(pytz.timezone(tz_name))
    return f"User's current local time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({tz_name})"
