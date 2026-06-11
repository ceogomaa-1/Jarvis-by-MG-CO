"""
Golden Synapses (Batch 47 bonus): weekly + on-demand (rate-limited 1/day)
discovery of non-obvious cross-cluster connections between memories.
Qualifying pairs become golden arcs on The Mind and land in Morning Queue
as 'opportunity' items.
"""
import itertools
import json
import os
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from backend.lib.business.mind.graph import _strength

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SONNET = "claude-sonnet-4-6"
TORONTO = ZoneInfo("America/Toronto")

SAMPLE_POOL = 60
SAMPLE_PAIRS = 40


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}


async def _already_ran_today(user_uuid: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    today_start = (
        datetime.now(TORONTO)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .isoformat()
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_mind_synapses",
            headers=_read_headers(),
            params={
                "user_id": f"eq.{user_uuid}",
                "created_at": f"gte.{today_start}",
                "select": "id",
                "limit": "1",
            },
            timeout=10.0,
        )
    return resp.status_code == 200 and len(resp.json()) > 0


async def _fetch_memories(user_uuid: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_user_memories",
            headers=_read_headers(),
            params={
                "user_id": f"eq.{user_uuid}",
                "mind_category": "not.is.null",
                "select": "id,memory,mind_category,created_at,last_referenced_at,reference_count",
                "order": "created_at.desc",
                "limit": "300",
            },
            timeout=15.0,
        )
    return resp.json() if resp.status_code == 200 else []


def _sample_cross_cluster_pairs(memories: list[dict]) -> list[tuple[dict, dict]]:
    scored = sorted(
        memories,
        key=lambda m: _strength(m.get("created_at"), m.get("last_referenced_at"), m.get("reference_count") or 0),
        reverse=True,
    )
    pool = scored[:SAMPLE_POOL]

    pairs = [
        (a, b)
        for a, b in itertools.combinations(pool, 2)
        if a.get("mind_category") and b.get("mind_category") and a["mind_category"] != b["mind_category"]
    ]
    random.shuffle(pairs)
    return pairs[:SAMPLE_PAIRS]


_SYNAPSE_PROMPT = """\
You are Jarvis, an AI business partner studying a list of memories about a small business owner. \
Below are pairs of memories from DIFFERENT areas of their business. Your job is to find pairs where \
connecting them reveals a genuinely NON-OBVIOUS, ACTIONABLE insight the owner probably hasn't noticed.

Set a strict bar: most pairs will have NO meaningful connection. Only flag a pair if connecting them \
would make the owner say "huh, I hadn't thought of that" - a real opportunity, risk, or synergy.

PAIRS:
{pairs_block}

Respond with ONLY a JSON array (no markdown fences, no commentary). Each element must be \
{{"pair_index": <int>, "insight": "<one or two sentence insight, written directly to the owner as 'you'>"}}. \
Omit any pair with no genuine connection. If no pairs qualify, respond with []."""


def _format_pairs_block(pairs: list[tuple[dict, dict]]) -> str:
    lines = []
    for i, (a, b) in enumerate(pairs):
        lines.append(
            f"{i}. [{a.get('mind_category')}] \"{(a.get('memory') or '')[:200]}\"\n"
            f"   <-> [{b.get('mind_category')}] \"{(b.get('memory') or '')[:200]}\""
        )
    return "\n".join(lines)


def _parse_synapse_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [
        item for item in parsed
        if isinstance(item, dict) and isinstance(item.get("pair_index"), int) and item.get("insight")
    ]


async def _call_llm(pairs: list[tuple[dict, dict]]) -> list[dict]:
    if not ANTHROPIC_API_KEY or not pairs:
        return []
    prompt = _SYNAPSE_PROMPT.format(pairs_block=_format_pairs_block(pairs))
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": SONNET,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
        if resp.status_code != 200:
            print(f"MIND_SYNAPSES: API error {resp.status_code}: {resp.text[:200]}")
            return []
        raw = resp.json().get("content", [{}])[0].get("text", "")
        return _parse_synapse_array(raw)
    except Exception as e:
        print(f"MIND_SYNAPSES: error: {e}")
        return []


async def generate_synapses(user_id: str, force: bool = False) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"rate_limited": False, "synapses": []}

    user_uuid = _user_id_to_uuid(user_id)

    if not force and await _already_ran_today(user_uuid):
        return {"rate_limited": True, "synapses": []}

    memories = await _fetch_memories(user_uuid)
    pairs = _sample_cross_cluster_pairs(memories)
    if not pairs:
        return {"rate_limited": False, "synapses": []}

    flagged = await _call_llm(pairs)
    if not flagged:
        return {"rate_limited": False, "synapses": []}

    today = datetime.now(TORONTO).date().isoformat()
    created = []

    async with httpx.AsyncClient() as client:
        for item in flagged:
            idx = item["pair_index"]
            if idx < 0 or idx >= len(pairs):
                continue
            a, b = pairs[idx]
            insight = str(item["insight"]).strip()[:600]
            if not insight:
                continue
            memory_a_id, memory_b_id = sorted([a["id"], b["id"]])

            try:
                syn_resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/business_mind_synapses",
                    headers=_write_headers(),
                    json={
                        "user_id": user_uuid,
                        "memory_a_id": memory_a_id,
                        "memory_b_id": memory_b_id,
                        "insight": insight,
                    },
                    timeout=15.0,
                )
                rows = syn_resp.json() if syn_resp.status_code in (200, 201) else []
                synapse = rows[0] if rows else None
                if not synapse:
                    continue

                await client.post(
                    f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                    headers={**_write_headers(), "Prefer": "return=minimal"},
                    json={
                        "user_id": user_uuid,
                        "date": today,
                        "type": "opportunity",
                        "title": "Jarvis found a hidden connection",
                        "body": insight,
                        "action_prompt": f"Tell me more about this connection: {insight}",
                        "read": False,
                        "source_memory_ids": [memory_a_id, memory_b_id],
                        "synapse_id": synapse["id"],
                    },
                    timeout=15.0,
                )
                created.append(synapse)
            except Exception as e:
                print(f"MIND_SYNAPSES: insert error: {e}")

    return {"rate_limited": False, "synapses": created}


async def list_synapses(user_id: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    user_uuid = _user_id_to_uuid(user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_mind_synapses",
            headers=_read_headers(),
            params={
                "user_id": f"eq.{user_uuid}",
                "select": "id,memory_a_id,memory_b_id,insight,created_at",
                "order": "created_at.desc",
                "limit": "50",
            },
            timeout=15.0,
        )
    return resp.json() if resp.status_code == 200 else []
