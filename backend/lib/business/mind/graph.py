"""
Graph assembly for The Mind: nodes (memories), edges (semantic similarity),
queue_nodes (Morning Queue items spawned from memories), plus the
thought-trace activity log (live lighting + 24h replay).
"""
import asyncio
import math
import os
from datetime import datetime, timedelta, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"}


def _strength(created_at: str | None, last_referenced_at: str | None, reference_count: int) -> float:
    """strength = 0.5 * recency_decay(30d half-life-ish) + 0.5 * frequency(log-scaled)"""
    anchor = last_referenced_at or created_at
    try:
        last = datetime.fromisoformat((anchor or "").replace("Z", "+00:00"))
    except Exception:
        last = datetime.now(timezone.utc)
    days_since = max(0.0, (datetime.now(timezone.utc) - last).total_seconds() / 86400)
    recency = math.exp(-days_since / 30)
    frequency = math.log1p(max(0, reference_count or 0)) / math.log1p(20)
    return min(1.0, 0.5 * recency + 0.5 * frequency)


def _source_for(memory: dict) -> str:
    category = memory.get("category") or "general"
    if category == "knowledge_base" or memory.get("knowledge_source_id"):
        return "knowledge_base"
    if category == "morning_queue_action":
        return "morning_queue"
    return "chat"


async def build_graph(user_id: str, limit: int = 300) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"nodes": [], "edges": [], "queue_nodes": []}

    user_uuid = _user_id_to_uuid(user_id)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

    async with httpx.AsyncClient() as client:
        mem_resp, queue_resp = await asyncio.gather(
            client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_read_headers(),
                params={
                    "user_id": f"eq.{user_uuid}",
                    "select": "id,memory,mind_category,category,knowledge_source_id,created_at,last_referenced_at,reference_count",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
                timeout=15.0,
            ),
            client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers=_read_headers(),
                params={
                    "user_id": f"eq.{user_uuid}",
                    "created_at": f"gte.{cutoff}",
                    "source_memory_ids": "not.is.null",
                    "select": "id,title,action_prompt,source_memory_ids,synapse_id,created_at",
                },
                timeout=15.0,
            ),
        )
        memories = mem_resp.json() if mem_resp.status_code == 200 else []

        nodes = []
        memory_ids = []
        for mem in memories:
            mem_id = mem.get("id")
            if not mem_id:
                continue
            memory_ids.append(mem_id)
            nodes.append({
                "id": mem_id,
                "type": "memory",
                "memory": mem.get("memory", ""),
                "mind_category": mem.get("mind_category") or "general",
                "source": _source_for(mem),
                "created_at": mem.get("created_at"),
                "strength": _strength(mem.get("created_at"), mem.get("last_referenced_at"), mem.get("reference_count") or 0),
            })

        edges = []
        if memory_ids:
            id_list = ",".join(memory_ids)
            edge_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_mind_edges",
                headers=_read_headers(),
                params={
                    "user_id": f"eq.{user_uuid}",
                    "or": f"(memory_a_id.in.({id_list}),memory_b_id.in.({id_list}))",
                    "select": "memory_a_id,memory_b_id,weight",
                },
                timeout=15.0,
            )
            if edge_resp.status_code == 200:
                memory_id_set = set(memory_ids)
                for edge in edge_resp.json():
                    a, b = edge.get("memory_a_id"), edge.get("memory_b_id")
                    if a in memory_id_set and b in memory_id_set:
                        edges.append({"source": a, "target": b, "weight": edge.get("weight", 0.5)})

        queue_nodes = []
        if queue_resp.status_code == 200:
            for item in queue_resp.json():
                queue_nodes.append({
                    "id": item.get("id"),
                    "type": "queue_item",
                    "title": item.get("title"),
                    "action_prompt": item.get("action_prompt"),
                    "source_memory_ids": item.get("source_memory_ids") or [],
                    "synapse_id": item.get("synapse_id"),
                    "created_at": item.get("created_at"),
                })

    return {"nodes": nodes, "edges": edges, "queue_nodes": queue_nodes}


async def record_activity(user_id: str, memory_ids: list[str], event_type: str, conversation_id: str | None = None) -> None:
    if not memory_ids or not SUPABASE_URL or not SUPABASE_KEY:
        return

    user_uuid = _user_id_to_uuid(user_id)
    rows = [
        {"user_id": user_uuid, "memory_id": mid, "event_type": event_type, "conversation_id": conversation_id}
        for mid in memory_ids
    ]

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/business_mind_activity",
            headers=_write_headers(),
            json=rows,
            timeout=15.0,
        )

        if event_type != "used":
            return

        for mid in memory_ids:
            try:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/business_user_memories",
                    headers=_read_headers(),
                    params={"id": f"eq.{mid}", "select": "reference_count"},
                    timeout=10.0,
                )
                rows_data = resp.json() if resp.status_code == 200 else []
                current = rows_data[0].get("reference_count", 0) if rows_data else 0
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/business_user_memories",
                    headers=_write_headers(),
                    params={"id": f"eq.{mid}"},
                    json={
                        "reference_count": (current or 0) + 1,
                        "last_referenced_at": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=10.0,
                )
            except Exception as e:
                print(f"MIND_GRAPH: record_activity reference bump error: {e}")


async def get_activity(user_id: str, since_iso: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    user_uuid = _user_id_to_uuid(user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_mind_activity",
            headers=_read_headers(),
            params={
                "user_id": f"eq.{user_uuid}",
                "created_at": f"gte.{since_iso}",
                "select": "memory_id,event_type,conversation_id,created_at",
                "order": "created_at.asc",
            },
            timeout=15.0,
        )
        return resp.json() if resp.status_code == 200 else []
