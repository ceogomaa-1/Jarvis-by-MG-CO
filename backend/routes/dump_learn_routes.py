"""Dump Learn — routes (Rue Personal, Study Mode).

A "bin" the user dumps raw material into; Rue parses it down to lean text
(dump_learn_ingest), then explains it back at a chosen comprehension level
(dump_learn_engine). Files are uploaded directly from the browser to the
private `dump-learn-uploads` Storage bucket (same convention as
personal-chat-attachments) — this route only ever receives a storage_path for
file-kind items, never raw bytes, so a large PDF never has to pass through
this server as a request body.

Uses the Supabase REST API directly with the service-role key (same pattern
as study_routes.py).
"""
import asyncio
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent import _SUPABASE_URL, _SUPABASE_KEY
from backend.lib.personal import dump_learn_ingest, dump_learn_engine

router = APIRouter()

_BINS_TABLE = "dump_learn_bins"
_ITEMS_TABLE = "dump_learn_items"

_VALID_LEVELS = ("child", "graduate", "expert")
_VALID_KINDS = ("pdf", "docx", "pptx", "url", "youtube", "image", "text")

# Fire-and-forget task tracking (same convention as crm_enrich.track_task) — keeps
# a reference so background parse tasks aren't garbage-collected mid-run.
_BG_TASKS: set[asyncio.Task] = set()


def track_task(task: asyncio.Task) -> None:
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _require_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise HTTPException(503, "Dump Learn storage is not configured")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Models ───────────────────────────────────────────────────────────────────

class BinCreate(BaseModel):
    title: str | None = None


class BinUpdate(BaseModel):
    title: str | None = None
    level: str | None = None


class ItemCreate(BaseModel):
    kind: str
    source_name: str | None = None
    source_url: str | None = None       # url | youtube
    storage_path: str | None = None     # pdf | docx | pptx | image
    media_type: str | None = None       # image
    text: str | None = None             # text (pasted)


class ExplainRequest(BaseModel):
    level: str


class AskRequest(BaseModel):
    question: str


# ═══════════════════════════════════════════════════════════════════════════════
# Bins
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dump-learn/bins/{user_id}")
async def list_bins(user_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers(),
            params={"user_id": f"eq.{user_id}", "order": "updated_at.desc", "select": "*"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"bins": r.json()}


@router.post("/dump-learn/bins/{user_id}")
async def create_bin(user_id: str, body: BinCreate):
    _require_supabase()
    row = {"user_id": user_id, "title": (body.title or "New bin").strip()[:120] or "New bin"}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers(),
            json=row,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"bin": r.json()[0]}


@router.get("/dump-learn/bins/{user_id}/{bin_id}")
async def get_bin(user_id: str, bin_id: str):
    """Bin + its items — used to reopen a bin (or poll while items are parsing)."""
    _require_supabase()
    async with httpx.AsyncClient() as client:
        bin_r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{bin_id}", "user_id": f"eq.{user_id}", "select": "*"},
            timeout=15,
        )
        items_r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}",
            headers=_headers(),
            params={"bin_id": f"eq.{bin_id}", "user_id": f"eq.{user_id}", "order": "created_at.asc", "select": "*"},
            timeout=15,
        )
    if bin_r.status_code >= 400:
        raise HTTPException(bin_r.status_code, bin_r.text)
    rows = bin_r.json()
    if not rows:
        raise HTTPException(404, "bin not found")
    items = items_r.json() if items_r.status_code < 400 else []
    return {"bin": rows[0], "items": items}


@router.get("/dump-learn/bins/{user_id}/{bin_id}/status")
async def bin_status(user_id: str, bin_id: str):
    """Lightweight poll target while items are pending/parsing — the shrink-o-meter
    reads token_estimate/raw_char_count/original_size_bytes off this."""
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}",
            headers=_headers(),
            params={
                "bin_id": f"eq.{bin_id}", "user_id": f"eq.{user_id}", "order": "created_at.asc",
                "select": "id,kind,source_name,status,error,original_size_bytes,raw_char_count,token_estimate",
            },
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    items = r.json()
    return {
        "items": items,
        "all_settled": all(it["status"] in ("ready", "error") for it in items) if items else False,
        "ready_count": sum(1 for it in items if it["status"] == "ready"),
        "total_tokens": sum(it.get("token_estimate") or 0 for it in items if it["status"] == "ready"),
    }


@router.patch("/dump-learn/bins/{user_id}/{bin_id}")
async def update_bin(user_id: str, bin_id: str, body: BinUpdate):
    _require_supabase()
    patch: dict = {"updated_at": _now()}
    if body.title is not None:
        patch["title"] = body.title.strip()[:120] or "New bin"
    if body.level is not None:
        if body.level not in _VALID_LEVELS:
            raise HTTPException(422, f"level must be one of {_VALID_LEVELS}")
        patch["level"] = body.level
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{bin_id}", "user_id": f"eq.{user_id}"},
            json=patch,
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    rows = r.json()
    if not rows:
        raise HTTPException(404, "bin not found")
    return {"bin": rows[0]}


@router.delete("/dump-learn/bins/{user_id}/{bin_id}")
async def delete_bin(user_id: str, bin_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{bin_id}", "user_id": f"eq.{user_id}"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# Items
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/dump-learn/bins/{user_id}/{bin_id}/items")
async def add_item(user_id: str, bin_id: str, body: ItemCreate):
    _require_supabase()
    if body.kind not in _VALID_KINDS:
        raise HTTPException(422, f"kind must be one of {_VALID_KINDS}")

    if body.kind in ("pdf", "docx", "pptx", "image") and not body.storage_path:
        raise HTTPException(422, f"{body.kind} items need storage_path (upload to Storage first)")
    if body.kind in ("url", "youtube") and not body.source_url:
        raise HTTPException(422, f"{body.kind} items need source_url")
    if body.kind == "text" and not (body.text or "").strip():
        raise HTTPException(422, "text items need non-empty text")

    row = {
        "bin_id": bin_id,
        "user_id": user_id,
        "kind": body.kind,
        "source_name": (body.source_name or body.source_url or "Pasted text")[:200],
        "source_url": body.source_url,
        "storage_path": body.storage_path,
        "status": "pending",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}",
            headers=_headers(),
            json=row,
            timeout=15,
        )
        # touch the bin so it sorts to the top of the bin list
        await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{bin_id}"},
            json={"updated_at": _now()},
            timeout=10,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    item = r.json()[0]

    task = asyncio.create_task(dump_learn_ingest.ingest_item_task(
        item["id"], bin_id, user_id, body.kind,
        storage_path=body.storage_path,
        url=body.source_url,
        text=body.text,
        media_type=body.media_type,
        filename=body.source_name,
    ))
    track_task(task)

    return {"item": item}


@router.delete("/dump-learn/bins/{user_id}/{bin_id}/items/{item_id}")
async def delete_item(user_id: str, bin_id: str, item_id: str):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{item_id}", "bin_id": f"eq.{bin_id}", "user_id": f"eq.{user_id}"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# Explain + follow-up chat
# ═══════════════════════════════════════════════════════════════════════════════

async def _load_ready_items(user_id: str, bin_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}",
            headers=_headers(),
            params={"bin_id": f"eq.{bin_id}", "user_id": f"eq.{user_id}", "select": "*"},
            timeout=15,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()


@router.post("/dump-learn/bins/{user_id}/{bin_id}/explain")
async def explain(user_id: str, bin_id: str, body: ExplainRequest):
    _require_supabase()
    if body.level not in _VALID_LEVELS:
        raise HTTPException(422, f"level must be one of {_VALID_LEVELS}")

    items = await _load_ready_items(user_id, bin_id)
    result = await dump_learn_engine.explain_bin(bin_id, user_id, body.level, items)
    if result.get("error"):
        raise HTTPException(422, result["error"])

    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{bin_id}"},
            json={"level": body.level, "updated_at": _now()},
            timeout=10,
        )

    return {"lesson": result["lesson"], "cached": result["cached"], "cost": result["cost"], "level": body.level}


@router.post("/dump-learn/bins/{user_id}/{bin_id}/ask")
async def ask(user_id: str, bin_id: str, body: AskRequest):
    _require_supabase()
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(422, "question required")

    async with httpx.AsyncClient() as client:
        bin_r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_BINS_TABLE}",
            headers=_headers(),
            params={"id": f"eq.{bin_id}", "user_id": f"eq.{user_id}", "select": "level"},
            timeout=10,
        )
    bin_rows = bin_r.json() if bin_r.status_code < 400 else []
    level = bin_rows[0]["level"] if bin_rows else "graduate"

    items = await _load_ready_items(user_id, bin_id)
    result = await dump_learn_engine.answer_followup(bin_id, user_id, level, items, question)
    if result.get("error"):
        raise HTTPException(422, result["error"])
    return {"answer": result["answer"], "cost": result["cost"]}
