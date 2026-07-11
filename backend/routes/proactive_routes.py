import os

import httpx
from fastapi import APIRouter

from backend.conversation import save_conversation_turn

router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@router.get("/proactive/{user_id}")
async def get_proactive_messages(user_id: str):
    """Return unread proactive messages (daily check-ins, fired reminders) and mark them read.
    Polled once on login/page load."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return {"messages": []}
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/proactive_messages",
            headers=headers,
            params={
                "user_id": f"eq.{user_id}",
                "read": "eq.false",
                "order": "created_at.desc",
                "limit": 3,
            },
            timeout=10.0,
        )
    messages = resp.json() if resp.status_code == 200 else []

    if messages:
        ids = ",".join(str(m["id"]) for m in messages)
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{_SUPABASE_URL}/rest/v1/proactive_messages",
                headers=headers,
                params={"id": f"in.({ids})"},
                json={"read": True},
                timeout=10.0,
            )

    return {"messages": [m["message"] for m in messages]}


_NO_MESSAGE = {"has_message": False, "message": None, "trigger_type": None}


async def _next_unread_message(user_id: str) -> dict | None:
    """Return the oldest unread `proactive_messages` row for this user, marking
    it read so it's delivered exactly once.

    Rue only ever writes to `proactive_messages` for two reasons:
    - a fired reminder (type=note_reminder — the notes cron dispatcher's
      "inapp" channel)
    - the once-daily check-in (type=morning_briefing)
    Both are handled identically here: oldest unread, mark read, deliver."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/proactive_messages",
            headers=headers,
            params={
                "user_id": f"eq.{user_id}",
                "read": "eq.false",
                "order": "created_at.asc",
                "limit": 1,
            },
            timeout=10.0,
        )
    if resp.status_code != 200:
        return None
    rows = resp.json()
    if not rows:
        return None

    row = rows[0]
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{_SUPABASE_URL}/rest/v1/proactive_messages",
            headers={**headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{row['id']}"},
            json={"read": True},
            timeout=10.0,
        )

    return {"has_message": True, "message": row["message"], "trigger_type": row.get("type") or "proactive"}


@router.get("/proactive/check/{user_id}")
async def check_proactive(user_id: str):
    """Frontend polls this every ~10s. Returns at most one unread proactive
    message (a fired reminder or the daily check-in), marks it read, and
    persists it to the conversation so it doesn't vanish on reload. Never
    raises — any internal error is swallowed and returns has_message: false."""
    try:
        unread = await _next_unread_message(user_id)
        if not unread:
            return _NO_MESSAGE
        if unread.get("message"):
            await save_conversation_turn(user_id, "assistant", unread["message"])
        return unread
    except Exception as e:
        print(f"PROACTIVE: check_proactive failed for {user_id}: {e}")
        return _NO_MESSAGE
