"""
Readiness, autonomous mode, and proactive insights API.

  GET   /business/readiness?user_id=...            → readiness score (0–100)
  POST  /business/autonomous/toggle                → enable/disable autonomous mode
  GET   /business/autonomous/state?user_id=...     → current autonomous mode state
  GET   /business/proactive/unread?user_id=...     → unread proactive insights
  PATCH /business/proactive/{id}/read              → mark insight as read

Requires Supabase table: business_proactive_insights
  (id uuid PK, user_id uuid, message text, type text, is_read bool default false, created_at timestamptz default now())
"""
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.lib.business.readiness import calculate_readiness
from backend.lib.business.brand_config import get_brand_config, upsert_brand_config

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

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
    """Batch 71 (Co-Founder Mode): flipping the lever ON doesn't just set a flag —
    it launches a full Operator run RIGHT NOW (scan → strategy → creation →
    executable initiatives), so within minutes the owner is looking at real
    proposals on real data. Returns run_id so the UI can stream the takeover live."""
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    await upsert_brand_config(request.user_id, {"operator_enabled": request.enabled})

    if not request.enabled:
        return {"autonomous_enabled": False}

    run_id = None
    try:
        from backend.lib.business.operator.loop import (
            create_operator_run_row,
            run_operator_for_user,
        )
        run_id = await create_operator_run_row(request.user_id)
        if run_id:
            background_tasks.add_task(run_operator_for_user, request.user_id, run_id)
    except Exception as e:
        print(f"READINESS: first-flip operator launch failed: {e}")

    return {"autonomous_enabled": True, "first_run_id": run_id}


@router.get("/business/autonomous/state")
async def get_autonomous_state(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    config = await get_brand_config(user_id)
    return {"enabled": bool(config.get("operator_enabled", False))}


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
