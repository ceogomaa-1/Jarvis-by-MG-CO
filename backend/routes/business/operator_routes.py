"""
Operator Agent API (Batch 71: Co-Founder Mode).

  GET   /business/operator/pending              → pending initiatives for user
  POST  /business/operator/trigger              → manually trigger a run (returns run_id immediately)
  GET   /business/operator/status/stream        → SSE stream of run lifecycle events
  POST  /business/operator/actions/{id}/approve → APPROVE: Rue executes the initiative for real
  GET   /business/operator/actions/{id}         → one initiative (poll while executing)
  GET   /business/operator/activity             → recently executed initiatives (the receipts)
  PATCH /business/operator/actions/{id}         → update action status (ship/discard/edit + decline reason)
  GET   /business/operator/runs                 → recent run history
"""
import asyncio
import json
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib.business.operator.executor_agent import execute_initiative
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


def _normalize_action(row: dict) -> dict:
    """Ensure execution_plan / expected_impact are present even on pre-migration
    rows (where they only live inside artifact_metadata)."""
    meta = row.get("artifact_metadata") or {}
    if not row.get("execution_plan"):
        row["execution_plan"] = meta.get("execution_plan") or {}
    if not row.get("expected_impact"):
        row["expected_impact"] = meta.get("expected_impact") or ""
    return row


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
                    # select * so this works before AND after the batch71 migration
                    "select": "*",
                    "user_id": f"eq.{user_id}",
                    "status": "in.(pending,executing)",
                    "order": "priority.asc,created_at.desc",
                    "limit": str(min(limit, 50)),
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return {"actions": [_normalize_action(r) for r in resp.json()]}
    except Exception as e:
        print(f"OPERATOR_ROUTES: get_pending_actions exception: {e}")
    return {"actions": []}


@router.get("/business/operator/activity")
async def get_activity(user_id: str = "", limit: int = 12):
    """The receipts: initiatives Rue actually executed (or failed), newest first."""
    if not user_id:
        return {"actions": []}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={
                    "select": "*",
                    "user_id": f"eq.{user_id}",
                    "status": "in.(executed,execution_failed,shipped)",
                    "order": "created_at.desc",
                    "limit": str(min(limit, 30)),
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = [_normalize_action(r) for r in resp.json()]
            # Legacy 'shipped' rows carry results in shipped_result
            for r in rows:
                if not r.get("execution_result") and r.get("shipped_result"):
                    r["execution_result"] = r["shipped_result"]
            return {"actions": rows}
    except Exception as e:
        print(f"OPERATOR_ROUTES: get_activity exception: {e}")
    return {"actions": []}


@router.get("/business/operator/actions/{action_id}")
async def get_action(action_id: str, user_id: str = ""):
    """Poll one initiative — the frontend watches this while Rue executes."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={"select": "*", "id": f"eq.{action_id}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code == 200 and resp.json():
            row = resp.json()[0]
            if user_id and str(row.get("user_id")) != str(user_id):
                raise HTTPException(status_code=403, detail="Not your initiative")
            row = _normalize_action(row)
            if not row.get("execution_result") and row.get("shipped_result"):
                row["execution_result"] = row["shipped_result"]
            return {"action": row}
    except HTTPException:
        raise
    except Exception as e:
        print(f"OPERATOR_ROUTES: get_action exception: {e}")
    raise HTTPException(status_code=404, detail="Initiative not found")


class ApproveRequest(BaseModel):
    user_id: str


@router.post("/business/operator/actions/{action_id}/approve")
async def approve_and_execute(action_id: str, request: ApproveRequest, background_tasks: BackgroundTasks):
    """The moment that matters: the owner approved — Rue executes for real.

    Returns immediately; the Executor agent runs in the background. The
    frontend polls GET /business/operator/actions/{id} for the receipts.
    """
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    # Validate ownership + approvability up front so the click gets an honest answer.
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={"select": "id,user_id,status", "id": f"eq.{action_id}", "limit": "1"},
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {e}")
    if not rows:
        raise HTTPException(status_code=404, detail="Initiative not found")
    row = rows[0]
    if str(row.get("user_id")) != str(request.user_id):
        raise HTTPException(status_code=403, detail="Not your initiative")
    if row.get("status") not in ("pending", "edited", "execution_failed"):
        raise HTTPException(status_code=409, detail=f"Initiative is already {row.get('status')}")

    background_tasks.add_task(execute_initiative, action_id, request.user_id)
    return {"ok": True, "status": "executing", "action_id": action_id}


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
    decline_reason: str | None = None  # captured on discard — the strategist learns from it


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
    if request.decline_reason:
        payload["decline_reason"] = request.decline_reason[:500]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions?id=eq.{action_id}",
                headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=payload,
                timeout=10.0,
            )
            if resp.status_code not in (200, 204) and "decline_reason" in payload:
                # Pre-migration fallback: retry without the batch71 column.
                payload.pop("decline_reason", None)
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


# ════════════════════════════════════════════════════════════════════
# Co-founder questions (Batch 72) — THE DETECTIVE
# ════════════════════════════════════════════════════════════════════

@router.get("/business/cofounder/questions")
async def get_cofounder_questions(user_id: str = "", status: str = "open"):
    if not user_id:
        return {"questions": []}
    from backend.lib.business.cofounder_questions import list_questions
    if status not in ("open", "answered", "dismissed"):
        status = "open"
    return {"questions": await list_questions(user_id, status=status)}


class AnswerQuestionRequest(BaseModel):
    user_id: str
    answer: str


@router.post("/business/cofounder/questions/{question_id}/answer")
async def answer_cofounder_question(question_id: str, request: AnswerQuestionRequest):
    """The owner answers — the fact goes on record and feeds every future scan."""
    if not request.user_id or not request.answer.strip():
        raise HTTPException(status_code=400, detail="user_id and answer required")
    from backend.lib.business.cofounder_questions import resolve_question
    ok = await resolve_question(question_id, request.user_id, answer=request.answer.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found (or not yours)")
    return {"ok": True}


class DismissQuestionRequest(BaseModel):
    user_id: str


@router.post("/business/cofounder/questions/{question_id}/dismiss")
async def dismiss_cofounder_question(question_id: str, request: DismissQuestionRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    from backend.lib.business.cofounder_questions import resolve_question
    ok = await resolve_question(question_id, request.user_id, answer=None)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found (or not yours)")
    return {"ok": True}
