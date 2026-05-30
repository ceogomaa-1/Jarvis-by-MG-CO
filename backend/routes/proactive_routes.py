import json
import os
from datetime import datetime, timezone
from pathlib import Path

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

_NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "notes"
_NO_MESSAGE = {"has_message": False, "message": None, "trigger_type": None}


async def _check_due_reminders(user_id: str) -> dict | None:
    """Return a proactive reminder message if any note is past its remind_at time."""
    notes_path = _NOTES_DIR / f"{user_id}_notes.json"
    if not notes_path.exists():
        return None

    try:
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    due_note = None
    for note in notes:
        if note.get("done") or not note.get("remind_at"):
            continue
        try:
            remind_dt = datetime.fromisoformat(note["remind_at"])
            if remind_dt.tzinfo is None:
                remind_dt = remind_dt.replace(tzinfo=timezone.utc)
            if now >= remind_dt:
                due_note = note
                break
        except (ValueError, TypeError):
            continue

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

    # Mark note as done
    for note in notes:
        if note["id"] == due_note["id"]:
            note["done"] = True
    notes_path.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"has_message": True, "message": message, "trigger_type": "reminder"}


@router.get("/proactive/check/{user_id}")
async def check_proactive(user_id: str):
    """Frontend polls this every 5 minutes.
    Checks due reminders first, then pending insights."""

    # 1. Reminders take priority — fire them the moment they're due
    reminder = await _check_due_reminders(user_id)
    if reminder:
        if reminder.get("message"):
            await save_conversation_turn(user_id, "assistant", reminder["message"])
        return reminder

    # 2. Deliver any background-generated insight that's been stored
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
