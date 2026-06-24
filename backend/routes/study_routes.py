"""Study Mode storage (Jarvis Personal).

Fully separate from personal_notes / normal chat history:
  • study_notes — captured notes, categorized, shown in the Study drawer.
  • study_chats — multiple study conversations (new-chat support), messages
    stored as a JSONB array on the chat row.

Uses the Supabase REST API directly with the service-role key (same pattern as
backend/agent.py notes helpers).
"""

import json
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent import _SUPABASE_URL, _SUPABASE_KEY

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostics — one hit answers "why didn't Study Mode use Grok?"
# GET /api/study/diag
#   • If this 404s, the new provider code is NOT deployed (stale Render build).
#   • Reports the live env flag, whether the Grok key is present, what the resolver
#     decides, and a REAL 1-token live call to xAI so an invalid key is obvious.
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/study/diag")
async def study_diagnostics():
    out: dict = {"provider_code_deployed": True}  # reaching here proves the import chain loaded

    try:
        from backend.lib.providers.study_provider import grok_configured, resolve_study_provider
        from backend.lib.providers.grok import GROK_BASE_URL, GROK_MODEL
    except Exception as e:
        return {"provider_code_deployed": False, "import_error": str(e)}

    # Prove the cost-optimization build is present too (caching/tiering live in these).
    try:
        from backend.lib.business.cost import UsageAccumulator  # noqa: F401
        from backend.lib.business.model_router import select_personal_model  # noqa: F401
        out["cost_optimization_code_deployed"] = True
    except Exception as e:
        out["cost_optimization_code_deployed"] = False
        out["cost_import_error"] = str(e)

    env_val = os.getenv("STUDY_MODE_PROVIDER", "(unset)")
    out["env_STUDY_MODE_PROVIDER"] = env_val
    out["grok_key_present"] = grok_configured()
    out["grok_model"] = GROK_MODEL
    out["grok_base_url"] = GROK_BASE_URL
    # What a normal Study Mode request (no per-request override) resolves to right now.
    resolved, notice = resolve_study_provider()
    out["resolves_to"] = resolved
    out["resolve_notice"] = notice

    # ── Live key check: a real, cheap call to xAI grok-4.3 ──
    if grok_configured():
        key = (os.getenv("GROK_API_KEY") or "").strip()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{GROK_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": GROK_MODEL, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
                )
            out["grok_live_check"] = {
                "ok": r.status_code == 200,
                "status": r.status_code,
                "body": r.text[:400],
            }
        except Exception as e:
            out["grok_live_check"] = {"ok": False, "error": str(e)}
    else:
        out["grok_live_check"] = {"ok": False, "error": "GROK_API_KEY not set on this service"}

    return out

_NOTES_TABLE = "study_notes"
_CHATS_TABLE = "study_chats"
_CAPTURE_MODEL = "claude-sonnet-4-6"


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
    images: list[dict] | None = None


class StudyNoteUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    images: list[dict] | None = None


class StudyCaptureImage(BaseModel):
    base64: str
    type: str | None = "image/jpeg"


class StudyCapture(BaseModel):
    images: list[StudyCaptureImage] | None = None
    # Legacy single-image fields (still accepted)
    image_base64: str | None = None
    image_type: str | None = "image/jpeg"


class StudyChatCreate(BaseModel):
    title: str | None = None
    messages: list[dict] | None = None


class StudyChatUpdate(BaseModel):
    title: str | None = None
    messages: list[dict] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Capture — photo → OCR text + subject detection → saved study note
# ═══════════════════════════════════════════════════════════════════════════════

_CAPTURE_PROMPT = (
    "You are Jarvis Study Capture. A student just snapped one or more photos of study "
    "material (worksheet, textbook pages, whiteboard, handwritten notes, slides, etc.). "
    "When multiple images are given, treat them as consecutive PAGES of the SAME material "
    "and combine them into ONE coherent note in reading order.\n\n"
    "Do THREE things and return STRICT JSON only (no prose, no code fences):\n"
    "1. \"text\": Extract ALL the text/content from every image, cleanly and completely. "
    "Preserve structure (headings, numbered questions, bullet points, equations) using "
    "simple Markdown. Merge the pages into one continuous note; do not repeat a 'page 1/2' "
    "header for each image unless it's part of the content. Fix obvious OCR noise but do "
    "NOT invent content. If there are diagrams, briefly describe them in [brackets].\n"
    "2. \"subject\": The single best school subject/folder name for this material "
    "(e.g. \"Mathematics\", \"Biology\", \"History\", \"Chemistry\", \"English\", "
    "\"Physics\", \"Computer Science\"). One short Title-Case label.\n"
    "3. \"title\": A short 3-7 word title describing this specific note "
    "(e.g. \"Simultaneous Equations Worksheet\").\n\n"
    "Return exactly: {\"subject\": \"...\", \"title\": \"...\", \"text\": \"...\"}"
)


def _parse_capture_json(raw: str) -> dict:
    """Best-effort extraction of the JSON object from the model output."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Total fallback — keep whatever text we got so the note isn't lost
    return {"subject": "General", "title": "Captured note", "text": s}


@router.post("/study/capture/{user_id}")
async def capture_study_note(user_id: str, body: StudyCapture):
    """Photo → extract all text + detect subject → save as a categorized note."""
    _require_supabase()
    from backend.llm import _client

    # Collect images (new multi-image list, or legacy single field)
    raw_images: list[tuple[str, str]] = []  # (base64, media_type)
    if body.images:
        for img in body.images[:10]:
            b64 = img.base64.split(",")[1] if "," in img.base64 else img.base64
            mt = img.type or "image/jpeg"
            raw_images.append((b64, mt if mt.startswith("image/") else "image/jpeg"))
    elif body.image_base64:
        b64 = body.image_base64.split(",")[1] if "," in body.image_base64 else body.image_base64
        mt = body.image_type or "image/jpeg"
        raw_images.append((b64, mt if mt.startswith("image/") else "image/jpeg"))

    if not raw_images:
        raise HTTPException(422, "No image provided.")

    content_blocks = [
        {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}}
        for (b64, mt) in raw_images
    ]
    content_blocks.append({"type": "text", "text": _CAPTURE_PROMPT})

    try:
        msg = await _client.messages.create(
            model=_CAPTURE_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": content_blocks}],
        )
        out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:
        raise HTTPException(502, f"Could not read the photo: {e}")

    data = _parse_capture_json(out)
    subject = (data.get("subject") or "General").strip() or "General"
    title = (data.get("title") or "").strip()
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "No readable text found in the photo.")

    content = f"# {title}\n\n{text}" if title else text
    row = {"user_id": user_id, "content": content, "category": subject}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
            headers=_headers(),
            json=row,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"note": r.json()[0], "subject": subject, "title": title}


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
        "images": body.images or [],
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
    if body.images is not None:
        patch["images"] = body.images
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
