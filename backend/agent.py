import os
import re
import traceback
from datetime import datetime, timedelta, timezone

import httpx
import pytz

from backend.utils.user_context import get_user_timezone

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
                "recurrence": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly", "monthly"],
                    "description": "Optional — repeat this reminder after it fires. Defaults to 'none' (one-off).",
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
    {
        "name": "mark_note_done",
        "description": "Mark a note or reminder as done/completed",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "mark_note_undone",
        "description": "Re-open a note that was previously marked done",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "edit_note",
        "description": "Edit a note's text and/or its reminder time. Pass remind_at to set or change the reminder, or an empty string to clear it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
                "note": {"type": "string", "description": "New text for the note (optional)"},
                "remind_at": {
                    "type": "string",
                    "description": "New reminder time in natural language (optional), e.g. 'tomorrow at 9am'. Pass an empty string to clear the reminder.",
                },
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "snooze_note",
        "description": "Snooze a note's reminder to a new time, re-arming it if it already fired",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
                "remind_at": {
                    "type": "string",
                    "description": "New reminder time in natural language, e.g. 'in 1 hour' or 'tomorrow at 9am'",
                },
            },
            "required": ["note_id", "remind_at"],
        },
    },
    {
        "name": "delete_note",
        "description": "Permanently delete a note or reminder",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "set_note_recurrence",
        "description": "Set how often a note's reminder repeats after it fires",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "The id of the note, from get_notes"},
                "recurrence": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly", "monthly"],
                },
            },
            "required": ["note_id", "recurrence"],
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


def _parse_remind_at(text: str, tz_name: str = "UTC") -> str | None:
    """Convert natural language time expressions to an ISO UTC datetime string.

    Relative offsets ("in 5 minutes") are anchored to the current instant.
    Absolute expressions ("tomorrow at 9am", "friday", "5:40pm", etc.) are
    resolved against the user's local timezone (tz_name) so "tomorrow at 9am"
    means 9am in the user's timezone, not UTC.
    """
    text = text.strip().lower()

    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.utc

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    now_naive = now_local.replace(tzinfo=None)

    def _local_to_utc_iso(local_naive: datetime) -> str:
        return tz.localize(local_naive).astimezone(timezone.utc).isoformat()

    # Already an ISO datetime/date — pass through unchanged (naive values are
    # assumed to be in the user's local timezone)
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return _local_to_utc_iso(parsed)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    m = re.match(r"in (\d+) minutes?$", text)
    if m:
        return (now_utc + timedelta(minutes=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) hours?$", text)
    if m:
        return (now_utc + timedelta(hours=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) days?$", text)
    if m:
        return (now_utc + timedelta(days=int(m.group(1)))).isoformat()

    m = re.match(r"in (\d+) weeks?$", text)
    if m:
        return (now_utc + timedelta(weeks=int(m.group(1)))).isoformat()

    # Fixed times of day — "tonight", "this evening", "noon", etc.
    if text in _TIME_OF_DAY:
        hour, minute = _TIME_OF_DAY[text]
        target = now_naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_naive:
            target += timedelta(days=1)
        return _local_to_utc_iso(target)

    if text == "tomorrow":
        target = (now_naive + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return _local_to_utc_iso(target)

    m = re.match(r"tomorrow at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = (now_naive + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return _local_to_utc_iso(target)

    m = re.match(r"today at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = now_naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_naive: target += timedelta(days=1)
        return _local_to_utc_iso(target)

    # Weekday names — "monday", "next monday", "this friday at 3pm"
    m = re.match(
        r"(?:(next|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?$",
        text,
    )
    if m:
        modifier, weekday_name, hour, minute, period = m.groups()
        target_weekday = _WEEKDAYS[weekday_name]
        days_ahead = (target_weekday - now_naive.weekday()) % 7
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

        target = (now_naive + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_naive:
            target += timedelta(days=7)
        return _local_to_utc_iso(target)

    # 24-hour time — "15:30"
    m = re.match(r"(\d{1,2}):(\d{2})$", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now_naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now_naive: target += timedelta(days=1)
            return _local_to_utc_iso(target)

    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        target = now_naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_naive: target += timedelta(days=1)
        return _local_to_utc_iso(target)

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


async def save_note(user_id: str, note: str, remind_at_iso: str | None = None, recurrence: str = "none") -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to save note: notes storage is not configured."
    if recurrence not in ("none", "daily", "weekly", "monthly"):
        recurrence = "none"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                json={
                    "user_id": user_id,
                    "note": note,
                    "remind_at": remind_at_iso,
                    "remind_recurrence": recurrence,
                },
                timeout=10.0,
            )
        if resp.status_code not in (200, 201):
            return f"Failed to save note: {resp.text[:200]}"
        rows = resp.json()
        note_id = rows[0]["id"] if rows else "?"
        result = f"Note saved (id: {note_id}): {note}"
        if remind_at_iso:
            result += f" — reminder set for {remind_at_iso}"
            if recurrence != "none":
                result += f" (repeats {recurrence})"
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
            if n.get("remind_recurrence") and n["remind_recurrence"] != "none":
                line += f" (repeats {n['remind_recurrence']})"
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


async def mark_note_undone(user_id: str, note_id: str) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to re-open note: notes storage is not configured."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json={"done": False, "done_at": None},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to re-open note: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} re-opened."
    except Exception as e:
        return f"Failed to re-open note: {e}"


async def edit_note(
    user_id: str,
    note_id: str,
    note: str | None = None,
    remind_at_iso: str | None = None,
    clear_remind_at: bool = False,
) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to edit note: notes storage is not configured."
    payload: dict = {}
    if note is not None:
        payload["note"] = note
    if clear_remind_at:
        payload["remind_at"] = None
        payload["channels_sent"] = []
    elif remind_at_iso is not None:
        payload["remind_at"] = remind_at_iso
        payload["channels_sent"] = []
    if not payload:
        return "Nothing to update."
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json=payload,
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to edit note: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} updated."
    except Exception as e:
        return f"Failed to edit note: {e}"


async def snooze_note(user_id: str, note_id: str, remind_at_iso: str) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to snooze note: notes storage is not configured."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json={
                    "remind_at": remind_at_iso,
                    "channels_sent": [],
                    "done": False,
                    "done_at": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to snooze note: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} snoozed until {remind_at_iso}."
    except Exception as e:
        return f"Failed to snooze note: {e}"


async def delete_note(user_id: str, note_id: str) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to delete note: notes storage is not configured."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to delete note: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} deleted."
    except Exception as e:
        return f"Failed to delete note: {e}"


async def set_note_recurrence(user_id: str, note_id: str, recurrence: str) -> str:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return "Failed to update recurrence: notes storage is not configured."
    if recurrence not in ("none", "daily", "weekly", "monthly"):
        return f"Invalid recurrence: {recurrence!r}. Use none, daily, weekly, or monthly."
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json={"remind_recurrence": recurrence, "updated_at": datetime.now(timezone.utc).isoformat()},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"Failed to update recurrence: {resp.text[:200]}"
        rows = resp.json()
        if not rows:
            return f"Note {note_id} not found."
        return f"Note {note_id} recurrence set to {recurrence}."
    except Exception as e:
        return f"Failed to update recurrence: {e}"


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
            recurrence = tool_input.get("recurrence", "none")
            remind_at_iso = None
            if remind_at_str:
                tz_name = await get_user_timezone(user_id)
                remind_at_iso = _parse_remind_at(remind_at_str, tz_name)
            return await save_note(user_id, note, remind_at_iso, recurrence)
        elif tool_name == "get_notes":
            return await get_notes(user_id)
        elif tool_name == "mark_note_done":
            return await mark_note_done(user_id, tool_input.get("note_id", ""))
        elif tool_name == "mark_note_undone":
            return await mark_note_undone(user_id, tool_input.get("note_id", ""))
        elif tool_name == "edit_note":
            note_id = tool_input.get("note_id", "")
            new_note = tool_input.get("note")
            remind_at_str = tool_input.get("remind_at")
            clear_remind = remind_at_str == ""
            remind_at_iso = None
            if remind_at_str:
                tz_name = await get_user_timezone(user_id)
                remind_at_iso = _parse_remind_at(remind_at_str, tz_name)
                if remind_at_iso is None:
                    return f"Could not understand the time: {remind_at_str!r}"
            return await edit_note(user_id, note_id, new_note, remind_at_iso, clear_remind)
        elif tool_name == "snooze_note":
            note_id = tool_input.get("note_id", "")
            remind_at_str = tool_input.get("remind_at", "")
            tz_name = await get_user_timezone(user_id)
            remind_at_iso = _parse_remind_at(remind_at_str, tz_name)
            if remind_at_iso is None:
                return f"Could not understand the time: {remind_at_str!r}"
            return await snooze_note(user_id, note_id, remind_at_iso)
        elif tool_name == "delete_note":
            return await delete_note(user_id, tool_input.get("note_id", ""))
        elif tool_name == "set_note_recurrence":
            return await set_note_recurrence(user_id, tool_input.get("note_id", ""), tool_input.get("recurrence", "none"))
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        traceback.print_exc()
        return f"Tool {tool_name} failed: {e}"
