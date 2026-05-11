import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from backend.llm import jarvis_think
from backend.triggers import get_pending_proactive_message, mark_proactive_delivered

router = APIRouter()

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

    now = datetime.now()
    due_note = None
    for note in notes:
        if note.get("done") or not note.get("remind_at"):
            continue
        try:
            if now >= datetime.fromisoformat(note["remind_at"]):
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
        return reminder

    # 2. Deliver any background-generated insight that's been stored
    pending = await get_pending_proactive_message(user_id)
    if not pending:
        return _NO_MESSAGE

    await mark_proactive_delivered(user_id)
    return {
        "has_message": True,
        "message": pending["message"],
        "trigger_type": pending["trigger_type"],
    }
