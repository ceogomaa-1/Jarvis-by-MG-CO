"""
Operator Agent API.

  GET   /business/operator/pending              → pending actions for user
  POST  /business/operator/trigger              → manually trigger a run (returns run_id immediately)
  GET   /business/operator/status/stream        → SSE stream of run lifecycle events
  PATCH /business/operator/actions/{id}         → update action status (ship/discard/edit)
  GET   /business/operator/runs                 → recent run history
"""
import asyncio
import json
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib.business.operator.loop import run_operator_for_user, create_operator_run_row

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Maps cycles_completed value to the agent node ID that is currently active
_CYCLE_TO_STAGE = {
    0: "operator-strategist",
    1: "operator-researcher",
    2: "operator-creator",
    3: "operator-packager",
}


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
async def trigger_run(request: TriggerRunRequest, background_tasks: BackgroundTasks):
    """
    Trigger an operator run. Creates the run row immediately and returns run_id
    so the frontend can open the SSE status stream without waiting for the run to finish.
    """
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    run_id = await create_operator_run_row(request.user_id)
    if not run_id:
        raise HTTPException(status_code=500, detail="Failed to create run record")

    background_tasks.add_task(run_operator_for_user, request.user_id, run_id)

    return {"run_id": run_id, "status": "started"}


@router.get("/business/operator/status/stream")
async def stream_run_status(run_id: str, user_id: str = ""):
    """
    SSE endpoint that streams run stage updates.
    Polls Supabase every second; closes when the run reaches a terminal state.
    Maps cycles_completed → agent node ID so the frontend can light up the correct node.
    """
    async def event_generator():
        last_cycles = -1
        last_status = ""

        for _ in range(600):  # Max 10 minutes
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{SUPABASE_URL}/rest/v1/business_operator_runs",
                        headers=_headers(),
                        params={
                            "select": "id,status,cycles_completed",
                            "id": f"eq.{run_id}",
                            "limit": "1",
                        },
                        timeout=5.0,
                    )
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        run = rows[0]
                        cycles = run.get("cycles_completed") or 0
                        status = run.get("status", "running")

                        if cycles != last_cycles or status != last_status:
                            last_cycles = cycles
                            last_status = status
                            stage = _CYCLE_TO_STAGE.get(cycles, "operator-strategist")
                            yield f"data: {json.dumps({'run_id': run_id, 'stage': stage, 'cycles_completed': cycles, 'status': status})}\n\n"

                        if status in ("complete", "failed", "budget_capped"):
                            # Final event already emitted above; close stream
                            break
            except Exception as e:
                print(f"OPERATOR_ROUTES: SSE poll error: {e}")

            await asyncio.sleep(1)
        else:
            # The 10-minute cap was reached without a terminal status. Emit an explicit
            # timeout sentinel so the frontend EventSource can stop cleanly instead of
            # seeing a silent close it has to guess at.
            yield f"data: {json.dumps({'run_id': run_id, 'status': 'timeout', 'stage': 'operator-timeout', 'cycles_completed': last_cycles if last_cycles >= 0 else 0})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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
