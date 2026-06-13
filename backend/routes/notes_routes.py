from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.agent import (
    _NOTES_TABLE,
    _SUPABASE_KEY,
    _SUPABASE_URL,
    _load_notes,
    _notes_headers,
    _parse_remind_at,
    get_notes,
    mark_note_done,
)
from backend.memory import save_interaction

router = APIRouter()


class NoteCreate(BaseModel):
    note: str
    remind_at: str | None = None  # natural language or ISO — parsed server-side


class NoteUpdate(BaseModel):
    note: str | None = None
    remind_at: str | None = None  # natural language, ISO, or null to clear
    done: bool | None = None


class SnoozeRequest(BaseModel):
    remind_at: str  # natural language or ISO


def _require_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise HTTPException(503, "Notes storage is not configured")


@router.get("/notes/{user_id}")
async def list_notes(user_id: str, include_done: bool = False):
    notes = await _load_notes(user_id)
    if not include_done:
        notes = [n for n in notes if not n.get("done")]
    return {"user_id": user_id, "count": len(notes), "notes": notes}


@router.post("/notes/{user_id}")
async def create_note(user_id: str, body: NoteCreate, background_tasks: BackgroundTasks):
    _require_supabase()
    remind_at_iso = _parse_remind_at(body.remind_at) if body.remind_at else None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_notes_headers(),
            json={"user_id": user_id, "note": body.note, "remind_at": remind_at_iso},
            timeout=10.0,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(500, f"Failed to create note: {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        raise HTTPException(500, "Failed to create note: no row returned")

    background_tasks.add_task(
        save_interaction, user_id, f"Add a note: {body.note}", "Noted — added to your notes."
    )
    return {"note": rows[0]}


@router.patch("/notes/{user_id}/{note_id}")
async def update_note(user_id: str, note_id: str, body: NoteUpdate, background_tasks: BackgroundTasks):
    _require_supabase()
    payload = {}
    if body.note is not None:
        payload["note"] = body.note
    if body.remind_at is not None:
        payload["remind_at"] = _parse_remind_at(body.remind_at) if body.remind_at else None
        payload["channels_sent"] = []
    if body.done is not None:
        payload["done"] = body.done
        payload["done_at"] = datetime.now(timezone.utc).isoformat() if body.done else None
    if not payload:
        raise HTTPException(400, "No fields to update")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_notes_headers(),
            params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
            json=payload,
            timeout=10.0,
        )
    if resp.status_code != 200:
        raise HTTPException(500, f"Failed to update note: {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        raise HTTPException(404, "Note not found")

    if body.done:
        background_tasks.add_task(
            save_interaction, user_id, f"Mark note done: {rows[0]['note']}", "Done — checked that off your notes."
        )
    return {"note": rows[0]}


@router.delete("/notes/{user_id}/{note_id}")
async def delete_note(user_id: str, note_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_notes_headers(),
            params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
            timeout=10.0,
        )
    if resp.status_code != 200:
        raise HTTPException(500, f"Failed to delete note: {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        raise HTTPException(404, "Note not found")
    return {"deleted": True, "id": note_id}


@router.post("/notes/{user_id}/{note_id}/snooze")
async def snooze_note(user_id: str, note_id: str, body: SnoozeRequest):
    _require_supabase()
    remind_at_iso = _parse_remind_at(body.remind_at)
    if not remind_at_iso:
        raise HTTPException(400, f"Could not understand the time: {body.remind_at!r}")

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
        raise HTTPException(500, f"Failed to snooze note: {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        raise HTTPException(404, "Note not found")
    return {"note": rows[0]}


@router.post("/notes/{user_id}/done/{note_id}")
async def complete_note(user_id: str, note_id: str):
    result = await mark_note_done(user_id, note_id)
    return {"result": result}
