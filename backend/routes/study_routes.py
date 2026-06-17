"""Study Mode storage (Jarvis Personal).

Fully separate from personal_notes / normal chat history:
  • study_notes — captured notes, categorized, shown in the Study drawer.
  • study_chats — multiple study conversations (new-chat support), messages
    stored as a JSONB array on the chat row.

Uses the Supabase REST API directly with the service-role key (same pattern as
backend/agent.py notes helpers).
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent import _SUPABASE_URL, _SUPABASE_KEY

router = APIRouter()

_NOTES_TABLE = "study_notes"
_CHATS_TABLE = "study_chats"


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _require_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise HTTPException(503, "Study storage is not configured")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Models ───────────────────────────────────────────────────────────────────

class StudyNoteCreate(BaseModel):
    content: str
    category: str | None = None


class StudyNoteUpdate(BaseModel):
    content: str | None = None
    category: str | None = None


class StudyChatCreate(BaseModel):
    title: str | None = None
    messages: list[dict] | None = None


class StudyChatUpdate(BaseModel):
    title: str | None = None
    messages: list[dict] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Study notes
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/study/notes/{user_id}")
async def list_study_notes(user_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_headers(),
            params={"user_id": f"eq.{user_id}", "order": "created_at.desc", "select": "*"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    notes = r.json()
    return {"user_id": user_id, "count": len(notes), "notes": notes}


@router.post("/study/notes/{user_id}")
async def create_study_note(user_id: str, body: StudyNoteCreate):
    _require_supabase()
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(422, "content required")
    row = {
        "user_id": user_id,
        "content": content,
        "category": (body.category or "General").strip() or "General",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_headers(),
            json=row,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"note": r.json()[0]}


@router.patch("/study/notes/{user_id}/{note_id}")
async def update_study_note(user_id: str, note_id: str, body: StudyNoteUpdate):
    _require_supabase()
    patch: dict = {"updated_at": _now()}
    if body.content is not None:
        patch["content"] = body.content.strip()
    if body.category is not None:
        patch["category"] = (body.category.strip() or "General")
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
            json=patch,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    rows = r.json()
    if not rows:
        raise HTTPException(404, "note not found")
    return {"note": rows[0]}


@router.delete("/study/notes/{user_id}/{note_id}")
async def delete_study_note(user_id: str, note_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# Study chats
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/study/chats/{user_id}")
async def list_study_chats(user_id: str):
    """List chats WITHOUT message bodies — for the sidebar."""
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_CHATS_TABLE}",
            headers=_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
                "select": "id,title,created_at,updated_at",
            },
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    chats = r.json()
    return {"user_id": user_id, "count": len(chats), "chats": chats}


@router.get("/study/chats/{user_id}/{chat_id}")
async def get_study_chat(user_id: str, chat_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_CHATS_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{chat_id}", "user_id": f"eq.{user_id}", "select": "*"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    rows = r.json()
    if not rows:
        raise HTTPException(404, "chat not found")
    return {"chat": rows[0]}


@router.post("/study/chats/{user_id}")
async def create_study_chat(user_id: str, body: StudyChatCreate):
    _require_supabase()
    row = {
        "user_id": user_id,
        "title": (body.title or "New chat").strip()[:120] or "New chat",
        "messages": body.messages or [],
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_CHATS_TABLE}",
            headers=_headers(),
            json=row,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"chat": r.json()[0]}


@router.patch("/study/chats/{user_id}/{chat_id}")
async def update_study_chat(user_id: str, chat_id: str, body: StudyChatUpdate):
    _require_supabase()
    patch: dict = {"updated_at": _now()}
    if body.title is not None:
        patch["title"] = body.title.strip()[:120] or "New chat"
    if body.messages is not None:
        patch["messages"] = body.messages
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_CHATS_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{chat_id}", "user_id": f"eq.{user_id}"},
            json=patch,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    rows = r.json()
    if not rows:
        raise HTTPException(404, "chat not found")
    return {"chat": rows[0]}


@router.delete("/study/chats/{user_id}/{chat_id}")
async def delete_study_chat(user_id: str, chat_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/{_CHATS_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{chat_id}", "user_id": f"eq.{user_id}"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"status": "deleted"}
