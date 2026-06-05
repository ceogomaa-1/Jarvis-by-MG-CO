"""
Readiness, autonomous mode, and proactive insights API.

  GET   /business/readiness?user_id=...            → readiness score (0–100)
  POST  /business/autonomous/toggle                → enable/disable autonomous mode
  GET   /business/proactive/unread?user_id=...     → unread proactive insights
  PATCH /business/proactive/{id}/read              → mark insight as read

Requires Supabase table: business_proactive_insights
  (id uuid PK, user_id uuid, message text, type text, is_read bool default false, created_at timestamptz default now())
"""
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.lib.business.readiness import calculate_readiness
from backend.lib.business.brand_config import upsert_brand_config

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

router = APIRouter()


def _headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


# ════════════════════════════════════════════════════════════════════
# Readiness score
# ════════════════════════════════════════════════════════════════════

@router.get("/business/readiness")
async def get_readiness(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await calculate_readiness(user_id)


# ════════════════════════════════════════════════════════════════════
# Autonomous mode toggle
# ════════════════════════════════════════════════════════════════════

class ToggleRequest(BaseModel):
    user_id: str
    enabled: bool


@router.post("/business/autonomous/toggle")
async def toggle_autonomous(request: ToggleRequest, background_tasks: BackgroundTasks):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    await upsert_brand_config(request.user_id, {"operator_enabled": request.enabled})
    if request.enabled:
        background_tasks.add_task(_generate_proactive_insight, request.user_id)
    return {"autonomous_enabled": request.enabled}


# ════════════════════════════════════════════════════════════════════
# Proactive insights
# ════════════════════════════════════════════════════════════════════

@router.get("/business/proactive/unread")
async def get_unread_insights(user_id: str = ""):
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"messages": []}
    user_uuid = _user_id_to_uuid(user_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_proactive_insights",
                headers=_headers(),
                params={
                    "select": "*",
                    "user_id": f"eq.{user_uuid}",
                    "is_read": "eq.false",
                    "order": "created_at.desc",
                    "limit": "5",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return {"messages": resp.json()}
    except Exception as e:
        print(f"READINESS: get_unread_insights error: {e}")
    return {"messages": []}


@router.patch("/business/proactive/{insight_id}/read")
async def mark_insight_read(insight_id: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_proactive_insights?id=eq.{insight_id}",
                headers={
                    **_headers(),
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"is_read": True},
                timeout=10.0,
            )
        return {"ok": resp.status_code in (200, 204)}
    except Exception as e:
        print(f"READINESS: mark_insight_read error: {e}")
        return {"ok": False}


# ════════════════════════════════════════════════════════════════════
# Proactive insight generation (background task)
# ════════════════════════════════════════════════════════════════════

async def _generate_proactive_insight(user_id: str) -> None:
    """
    Generate one proactive insight from Jarvis based on user's accumulated context.
    Called as a background task when autonomous mode is enabled.
    """
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY or not ANTHROPIC_API_KEY:
        return

    user_uuid = _user_id_to_uuid(user_id)

    try:
        async with httpx.AsyncClient() as client:
            # Gather context
            mem_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_headers(),
                params={
                    "select": "memory",
                    "user_id": f"eq.{user_uuid}",
                    "order": "created_at.desc",
                    "limit": "20",
                },
                timeout=10.0,
            )
            memories = mem_resp.json() if mem_resp.status_code == 200 else []
            memory_text = "\n".join(f"- {m['memory']}" for m in memories) or "No memories yet."

            brand_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_brand_config",
                headers=_headers(),
                params={
                    "select": "north_star_target_usd,display_name",
                    "user_id": f"eq.{user_uuid}",
                    "limit": "1",
                },
                timeout=10.0,
            )
            brand_rows = brand_resp.json() if brand_resp.status_code == 200 else []
            north_star = brand_rows[0].get("north_star_target_usd", 1000000) if brand_rows else 1000000

            prompt = f"""You are Jarvis OS1, an AI business operator proactively reaching out to your user with a helpful insight.

Context about this user:
{memory_text}

Their North Star revenue target: ${north_star:,.0f}/year

Generate ONE proactive message. It should be:
- Specific to their business (not generic advice)
- Actionable (something they can do today or this week)
- Tied to revenue growth or operational improvement
- Brief (2-4 sentences max)
- Conversational and direct

Return ONLY the message text, nothing else."""

            ai_resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )

            if ai_resp.status_code != 200:
                print(f"READINESS: insight generation AI error {ai_resp.status_code}")
                return

            message_text = ai_resp.json().get("content", [{}])[0].get("text", "").strip()
            if not message_text:
                return

            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_proactive_insights",
                headers={
                    **_headers(),
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "user_id": user_uuid,
                    "message": message_text,
                    "type": "proactive_insight",
                    "is_read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
            print(f"READINESS: proactive insight generated for {user_id}")

    except Exception as e:
        print(f"READINESS: _generate_proactive_insight error: {e}")
