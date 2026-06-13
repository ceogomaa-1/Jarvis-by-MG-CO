import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from backend.llm import jarvis_think
from backend.triggers import get_pending_proactive_message, mark_proactive_delivered
from backend.conversation import save_conversation_turn

router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@router.get("/proactive/{user_id}")
async def get_proactive_messages(user_id: str):
    """Return unread proactive messages (morning briefings, etc.) and mark them read."""
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


async def _check_unread_proactive_messages(user_id: str) -> dict | None:
    """Return the oldest unread row from `proactive_messages` (morning
    briefings, and the "inapp" channel's `note_reminder` rows written by the
    cron dispatcher), marking it read.

    Without this, those rows only ever surfaced via GET /api/proactive/{user_id}
    on page load — so a reminder that fired while the app was open didn't show
    up until the user reloaded. Folding the check into this polled endpoint
    makes them appear live."""
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


async def _check_due_reminders(user_id: str) -> dict | None:
    """Return a proactive reminder message if any note is past its remind_at time
    and hasn't been surfaced in chat yet ("chat" not in channels_sent)."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None

    now = datetime.now(timezone.utc)
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/personal_notes",
            headers=headers,
            params={
                "user_id": f"eq.{user_id}",
                "done": "eq.false",
                "remind_at": f"lte.{now.isoformat()}",
                "order": "remind_at.asc",
                "limit": 10,
            },
            timeout=10.0,
        )
    if resp.status_code != 200:
        return None

    notes = resp.json()
    due_note = next((n for n in notes if "chat" not in (n.get("channels_sent") or [])), None)
    if not due_note:
        return None

    # Generate a natural reminder message via Jarvis
    system_override = (
        f"The user set a reminder and it's now due.\n"
        f"The reminder is: \"{due_note['note']}\"\n"
        f"Set at: {due_note['created_at']}\n"
        f"Due at: {due_note['remind_at']}\n\n"
        "Surface this reminder naturally — like a person who remembered something important "
        "for them would. Don't say 'Your reminder is due.' Just bring it up the way a present, "
        "engaged person would. Keep it to one sentence, two max. "
        "Do not start with Hey or any greeting."
    )

    message = await jarvis_think(
        user_message="[Reminder due]",
        conversation_history=[],
        system_override=system_override,
    )

    # Mark the "chat" channel as delivered — note stays active until the user marks it done
    channels_sent = (due_note.get("channels_sent") or []) + ["chat"]
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{_SUPABASE_URL}/rest/v1/personal_notes",
            headers={**headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{due_note['id']}"},
            json={"channels_sent": channels_sent},
            timeout=10.0,
        )

    return {"has_message": True, "message": message, "trigger_type": "reminder"}


@router.get("/proactive/check/{user_id}")
async def check_proactive(user_id: str):
    """Frontend polls this every ~10s.
    Checks due reminders first, then unread proactive_messages (cron-fired
    "inapp" reminders, morning briefings), then pending insights."""

    # 1. Reminders take priority — fire them the moment they're due
    reminder = await _check_due_reminders(user_id)
    if reminder:
        if reminder.get("message"):
            await save_conversation_turn(user_id, "assistant", reminder["message"])
        return reminder

    # 2. Surface unread proactive_messages rows live (e.g. the cron
    # dispatcher's "inapp" channel insert) instead of waiting for next reload
    unread = await _check_unread_proactive_messages(user_id)
    if unread:
        return unread

    # 3. Deliver any background-generated insight that's been stored
    pending = await get_pending_proactive_message(user_id)
    if not pending:
        return _NO_MESSAGE

    await mark_proactive_delivered(user_id)
    if pending.get("message"):
        await save_conversation_turn(user_id, "assistant", pending["message"])
    return {
        "has_message": True,
        "message": pending["message"],
        "trigger_type": pending["trigger_type"],
    }
