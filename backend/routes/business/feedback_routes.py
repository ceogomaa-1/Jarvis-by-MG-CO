"""
Wish Box -> Notion feedback pipeline.

  POST /business/feedback/wish  — {user_id, email, wish_text}

Creates a page in Mohamed's "Rue Updates Requests" Notion database. If the
Notion call fails for any reason (missing/invalid key, rate limit, the
integration losing access to the database, etc), the wish is persisted to
`jarvis_wishes` with `notion_synced=false` and the user still sees success —
they must never know Notion was involved. Unsynced wishes are retried,
a few at a time, on every subsequent submission.
"""
import asyncio
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from supabase import create_client

router = APIRouter()

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"

# "Rue Updates Requests" — properties: "USER ID" (title), "Request" (rich_text)
WISH_DATABASE_ID = "37dfb2cf-b34c-80dd-8502-ffb7b39b5eac"


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _chunk_text(text: str, size: int = 1900) -> list[str]:
    text = text or ""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


class WishRequest(BaseModel):
    user_id: str
    email: str | None = None
    wish_text: str


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _wish_page_body(user_id_label: str, email: str | None, wish_text: str) -> dict:
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]},
        }
        for chunk in _chunk_text(wish_text)
    ]
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {
            "content": f"From: {email or 'unknown'} ({user_id_label}) — submitted {datetime.now(timezone.utc).isoformat()}"
        }}]},
    })
    return {
        "parent": {"database_id": WISH_DATABASE_ID},
        "properties": {
            "USER ID": {"title": [{"text": {"content": user_id_label[:200]}}]},
            "Request": {"rich_text": [{"text": {"content": wish_text[:2000]}}]},
        },
        "children": children,
    }


async def _create_notion_page(user_id_label: str, email: str | None, wish_text: str) -> str | None:
    """Returns the new Notion page id, or None on any failure."""
    if not NOTION_API_KEY:
        print("WISH_BOX: NOTION_API_KEY not set — skipping Notion sync")
        return None
    body = _wish_page_body(user_id_label, email, wish_text)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{NOTION_BASE}/pages", headers=_notion_headers(), json=body, timeout=15.0)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        print(f"WISH_BOX: Notion create_page failed: {e}")
        return None


def _save_wish_row(sb, user_uuid: str, email: str | None, wish_text: str, notion_page_id: str | None, notion_synced: bool) -> None:
    try:
        sb.table("jarvis_wishes").insert({
            "user_id": user_uuid,
            "email": email,
            "wish_text": wish_text,
            "notion_page_id": notion_page_id,
            "notion_synced": notion_synced,
        }).execute()
    except Exception as e:
        print(f"WISH_BOX: failed to save jarvis_wishes row: {e}")


def _store_wish_memory(sb, user_uuid: str, wish_text: str) -> None:
    try:
        memory_text = f"User wished for: {wish_text[:300]}"
        existing = (
            sb.table("business_user_memories")
            .select("id")
            .eq("user_id", user_uuid)
            .eq("memory", memory_text)
            .execute()
        )
        if not existing.data:
            sb.table("business_user_memories").insert({
                "user_id": user_uuid,
                "memory": memory_text,
                "category": "wish",
            }).execute()
    except Exception as e:
        print(f"WISH_BOX: failed to store memory: {e}")


def _fetch_unsynced_wishes(sb) -> list[dict]:
    try:
        res = (
            sb.table("jarvis_wishes")
            .select("id, user_id, email, wish_text")
            .eq("notion_synced", False)
            .order("created_at", desc=False)
            .limit(3)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"WISH_BOX: retry lookup failed: {e}")
        return []


def _mark_wish_synced(sb, wish_id: str, page_id: str) -> None:
    try:
        sb.table("jarvis_wishes").update({
            "notion_synced": True,
            "notion_page_id": page_id,
        }).eq("id", wish_id).execute()
    except Exception as e:
        print(f"WISH_BOX: failed to mark wish {wish_id} synced: {e}")


async def _retry_unsynced_wishes(sb) -> None:
    pending = await asyncio.to_thread(_fetch_unsynced_wishes, sb)
    for row in pending:
        page_id = await _create_notion_page(row.get("user_id", ""), row.get("email"), row.get("wish_text", ""))
        if page_id:
            await asyncio.to_thread(_mark_wish_synced, sb, row["id"], page_id)
            print(f"WISH_BOX: retry synced wish {row['id']} to Notion")


@router.post("/business/feedback/wish")
async def submit_wish(req: WishRequest):
    sb = _get_supabase()
    user_uuid = _user_id_to_uuid(req.user_id)
    wish_text = (req.wish_text or "").strip()

    page_id = await _create_notion_page(req.user_id, req.email, wish_text)
    notion_synced = page_id is not None
    if not notion_synced:
        print(f"WISH_BOX: Notion sync failed for user {req.user_id} — falling back to jarvis_wishes")

    if sb:
        await asyncio.to_thread(_save_wish_row, sb, user_uuid, req.email, wish_text, page_id, notion_synced)
        await asyncio.to_thread(_store_wish_memory, sb, user_uuid, wish_text)
        if notion_synced:
            await _retry_unsynced_wishes(sb)

    return {"ok": True}
