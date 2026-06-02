"""
Operator Agent API.

  GET   /business/operator/pending         → pending actions for user
  POST  /business/operator/trigger         → manually trigger a run (testing)
  PATCH /business/operator/actions/{id}    → update action status (ship/discard/edit)
  GET   /business/operator/runs            → recent run history
"""
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.business.operator.loop import run_operator_for_user

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


@router.get("/business/operator/pending")
async def get_pending_actions(user_id: str = "", limit: int = 20):
    if not user_id:
        return {"actions": []}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={
                    "select": "id,action_type,title,description,internal_or_external,artifact_markdown,connector_type,priority,status,created_at",
                    "user_id": f"eq.{user_id}",
                    "status": "eq.pending",
                    "order": "priority.asc,created_at.desc",
                    "limit": str(min(limit, 50)),
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return {"actions": resp.json()}
    except Exception as e:
        print(f"OPERATOR_ROUTES: get_pending_actions exception: {e}")
    return {"actions": []}


@router.get("/business/operator/runs")
async def get_run_history(user_id: str = "", limit: int = 5):
    if not user_id:
        return {"runs": []}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_operator_runs",
                headers=_headers(),
                params={
                    "select": "id,status,cycles_completed,total_cost_usd,started_at,completed_at,error",
                    "user_id": f"eq.{user_id}",
                    "order": "started_at.desc",
                    "limit": str(min(limit, 10)),
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return {"runs": resp.json()}
    except Exception as e:
        print(f"OPERATOR_ROUTES: get_run_history exception: {e}")
    return {"runs": []}


class TriggerRunRequest(BaseModel):
    user_id: str


@router.post("/business/operator/trigger")
async def trigger_run(request: TriggerRunRequest):
    """Manually trigger an operator run. For testing / manual use only."""
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    result = await run_operator_for_user(request.user_id)
    return result


class UpdateActionRequest(BaseModel):
    status: str  # 'shipped' | 'discarded' | 'edited'
    artifact_markdown: str | None = None


@router.patch("/business/operator/actions/{action_id}")
async def update_action(action_id: str, request: UpdateActionRequest):
    valid_statuses = {"shipped", "discarded", "edited"}
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    payload: dict = {"status": request.status}
    if request.status == "shipped":
        payload["shipped_at"] = "now()"
    if request.artifact_markdown is not None:
        payload["artifact_markdown"] = request.artifact_markdown

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions?id=eq.{action_id}",
                headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=payload,
                timeout=10.0,
            )
        if resp.status_code in (200, 204):
            return {"ok": True}
        return {"ok": False, "error": f"Supabase {resp.status_code}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
