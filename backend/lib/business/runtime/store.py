"""Postgres-backed durable workflow/event store.

All claims happen through Batch 77 RPC functions using FOR UPDATE SKIP LOCKED.
That makes multiple API replicas safe and lets expired work resume after a crash.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.lib.business.goal_engine import ensure_primary_business

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 15.0


class RuntimeUnavailable(RuntimeError):
    pass


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _ready() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeUnavailable("Supabase is not configured")


async def append_workflow_event(
    workflow_id: str,
    event_type: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    message: str = "",
    data: dict | None = None,
) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_workflow_events",
                headers=_headers("return=minimal"),
                json={
                    "workflow_id": workflow_id,
                    "event_type": event_type,
                    "from_status": from_status,
                    "to_status": to_status,
                    "message": message[:1000],
                    "data": data or {},
                },
                timeout=TIMEOUT,
            )
    except Exception as exc:
        print(f"OS1_RUNTIME: append event failed: {exc}")


async def update_workflow_step(
    workflow_id: str,
    step_key: str,
    status: str,
    *,
    output: dict | None = None,
    error: str | None = None,
) -> bool:
    """Persist live progress without making step rows the execution authority.

    The Operator's cycle outputs remain its durable checkpoints. These rows are
    the inspectable timeline that mirrors those checkpoints for the UI and ops.
    """
    _ready()
    if status not in {"pending", "running", "waiting", "succeeded", "failed", "skipped"}:
        raise ValueError(f"Unsupported workflow step status: {status}")
    now = datetime.now(timezone.utc).isoformat()
    patch: dict[str, Any] = {"status": status, "last_error": error[:2000] if error else None}
    if output is not None:
        patch["output"] = output
    if status == "running":
        patch.update({"started_at": now, "completed_at": None})
    elif status in {"succeeded", "failed", "skipped"}:
        patch["completed_at"] = now

    async with httpx.AsyncClient() as client:
        step_response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflow_steps",
            headers=_headers("return=representation"),
            params={"workflow_id": f"eq.{workflow_id}", "step_key": f"eq.{step_key}"},
            json=patch,
            timeout=TIMEOUT,
        )
        if step_response.status_code not in (200, 204):
            return False
        rows = step_response.json() if step_response.content else []
        if not rows:
            return False
        workflow_patch = {"current_step": None if status == "succeeded" and step_key == "finalize" else step_key}
        workflow_response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{workflow_id}", "status": "eq.running"},
            json=workflow_patch,
            timeout=TIMEOUT,
        )
    return workflow_response.status_code in (200, 204)


async def complete_workflow_steps(
    workflow_id: str,
    output: dict | None = None,
    *,
    terminal_status: str = "succeeded",
) -> None:
    """Reconcile every remaining step after an idempotent successful retry."""
    _ready()
    if terminal_status not in {"succeeded", "skipped"}:
        raise ValueError("Workflow step reconciliation must succeed or skip steps")
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflow_steps",
            headers=_headers("return=minimal"),
            params={"workflow_id": f"eq.{workflow_id}", "status": "in.(pending,running,waiting)"},
            json={"status": terminal_status, "completed_at": now, "last_error": None, "output": output or {}},
            timeout=TIMEOUT,
        )


async def enqueue_workflow(
    user_id: str,
    kind: str,
    input_data: dict,
    *,
    idempotency_key: str,
    goal_id: str | None = None,
    initiative_id: str | None = None,
    priority: int = 50,
    max_attempts: int = 5,
    run_after: str | None = None,
    steps: list[dict] | None = None,
) -> dict:
    _ready()
    business = await ensure_primary_business(user_id)
    payload = {
        "business_id": business["id"],
        "goal_id": goal_id,
        "initiative_id": initiative_id,
        "kind": kind,
        "status": "queued",
        "priority": min(max(int(priority), 0), 100),
        "input": input_data,
        "idempotency_key": idempotency_key,
        "max_attempts": min(max(int(max_attempts), 1), 20),
        "run_after": run_after or datetime.now(timezone.utc).isoformat(),
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_workflows?on_conflict=business_id,idempotency_key",
            headers=_headers("resolution=ignore-duplicates,return=representation"),
            json=payload,
            timeout=TIMEOUT,
        )
        if response.status_code not in (200, 201):
            raise RuntimeUnavailable(f"Batch 77 runtime unavailable: {response.text[:180]}")
        rows = response.json()
        if rows:
            workflow = rows[0]
            created = True
        else:
            existing = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_workflows",
                headers=_headers(),
                params={
                    "select": "*",
                    "business_id": f"eq.{business['id']}",
                    "idempotency_key": f"eq.{idempotency_key}",
                    "limit": "1",
                },
                timeout=TIMEOUT,
            )
            if existing.status_code != 200 or not existing.json():
                raise RuntimeUnavailable("Workflow upsert returned no durable record")
            workflow = existing.json()[0]
            created = False

        if created and steps:
            step_rows = []
            for position, step in enumerate(steps):
                key = str(step.get("step_key") or f"step_{position + 1}")
                step_rows.append({
                    "workflow_id": workflow["id"],
                    "step_key": key,
                    "handler": str(step.get("handler") or key),
                    "position": position,
                    "input": step.get("input") or {},
                    "max_attempts": min(max(int(step.get("max_attempts", 3)), 1), 10),
                    "idempotency_key": step.get("idempotency_key") or f"{idempotency_key}:{key}",
                })
            step_response = await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_workflow_steps",
                headers=_headers("return=minimal"),
                json=step_rows,
                timeout=TIMEOUT,
            )
            if step_response.status_code not in (200, 201, 204):
                raise RuntimeUnavailable(f"Could not persist workflow steps: {step_response.text[:180]}")
    if created:
        await append_workflow_event(workflow["id"], "workflow_queued", to_status="queued", data={"kind": kind})
    workflow["created_now"] = created
    return workflow


async def claim_workflows(worker_name: str, limit: int = 2, lease_seconds: int = 1800) -> list[dict]:
    _ready()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/claim_os1_workflows",
            headers=_headers(),
            json={"worker_name": worker_name, "claim_limit": limit, "lease_seconds": lease_seconds},
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        raise RuntimeUnavailable(f"Workflow claim failed: {response.text[:180]}")
    return response.json() or []


async def extend_workflow_lease(workflow_id: str, worker_name: str, lease_seconds: int = 1800) -> bool:
    expires = datetime.now(timezone.utc) + timedelta(seconds=max(lease_seconds, 30))
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers("return=representation"),
            params={"id": f"eq.{workflow_id}", "status": "eq.running", "lease_owner": f"eq.{worker_name}"},
            json={"lease_expires_at": expires.isoformat()},
            timeout=TIMEOUT,
        )
    return response.status_code == 200 and bool(response.json())


async def complete_workflow(workflow: dict, output: dict | None = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers("return=representation"),
            params={
                "id": f"eq.{workflow['id']}",
                "status": "eq.running",
                "lease_owner": f"eq.{workflow.get('lease_owner')}",
            },
            json={
                "status": "succeeded",
                "output": output or {},
                "completed_at": now,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error": None,
            },
            timeout=TIMEOUT,
        )
    ok = response.status_code == 200 and bool(response.json())
    if ok:
        await append_workflow_event(
            workflow["id"], "workflow_succeeded", from_status="running", to_status="succeeded", data=output or {}
        )
    return ok


async def fail_workflow(workflow: dict, error: str, *, retryable: bool = True) -> dict:
    attempts = int(workflow.get("attempts") or 1)
    max_attempts = int(workflow.get("max_attempts") or 5)
    will_retry = retryable and attempts < max_attempts
    status = "queued" if will_retry else "dead_letter"
    delay_seconds = min(60 * (2 ** max(attempts - 1, 0)), 3600)
    payload: dict[str, Any] = {
        "status": status,
        "last_error": str(error)[:2000],
        "lease_owner": None,
        "lease_expires_at": None,
    }
    if will_retry:
        payload["run_after"] = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
    else:
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers("return=representation"),
            params={
                "id": f"eq.{workflow['id']}",
                "status": "eq.running",
                "lease_owner": f"eq.{workflow.get('lease_owner')}",
            },
            json=payload,
            timeout=TIMEOUT,
        )
    updated = response.status_code == 200 and bool(response.json())
    if updated:
        await append_workflow_event(
            workflow["id"],
            "workflow_retry_scheduled" if will_retry else "workflow_dead_lettered",
            from_status="running",
            to_status=status,
            message=str(error),
            data={"attempts": attempts, "max_attempts": max_attempts, "retry_delay_seconds": delay_seconds if will_retry else None},
        )
    return {"ok": updated, "retrying": will_retry if updated else False, "status": status if updated else "lease_lost"}


async def deny_workflow(workflow: dict, decision: dict) -> bool:
    """Cancel work that the autonomy governor refused; denial is not a crash."""
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers("return=representation"),
            params={
                "id": f"eq.{workflow['id']}",
                "status": "eq.running",
                "lease_owner": f"eq.{workflow.get('lease_owner')}",
            },
            json={
                "status": "cancelled",
                "output": {"autonomy_decision": decision},
                "last_error": str(decision.get("reason") or "Autonomy denied")[:2000],
                "completed_at": now,
                "lease_owner": None,
                "lease_expires_at": None,
            },
            timeout=TIMEOUT,
        )
    updated = response.status_code == 200 and bool(response.json())
    if updated:
        await append_workflow_event(
            workflow["id"],
            "workflow_denied",
            from_status="running",
            to_status="cancelled",
            message=str(decision.get("reason") or "Autonomy denied"),
            data=decision,
        )
    return updated


async def get_workflow(user_id: str, workflow_id: str) -> dict | None:
    business = await ensure_primary_business(user_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers(),
            params={"select": "*", "id": f"eq.{workflow_id}", "business_id": f"eq.{business['id']}", "limit": "1"},
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        raise RuntimeUnavailable(f"Workflow lookup failed: {response.text[:180]}")
    return response.json()[0] if response.json() else None


async def list_workflows(user_id: str, limit: int = 30) -> list[dict]:
    business = await ensure_primary_business(user_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_workflows",
            headers=_headers(),
            params={
                "select": "*",
                "business_id": f"eq.{business['id']}",
                "order": "created_at.desc",
                "limit": str(min(max(limit, 1), 100)),
            },
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        raise RuntimeUnavailable(f"Workflow list failed: {response.text[:180]}")
    return response.json()


async def emit_event(
    user_id: str,
    event_type: str,
    payload: dict,
    *,
    idempotency_key: str,
    source: str = "rue",
    subject_type: str | None = None,
    subject_id: str | None = None,
) -> dict:
    business = await ensure_primary_business(user_id)
    row = {
        "business_id": business["id"],
        "event_type": event_type,
        "source": source,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "payload": payload,
        "idempotency_key": idempotency_key,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_events?on_conflict=business_id,idempotency_key",
            headers=_headers("resolution=ignore-duplicates,return=representation"),
            json=row,
            timeout=TIMEOUT,
        )
        if response.status_code not in (200, 201):
            raise RuntimeUnavailable(f"Event write failed: {response.text[:180]}")
        if response.json():
            return response.json()[0]
        existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_events",
            headers=_headers(),
            params={"select": "*", "business_id": f"eq.{business['id']}", "idempotency_key": f"eq.{idempotency_key}", "limit": "1"},
            timeout=TIMEOUT,
        )
    if existing.status_code == 200 and existing.json():
        return existing.json()[0]
    raise RuntimeUnavailable("Event upsert returned no durable record")


async def claim_events(worker_name: str, limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/claim_os1_events",
            headers=_headers(),
            json={"worker_name": worker_name, "claim_limit": limit, "lease_seconds": 120},
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        raise RuntimeUnavailable(f"Event claim failed: {response.text[:180]}")
    return response.json() or []


async def finish_event(event: dict, *, error: str | None = None) -> None:
    attempts = int(event.get("attempts") or 1)
    max_attempts = int(event.get("max_attempts") or 5)
    if error and attempts < max_attempts:
        status = "pending"
        available_at = datetime.now(timezone.utc) + timedelta(seconds=min(30 * 2 ** (attempts - 1), 900))
        patch = {"status": status, "available_at": available_at.isoformat(), "last_error": error[:2000]}
    elif error:
        patch = {"status": "dead_letter", "last_error": error[:2000], "processed_at": datetime.now(timezone.utc).isoformat()}
    else:
        patch = {"status": "processed", "last_error": None, "processed_at": datetime.now(timezone.utc).isoformat()}
    patch.update({"lease_owner": None, "lease_expires_at": None})
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_events",
            headers=_headers("return=minimal"),
            params={
                "id": f"eq.{event['id']}",
                "status": "eq.processing",
                "lease_owner": f"eq.{event.get('lease_owner')}",
            },
            json=patch,
            timeout=TIMEOUT,
        )
