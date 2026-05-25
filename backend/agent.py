import json
import re
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

_NOTES_DIR = Path(__file__).resolve().parent.parent / "data" / "notes"

# Anthropic native tool use format
ANTHROPIC_TOOLS = [
    {
        "name": "get_current_datetime",
        "description": "Get the current date and time. Call this whenever the user asks about the current time, date, or day.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for current information",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_note",
        "description": "Save a note or reminder for the user",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "remind_at": {
                    "type": "string",
                    "description": "Optional reminder time in natural language, e.g. 'in 5 minutes' or '5:40pm' or 'tomorrow at 9am'",
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "get_notes",
        "description": "Get all active notes and reminders for the user",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ─── Time parsing ─────────────────────────────────────────────────────────────

def _parse_remind_at(text: str) -> str | None:
    """Convert natural language time expressions to ISO datetime string."""
    text = text.strip().lower()
    now = datetime.now(timezone.utc)

    m = re.match(r"in (\d+) minutes?", text)
    if m:
        return (now + timedelta(minutes=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) hours?", text)
    if m:
        return (now + timedelta(hours=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) days?", text)
    if m:
        return (now + timedelta(days=int(m.group(1)))).isoformat()

    m = re.match(r"tomorrow at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    m = re.match(r"today at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now: target += timedelta(days=1)
        return target.isoformat()

    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now: target += timedelta(days=1)
        return target.isoformat()

    return None


# ─── Tool implementations ──────────────────────────────────────────────────────

async def web_search(query: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            data = r.json()
        parts = []
        if data.get("Answer"):
            parts.append(f"Direct answer: {data['Answer']}")
        if data.get("AbstractText"):
            parts.append(f"Summary: {data['AbstractText']}")
        topics = [t for t in data.get("RelatedTopics", []) if isinstance(t, dict) and t.get("Text")]
        if topics:
            parts.append("Related:\n" + "\n".join(f"- {t['Text']}" for t in topics[:5]))
        if not parts:
            return f"No instant-answer results found for '{query}'."
        return f"Search results for '{query}':\n\n" + "\n\n".join(parts)
    except Exception as e:
        return f"Search failed: {e}"


async def get_current_datetime() -> str:
    return datetime.now(timezone.utc).strftime("%A, %B %d %Y — %I:%M %p")


def _load_notes(user_id: str) -> list:
    path = _NOTES_DIR / f"{user_id}_notes.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_notes(user_id: str, notes: list):
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (_NOTES_DIR / f"{user_id}_notes.json").write_text(
        json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def save_note(user_id: str, note: str, remind_at_iso: str | None = None) -> str:
    try:
        notes = _load_notes(user_id)
        entry = {
            "id": uuid.uuid4().hex[:8],
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "remind_at": remind_at_iso,
            "done": False,
        }
        notes.append(entry)
        _save_notes(user_id, notes)
        result = f"Note saved (id: {entry['id']}): {note}"
        if remind_at_iso:
            result += f" — reminder set for {remind_at_iso}"
        return result
    except Exception as e:
        return f"Failed to save note: {e}"


async def get_notes(user_id: str) -> str:
    try:
        notes = [n for n in _load_notes(user_id) if not n.get("done")]
        if not notes:
            return "No active notes."
        lines = []
        for n in notes:
            line = f"[{n['id']}] {n['note']}"
            if n.get("remind_at"):
                line += f" (remind: {n['remind_at']})"
            lines.append(line)
        return "Active notes:\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to retrieve notes: {e}"


async def mark_note_done(user_id: str, note_id: str) -> str:
    try:
        notes = _load_notes(user_id)
        for n in notes:
            if n["id"] == note_id:
                n["done"] = True
                _save_notes(user_id, notes)
                return f"Note {note_id} marked as done."
        return f"Note {note_id} not found."
    except Exception as e:
        return f"Failed to mark note done: {e}"


# ─── Dispatcher (accepts structured dict input from Anthropic native tool use) ─

async def execute_tool(user_id: str, tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_current_datetime":
            return await get_current_datetime()
        elif tool_name == "web_search":
            return await web_search(tool_input.get("query", ""))
        elif tool_name == "save_note":
            note = tool_input.get("note", "")
            remind_at_str = tool_input.get("remind_at")
            remind_at_iso = _parse_remind_at(remind_at_str) if remind_at_str else None
            return await save_note(user_id, note, remind_at_iso)
        elif tool_name == "get_notes":
            return await get_notes(user_id)
        elif tool_name == "mark_note_done":
            return await mark_note_done(user_id, tool_input.get("note_id", ""))
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        traceback.print_exc()
        return f"Tool {tool_name} failed: {e}"
