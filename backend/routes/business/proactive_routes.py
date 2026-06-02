"""
API routes for the business proactive briefing system + metrics input.

Endpoints:
  GET   /business/proactive/latest?user_id=...   -> latest unread briefing (or null)
  POST  /business/proactive/mark-read            -> mark briefing read
  GET   /business/metrics?user_id=...            -> current metrics blob
  POST  /business/metrics                        -> upsert metrics blob
"""
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

router = APIRouter()


def _auth_headers(prefer_minimal: bool = False) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer_minimal:
        h["Prefer"] = "return=minimal"
    return h


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


# ════════════════════════════════════════════════════════════════════
# Proactive briefings
# ════════════════════════════════════════════════════════════════════

@router.get("/business/proactive/latest")
async def get_latest_briefing(user_id: str = ""):
    """Return the most recent unread briefing for the user, or null if none."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"briefing": None}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_proactive_messages",
                headers=_read_headers(),
                params={
                    "select": "id,briefing_text,flag_severity,flag_summary,suggested_action,read,created_at",
                    "user_id": f"eq.{user_id}",
                    "read": "eq.false",
                    "order": "created_at.desc",
                    "limit": "1",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            return {"briefing": None}
        rows = resp.json()
        return {"briefing": rows[0] if rows else None}
    except Exception as e:
        print(f"PROACTIVE: get_latest_briefing error: {e}")
        return {"briefing": None}


class MarkReadRequest(BaseModel):
    briefing_id: str
    user_id: str = ""


@router.post("/business/proactive/mark-read")
async def mark_briefing_read(request: MarkReadRequest):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_proactive_messages?id=eq.{request.briefing_id}",
                headers=_auth_headers(prefer_minimal=True),
                json={"read": True},
                timeout=10.0,
            )
        return {"ok": resp.status_code in (200, 204)}
    except Exception as e:
        print(f"PROACTIVE: mark_read error: {e}")
        return {"ok": False}


# ════════════════════════════════════════════════════════════════════
# Metrics input
# ════════════════════════════════════════════════════════════════════

@router.get("/business/metrics")
async def get_metrics(user_id: str = ""):
    """Return the user's current metrics blob."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"metrics_text": "", "updated_at": None}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_metrics",
                headers=_read_headers(),
                params={"select": "metrics_text,updated_at", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return {"metrics_text": "", "updated_at": None}
        rows = resp.json()
        if rows:
            return {"metrics_text": rows[0].get("metrics_text", ""), "updated_at": rows[0].get("updated_at")}
        return {"metrics_text": "", "updated_at": None}
    except Exception as e:
        print(f"PROACTIVE: get_metrics error: {e}")
        return {"metrics_text": "", "updated_at": None}


class SaveMetricsRequest(BaseModel):
    user_id: str
    metrics_text: str


@router.post("/business/metrics")
async def save_metrics(request: SaveMetricsRequest):
    """Upsert the user's metrics blob."""
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_user_metrics",
                headers={
                    **_auth_headers(),
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                json={
                    "user_id": request.user_id,
                    "metrics_text": request.metrics_text or "",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
        if resp.status_code not in (200, 201, 204):
            raise HTTPException(status_code=502, detail=f"Supabase {resp.status_code}: {resp.text[:200]}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"PROACTIVE: save_metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
