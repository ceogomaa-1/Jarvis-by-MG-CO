"""
Morning Queue — Rue's daily proactive digest.

Once a day (Render Cron -> POST /business/morning-queue/generate-all, or a
manual POST /business/morning-queue/generate-one for testing), every "active"
user (operator_enabled = true OR readiness score >= 60) gets 3-6 fresh queue
items generated from their memories, their industry's Daily Operations
playbook, and any connected-tool signals (Google Calendar, GoHighLevel
contacts, business metrics). Items land in morning_queue_items.

Acting on an item ("Act on this ->") buries a memory of what was actioned and
hands back the item's action_prompt so the frontend can drop it straight into
chat. Today's items are also injected into the chat system prompt via
queue_digest_for_prompt() so a fresh session already knows what's in the
queue.
"""
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from backend.lib.business.bible_loader import load_bible
from backend.lib.business.brand_config import get_brand_config, list_operator_enabled_users
from backend.lib.business.connectors.registry import (
    available_connectors_summary,
    get_connector_for_user,
    list_user_connections,
)
from backend.lib.business.mind.ingest import process_new_memory
from backend.lib.business.model_router import SONNET
from backend.lib.business.readiness import calculate_readiness

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

TORONTO = ZoneInfo("America/Toronto")

_VALID_TYPES = {"suggestion", "draft", "warning", "opportunity"}
_MAX_CONTEXT_CHARS = 9000


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}


def _today():
    return datetime.now(TORONTO).date()


_GENERATION_PROMPT = """\
You are Rue, an AI business operator preparing the Morning Queue for {company_name} \
({industry_label}). The Morning Queue is a short list of things waiting for the owner \
when they open the app this morning — drafts ready to send, warnings about things \
slipping, and opportunities worth chasing.

CONTEXT JARVIS KNOWS ABOUT THIS BUSINESS:
{context_block}

Generate 3-6 Morning Queue items. Each item has:
- "type": one of "suggestion" (a recommended action), "draft" (something Rue can \
pre-write for review — email, post, message), "warning" (something needs attention — \
stale lead, slipping metric, missed follow-up), or "opportunity" (a revenue/growth \
opening spotted in the data)
- "title": punchy, 6 words max
- "body": 1-3 sentences, specific — reference real names/numbers/dates from the context \
above whenever you can. No generic filler.
- "action_prompt": a first-person message the owner could send Rue to act on this \
right now (e.g. "Draft a follow-up email to Sarah about the Maple St listing")

If there's little to go on (no connected tools, few memories), still produce at least 2 \
items grounded in what IS known — never return an empty list.

Return ONLY a valid JSON array of items, nothing else."""


# ─── Context gathering ──────────────────────────────────────────────────

async def _fetch_business_profile(user_id: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_users",
                headers=_read_headers(),
                params={"select": "company_name,industry,role", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
        return rows[0] if rows else {}
    except Exception as e:
        print(f"MORNING_QUEUE: profile fetch error: {e}")
        return {}


async def _fetch_memories(user_uuid: str, limit: int = 20) -> list[dict]:
    """Returns recent memories as [{id, memory}, ...]."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_read_headers(),
                params={
                    "select": "id,memory",
                    "user_id": f"eq.{user_uuid}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
        return [{"id": r["id"], "memory": r["memory"]} for r in rows if r.get("memory") and r.get("id")]
    except Exception as e:
        print(f"MORNING_QUEUE: memories fetch error: {e}")
        return []


async def _fetch_metrics_text(user_id: str) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_metrics",
                headers=_read_headers(),
                params={"select": "metrics_text", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
        return rows[0].get("metrics_text", "") if rows else ""
    except Exception as e:
        print(f"MORNING_QUEUE: metrics fetch error: {e}")
        return ""


async def _calendar_signal(user_id: str) -> str:
    try:
        conn = await get_connector_for_user(user_id, "google")
        if not conn:
            return ""
        result = await conn.list_calendar_events(max_results=5)
        if not result.ok:
            return ""
        events = (result.data or {}).get("events", [])
        if not events:
            return ""
        lines = []
        for e in events:
            start = e.get("start", {}) or {}
            when = start.get("dateTime") or start.get("date") or "?"
            lines.append(f"- {e.get('summary', '(no title)')} at {when}")
        return "Today's calendar:\n" + "\n".join(lines)
    except Exception as e:
        print(f"MORNING_QUEUE: calendar signal error: {e}")
        return ""


async def _crm_signal(user_id: str) -> str:
    try:
        conn = await get_connector_for_user(user_id, "gohighlevel")
        if not conn:
            return ""
        result = await conn.list_contacts_v2(limit=10)
        if not result.ok:
            return ""
        contacts = (result.data or {}).get("contacts", [])
        if not contacts:
            return ""
        lines = []
        for c in contacts[:10]:
            name = " ".join(filter(None, [c.get("firstName"), c.get("lastName")])) or c.get("email") or "Unnamed contact"
            updated = c.get("dateUpdated") or c.get("dateAdded") or "unknown"
            lines.append(f"- {name} (last activity: {updated})")
        return "CRM contacts (review for stale follow-ups):\n" + "\n".join(lines)
    except Exception as e:
        print(f"MORNING_QUEUE: CRM signal error: {e}")
        return ""


async def _gather_context(user_id: str) -> dict:
    user_uuid = _user_id_to_uuid(user_id)

    profile = await _fetch_business_profile(user_id)
    industry = profile.get("industry", "")
    company_name = profile.get("company_name") or "the business"

    memory_rows = await _fetch_memories(user_uuid)
    memories = [r["memory"] for r in memory_rows]
    memory_ids = [r["id"] for r in memory_rows]
    metrics_text = await _fetch_metrics_text(user_id)

    bible = load_bible(industry) if industry else {}
    daily_ops = bible.get("daily_ops", "")

    brand = await get_brand_config(user_id)
    north_star = brand.get("north_star_target_label", "")

    connections = await list_user_connections(user_id)
    active_types = {c["connector_type"] for c in connections if c.get("status") == "active"}
    connector_summary = await available_connectors_summary(user_id)

    calendar_text = await _calendar_signal(user_id) if "google" in active_types else ""
    crm_text = await _crm_signal(user_id) if "gohighlevel" in active_types else ""

    sections = []
    if memories:
        sections.append("Recent memories Rue has about this user/business:\n" + "\n".join(f"- {m}" for m in memories))
    if daily_ops:
        sections.append(daily_ops)
    if north_star:
        sections.append(f"North Star goal: {north_star}")
    if metrics_text:
        sections.append(f"Latest business metrics:\n{metrics_text}")
    if calendar_text:
        sections.append(calendar_text)
    if crm_text:
        sections.append(crm_text)
    if connector_summary:
        sections.append(connector_summary)

    context_block = "\n\n---\n\n".join(s for s in sections if s)
    if len(context_block) > _MAX_CONTEXT_CHARS:
        context_block = context_block[:_MAX_CONTEXT_CHARS]
    if not context_block:
        context_block = "No memories or connected tools yet — Rue is just getting started with this business."

    return {
        "company_name": company_name,
        "industry_label": industry or "general business",
        "context_block": context_block,
        "memory_ids": memory_ids,
    }


# ─── LLM generation ─────────────────────────────────────────────────────

def _parse_items_array(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner).strip()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    cleaned = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()[:120]
        body = str(it.get("body", "")).strip()[:600]
        if not title or not body:
            continue
        item_type = str(it.get("type", "")).strip().lower()
        if item_type not in _VALID_TYPES:
            item_type = "suggestion"
        action_prompt = str(it.get("action_prompt", "")).strip()[:500] or body
        cleaned.append({"type": item_type, "title": title, "body": body, "action_prompt": action_prompt})
    return cleaned[:6]


async def _call_llm_for_items(ctx: dict) -> list[dict]:
    if not ANTHROPIC_API_KEY:
        return []
    prompt = _GENERATION_PROMPT.format(**ctx)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": SONNET, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]},
                timeout=60.0,
            )
        if resp.status_code != 200:
            print(f"MORNING_QUEUE: generation API error {resp.status_code}: {resp.text[:200]}")
            return []
        raw = resp.json().get("content", [{}])[0].get("text", "")
        return _parse_items_array(raw)
    except Exception as e:
        print(f"MORNING_QUEUE: generation error: {e}")
        return []


# ─── Generation entry points ────────────────────────────────────────────

async def _has_items_for_date(user_uuid: str, day) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers=_read_headers(),
                params={"select": "id", "user_id": f"eq.{user_uuid}", "date": f"eq.{day.isoformat()}", "limit": "1"},
                timeout=10.0,
            )
        return resp.status_code == 200 and bool(resp.json())
    except Exception as e:
        print(f"MORNING_QUEUE: has_items check error: {e}")
        return False


async def generate_queue_for_user(user_id: str, force: bool = False) -> dict:
    """Generate today's queue items for one user. Idempotent unless force=True."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"user_id": user_id, "status": "error", "error": "Supabase not configured", "items_created": 0}

    user_uuid = _user_id_to_uuid(user_id)
    today = _today()

    if not force and await _has_items_for_date(user_uuid, today):
        return {"user_id": user_id, "status": "skipped", "reason": "already generated today", "items_created": 0}

    ctx = await _gather_context(user_id)
    items = await _call_llm_for_items(ctx)
    if not items:
        return {"user_id": user_id, "status": "skipped", "reason": "no items generated", "items_created": 0}

    source_memory_ids = ctx.get("memory_ids") or None

    rows = [
        {
            "user_id": user_uuid,
            "date": today.isoformat(),
            "type": item["type"],
            "title": item["title"],
            "body": item["body"],
            "action_prompt": item["action_prompt"],
            "read": False,
            "source_memory_ids": source_memory_ids,
        }
        for item in items
    ]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                json=rows,
                timeout=15.0,
            )
        if resp.status_code not in (200, 201, 204):
            print(f"MORNING_QUEUE: insert failed {resp.status_code}: {resp.text[:200]}")
            return {"user_id": user_id, "status": "error", "error": "insert failed", "items_created": 0}
    except Exception as e:
        print(f"MORNING_QUEUE: insert error: {e}")
        return {"user_id": user_id, "status": "error", "error": str(e), "items_created": 0}

    return {"user_id": user_id, "status": "ok", "items_created": len(rows)}


async def list_active_users() -> list[str]:
    """Users eligible for queue generation: operator_enabled=true OR readiness score >= 60."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_users",
                headers=_read_headers(),
                params={"select": "user_id"},
                timeout=15.0,
            )
        all_users = [r["user_id"] for r in resp.json() if r.get("user_id")] if resp.status_code == 200 else []
    except Exception as e:
        print(f"MORNING_QUEUE: list users error: {e}")
        return []

    if not all_users:
        return []

    operator_rows = await list_operator_enabled_users()
    operator_uuids = {r["user_id"] for r in operator_rows if r.get("user_id")}

    eligible = []
    for user_id in all_users:
        if _user_id_to_uuid(user_id) in operator_uuids:
            eligible.append(user_id)
            continue
        try:
            readiness = await calculate_readiness(user_id)
            if readiness.get("score", 0) >= 60:
                eligible.append(user_id)
        except Exception as e:
            print(f"MORNING_QUEUE: readiness check failed for {user_id}: {e}")

    return eligible


async def generate_for_all_users() -> dict:
    """Cron entry point — generate today's queue for every eligible user."""
    users = await list_active_users()
    print(f"MORNING_QUEUE: {len(users)} active users eligible for queue generation")

    generated = skipped = failed = 0
    for user_id in users:
        try:
            result = await generate_queue_for_user(user_id)
            if result["status"] == "ok":
                generated += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                failed += 1
            print(f"MORNING_QUEUE: user={user_id} status={result['status']} items={result.get('items_created', 0)}")
        except Exception as e:
            failed += 1
            print(f"MORNING_QUEUE: user={user_id} FAILED: {e}")

    return {"total_users": len(users), "generated": generated, "skipped": skipped, "failed": failed}


# ─── Reading + acting on the queue ──────────────────────────────────────

async def list_queue_items(user_id: str) -> dict:
    """Returns {"today": [...], "yesterday": [...]}."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"today": [], "yesterday": []}

    user_uuid = _user_id_to_uuid(user_id)
    today = _today()
    yesterday = today - timedelta(days=1)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers=_read_headers(),
                params={
                    "select": "*",
                    "user_id": f"eq.{user_uuid}",
                    "date": f"in.({today.isoformat()},{yesterday.isoformat()})",
                    "order": "created_at.desc",
                },
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"MORNING_QUEUE: list items error: {e}")
        rows = []

    today_iso, yesterday_iso = today.isoformat(), yesterday.isoformat()
    return {
        "today": [r for r in rows if r.get("date") == today_iso],
        "yesterday": [r for r in rows if r.get("date") == yesterday_iso],
    }


async def unread_count(user_id: str) -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    user_uuid = _user_id_to_uuid(user_id)
    yesterday_iso = (_today() - timedelta(days=1)).isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers={**_read_headers(), "Prefer": "count=exact"},
                params={
                    "select": "id",
                    "user_id": f"eq.{user_uuid}",
                    "read": "eq.false",
                    "date": f"gte.{yesterday_iso}",
                },
                timeout=10.0,
            )
        if resp.status_code in (200, 206):
            content_range = resp.headers.get("content-range", "")
            if "/" in content_range:
                return int(content_range.split("/")[-1])
            return len(resp.json())
    except Exception as e:
        print(f"MORNING_QUEUE: unread count error: {e}")
    return 0


async def mark_read(user_id: str, item_id: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    user_uuid = _user_id_to_uuid(user_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{item_id}", "user_id": f"eq.{user_uuid}"},
                json={"read": True},
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"MORNING_QUEUE: mark read error: {e}")
        return False


async def mark_all_read(user_id: str) -> bool:
    """Mark today + yesterday's items read — called when the Morning Queue modal opens."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    user_uuid = _user_id_to_uuid(user_id)
    yesterday_iso = (_today() - timedelta(days=1)).isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"user_id": f"eq.{user_uuid}", "read": "eq.false", "date": f"gte.{yesterday_iso}"},
                json={"read": True},
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"MORNING_QUEUE: mark all read error: {e}")
        return False


async def queue_digest_for_prompt(user_id: str) -> str:
    """Short digest of today's queue items for system-prompt injection."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    user_uuid = _user_id_to_uuid(user_id)
    today_iso = _today().isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers=_read_headers(),
                params={
                    "select": "type,title,body",
                    "user_id": f"eq.{user_uuid}",
                    "date": f"eq.{today_iso}",
                    "order": "created_at.asc",
                },
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"MORNING_QUEUE: digest fetch error: {e}")
        rows = []

    if not rows:
        return ""

    lines = "\n".join(f"- [{r['type']}] {r['title']} — {r['body']}" for r in rows)
    return (
        "## Today's Morning Queue\n"
        "Rue already prepared these items for the user this morning. If they reference "
        "\"the queue\", \"what you flagged\", \"this morning's items\" or similar, these are what they mean:\n\n"
        f"{lines}"
    )


async def bury_memory_for_action(user_id: str, item_id: str) -> dict:
    """Mark an item read, bury a memory that the user acted on it, and return its action_prompt."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "action_prompt": ""}
    user_uuid = _user_id_to_uuid(user_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/morning_queue_items",
                headers=_read_headers(),
                params={
                    "select": "title,body,action_prompt",
                    "id": f"eq.{item_id}",
                    "user_id": f"eq.{user_uuid}",
                    "limit": "1",
                },
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
        if not rows:
            return {"ok": False, "action_prompt": ""}
        item = rows[0]

        await mark_read(user_id, item_id)

        memory = f"User acted on a Morning Queue item: \"{item['title']}\" — {item['body']}"
        async with httpx.AsyncClient() as client:
            ins = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_write_headers(),
                json={"user_id": user_uuid, "memory": memory, "category": "morning_queue_action"},
                timeout=10.0,
            )
        ins_rows = ins.json() if ins.status_code in (200, 201) else []
        if ins_rows:
            await process_new_memory(user_uuid, ins_rows[0]["id"], memory)

        return {"ok": True, "action_prompt": item.get("action_prompt", "")}
    except Exception as e:
        print(f"MORNING_QUEUE: bury memory error: {e}")
        return {"ok": False, "action_prompt": ""}
