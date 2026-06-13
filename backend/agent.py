import os
import re
import traceback
from datetime import datetime, timedelta, timezone

import httpx

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_NOTES_TABLE = "personal_notes"

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

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Fixed times of day — used for bare phrases like "tonight" or "this evening"
_TIME_OF_DAY = {
    "morning": (9, 0), "this morning": (9, 0),
    "afternoon": (15, 0), "this afternoon": (15, 0),
    "evening": (18, 0), "this evening": (18, 0),
    "tonight": (20, 0),
    "noon": (12, 0), "midday": (12, 0),
    "midnight": (0, 0),
}


def _parse_remind_at(text: str) -> str | None:
    """Convert natural language time expressions to ISO datetime string."""
    text = text.strip().lower()
    now = datetime.now(timezone.utc)

    # Already an ISO datetime/date — pass through unchanged
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        pass

    m = re.match(r"in (\d+) minutes?$", text)
    if m:
        return (now + timedelta(minutes=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) hours?$", text)
    if m:
        return (now + timedelta(hours=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) days?$", text)
    if m:
        return (now + timedelta(days=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) weeks?$", text)
    if m:
        return (now + timedelta(weeks=int(m.group(1)))).isoformat()

    # Fixed times of day — "tonight", "this evening", "noon", etc.
    if text in _TIME_OF_DAY:
        hour, minute = _TIME_OF_DAY[text]
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.isoformat()

    if text == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

    m = re.match(r"tomorrow at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    m = re.match(r"today at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now: target += timedelta(days=1)
        return target.isoformat()

    # Weekday names — "monday", "next monday", "this friday at 3pm"
    m = re.match(
        r"(?:(next|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?$",
        text,
    )
    if m:
        modifier, weekday_name, hour, minute, period = m.groups()
        target_weekday = _WEEKDAYS[weekday_name]
        days_ahead = (target_weekday - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7 if modifier == "next" else 0
        elif modifier == "next":
            days_ahead += 7

        if hour is not None:
            hour, minute = int(hour), int(minute or 0)
            if period == "pm" and hour < 12: hour += 12
            elif period == "am" and hour == 12: hour = 0
        else:
            hour, minute = 9, 0

        target = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=7)
        return target.isoformat()

    # 24-hour time — "15:30"
    m = re.match(r"(\d{1,2}):(\d{2})$", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now: target += timedelta(days=1)
            return target.isoformat()

    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
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


def _notes_headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def _load_notes(user_id: str) -> list:
    """Return all notes (active + done) for this user, newest first."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"user_id": f"eq.{user_id}", "order": "created_at.desc"},
                timeout=10.0,
            )
        if resp.status_code != 200:
            print(f"NOTES: load failed ({resp.status_code}): {resp.text[:200]}")
            return []
        return resp.json()
    except Exception as e:
        print(f"NOTES: load error: {e}")
        return []


async def save_note(user_id: str, note: str, remind_at_iso: str | None = None) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to save note: notes storage is not configured."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                json={"user_id": user_id, "note": note, "remind_at": remind_at_iso},
                timeout=10.0,
            )
        if resp.status_code not in (200, 201):
            return f"Failed to save note: {resp.text[:200]}"
        rows = resp.json()
        note_id = rows[0]["id"] if rows else "?"
        result = f"Note saved (id: {note_id}): {note}"
        if remind_at_iso:
            result += f" — reminder set for {remind_at_iso}"
        return result
    except Exception as e:
        return f"Failed to save note: {e}"


async def get_notes(user_id: str) -> str:
    try:
        notes = [n for n in await _load_notes(user_id) if not n.get("done")]
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
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to mark note done: notes storage is not configured."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json={"done": True, "done_at": datetime.now(timezone.utc).isoformat()},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to mark note done: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} marked as done."
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
