import asyncio
import os
from datetime import datetime, timezone, timedelta

from supabase import create_client

INACTIVITY_THRESHOLD_MINUTES = 15


def _client():
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _get_or_create_active_session_sync(user_id: str) -> dict:
    """
    Return the user's active session. If last message was >15 min ago, close it
    and open a new one. The returned dict always includes 'away_minutes'.
    """
    now = datetime.now(timezone.utc)
    try:
        sb = _client()
        if not sb:
            return _blank_session(now)

        res = (
            sb.table("user_sessions")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if res.data:
            session = res.data[0]
            raw_ts = session["last_message_at"]
            last_msg = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            gap_min = (now - last_msg).total_seconds() / 60

            if gap_min > INACTIVITY_THRESHOLD_MINUTES:
                sb.table("user_sessions").update({"is_active": False}).eq("id", session["id"]).execute()
                new = sb.table("user_sessions").insert({
                    "user_id": user_id,
                    "session_started_at": now.isoformat(),
                    "last_message_at": now.isoformat(),
                    "message_count": 1,
                    "is_active": True,
                }).execute()
                return {**new.data[0], "away_minutes": int(gap_min)}
            else:
                sb.table("user_sessions").update({
                    "last_message_at": now.isoformat(),
                    "message_count": session["message_count"] + 1,
                }).eq("id", session["id"]).execute()
                return {**session, "away_minutes": 0}

        new = sb.table("user_sessions").insert({
            "user_id": user_id,
            "session_started_at": now.isoformat(),
            "last_message_at": now.isoformat(),
            "message_count": 1,
            "is_active": True,
        }).execute()
        return {**new.data[0], "away_minutes": 0}

    except Exception as e:
        print(f"SESSIONS: get_or_create_active_session failed for {user_id}: {e}")
        return _blank_session(now)


async def get_or_create_active_session(user_id: str) -> dict:
    """Async wrapper around the synchronous Supabase session transaction."""
    return await asyncio.to_thread(_get_or_create_active_session_sync, user_id)


def _blank_session(now: datetime) -> dict:
    return {
        "session_started_at": now.isoformat(),
        "last_message_at": now.isoformat(),
        "message_count": 1,
        "away_minutes": 0,
    }


async def format_session_context(user_id: str) -> str:
    """Return session info string to append to the system prompt."""
    session = await get_or_create_active_session(user_id)
    now = datetime.now(timezone.utc)
    raw_start = session.get("session_started_at", now.isoformat())
    started = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
    duration_min = max(0, int((now - started).total_seconds() / 60))
    count = session.get("message_count", 1)

    parts = [f"Current session: {duration_min} min long, {count} messages exchanged."]
    away = session.get("away_minutes", 0)
    if away > INACTIVITY_THRESHOLD_MINUTES:
        parts.append(f"User just returned after being away for {away} minutes.")
    return " ".join(parts)
