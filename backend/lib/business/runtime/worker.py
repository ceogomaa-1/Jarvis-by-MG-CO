"""Lease-based runtime dispatcher.

The scheduler may run this on every API replica. Postgres atomically assigns
each job to one worker, and expired leases make interrupted work recoverable.
"""
from __future__ import annotations

import asyncio
import os
import socket
import uuid

from backend.lib.business.runtime import store
from backend.lib.business.runtime.handlers import (
    NonRetryableWorkflowError,
    RetryableWorkflowError,
    run_event_handler,
    run_workflow_handler,
)

WORKER_NAME = os.getenv("OS1_WORKER_NAME") or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
WORKFLOW_CONCURRENCY = min(max(int(os.getenv("OS1_WORKFLOW_CONCURRENCY", "2")), 1), 8)
WORKFLOW_LEASE_SECONDS = min(max(int(os.getenv("OS1_WORKFLOW_LEASE_SECONDS", "1800")), 120), 7200)

_dispatch_lock = asyncio.Lock()


async def _lease_heartbeat(workflow_id: str) -> None:
    interval = max(min(WORKFLOW_LEASE_SECONDS // 3, 300), 30)
    while True:
        await asyncio.sleep(interval)
        ok = await store.extend_workflow_lease(workflow_id, WORKER_NAME, WORKFLOW_LEASE_SECONDS)
        if not ok:
            return


async def _execute_claimed_workflow(workflow: dict) -> dict:
    heartbeat = asyncio.create_task(_lease_heartbeat(workflow["id"]))
    try:
        await store.append_workflow_event(
            workflow["id"],
            "workflow_started",
            from_status="queued",
            to_status="running",
            data={"attempt": workflow.get("attempts"), "worker": WORKER_NAME},
        )
        output = await run_workflow_handler(workflow)
        completed = await store.complete_workflow(workflow, output)
        return {
            "workflow_id": workflow["id"],
            "status": "succeeded" if completed else "lease_lost",
        }
    except NonRetryableWorkflowError as exc:
        result = await store.fail_workflow(workflow, str(exc), retryable=False)
        return {"workflow_id": workflow["id"], **result}
    except RetryableWorkflowError as exc:
        result = await store.fail_workflow(workflow, str(exc), retryable=True)
        return {"workflow_id": workflow["id"], **result}
    except Exception as exc:
        result = await store.fail_workflow(workflow, f"Unhandled {type(exc).__name__}: {exc}", retryable=True)
        return {"workflow_id": workflow["id"], **result}
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


async def dispatch_due_workflows(limit: int | None = None) -> dict:
    """Claim and execute one bounded batch. Never overlaps within a process."""
    if _dispatch_lock.locked():
        return {"status": "busy", "claimed": 0, "results": []}
    async with _dispatch_lock:
        try:
            claimed = await store.claim_workflows(
                WORKER_NAME,
                limit=limit or WORKFLOW_CONCURRENCY,
                lease_seconds=WORKFLOW_LEASE_SECONDS,
            )
        except store.RuntimeUnavailable as exc:
            # Batch 77 may not be deployed yet during rolling release.
            return {"status": "unavailable", "claimed": 0, "error": str(exc), "results": []}
        results = await asyncio.gather(*[_execute_claimed_workflow(item) for item in claimed]) if claimed else []
        return {"status": "ok", "claimed": len(claimed), "results": results}


async def dispatch_due_events(limit: int = 20) -> dict:
    try:
        events = await store.claim_events(WORKER_NAME, limit=limit)
    except store.RuntimeUnavailable as exc:
        return {"status": "unavailable", "claimed": 0, "error": str(exc)}
    results = []
    for event in events:
        try:
            output = await run_event_handler(event)
            await store.finish_event(event)
            results.append({"event_id": event["id"], "status": "processed", "output": output})
        except NonRetryableWorkflowError as exc:
            terminal = {**event, "attempts": event.get("max_attempts", 5)}
            await store.finish_event(terminal, error=str(exc))
            results.append({"event_id": event["id"], "status": "dead_letter", "error": str(exc)})
        except Exception as exc:
            await store.finish_event(event, error=str(exc))
            results.append({"event_id": event["id"], "status": "retrying", "error": str(exc)})
    return {"status": "ok", "claimed": len(events), "results": results}


async def dispatch_runtime_tick() -> dict:
    events = await dispatch_due_events()
    workflows = await dispatch_due_workflows()
    return {"events": events, "workflows": workflows}
