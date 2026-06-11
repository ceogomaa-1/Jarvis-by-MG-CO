"""
Central ingest hook for The Mind.

Every writer that inserts a row into business_user_memories
(memory.py, knowledge_base.py, morning_queue.py) calls process_new_memory()
right after the insert. This embeds the memory, classifies it into a Mind
cluster, refreshes its top-k similarity edges, and logs a 'born' activity
event — the things that make a memory "alive" on the graph.

Never raises — failures are logged and swallowed so they never break the
calling write path.
"""
import os

import httpx
from supabase import create_client

from backend.lib.business.mind.categorize import categorize_memory
from backend.lib.business.mind.embeddings import embed_text

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

SIMILARITY_THRESHOLD = 0.75
TOP_K = 3


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def process_new_memory(user_id: str, memory_id: str, memory_text: str) -> str | None:
    """Embeds, classifies, and links a new memory. Returns its mind_category (or None on failure)."""
    if not SUPABASE_URL or not SUPABASE_KEY or not memory_id:
        return None

    user_uuid = _user_id_to_uuid(user_id)

    try:
        embedding = await embed_text(memory_text)
        mind_category = await categorize_memory(memory_text)

        update_payload: dict = {"mind_category": mind_category}
        if embedding is not None:
            update_payload["embedding"] = embedding

        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{memory_id}"},
                json=update_payload,
                timeout=15.0,
            )

        if embedding is not None:
            await _refresh_edges(user_uuid, memory_id, embedding)

        await _log_activity(user_uuid, memory_id, "born")
        return mind_category
    except Exception as e:
        print(f"MIND_INGEST: process_new_memory error: {e}")
        return None


async def _refresh_edges(user_uuid: str, memory_id: str, embedding: list[float]) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        result = sb.rpc("match_mind_memories", {
            "query_embedding": embedding,
            "match_user_id": user_uuid,
            "exclude_memory_id": memory_id,
            "match_threshold": SIMILARITY_THRESHOLD,
            "match_count": TOP_K,
        }).execute()
        neighbors = result.data or []
    except Exception as e:
        print(f"MIND_INGEST: similarity RPC error: {e}")
        return

    for neighbor in neighbors:
        neighbor_id = neighbor.get("id")
        similarity = neighbor.get("similarity")
        if not neighbor_id or similarity is None:
            continue
        memory_a_id, memory_b_id = sorted([memory_id, neighbor_id])
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/business_mind_edges",
                    headers={**_write_headers(), "Prefer": "return=minimal,resolution=merge-duplicates"},
                    params={"on_conflict": "memory_a_id,memory_b_id"},
                    json={
                        "user_id": user_uuid,
                        "memory_a_id": memory_a_id,
                        "memory_b_id": memory_b_id,
                        "weight": similarity,
                    },
                    timeout=10.0,
                )
        except Exception as e:
            print(f"MIND_INGEST: edge upsert error: {e}")


async def _log_activity(user_uuid: str, memory_id: str, event_type: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_mind_activity",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                json={"user_id": user_uuid, "memory_id": memory_id, "event_type": event_type},
                timeout=10.0,
            )
    except Exception as e:
        print(f"MIND_INGEST: activity log error: {e}")
