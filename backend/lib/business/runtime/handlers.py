"""Workflow and event handlers registered with the durable OS1 runtime."""
from __future__ import annotations

from backend.lib.business.operator.executor_agent import execute_initiative
from backend.lib.business.operator.loop import create_operator_run_row, run_operator_for_user
from backend.lib.business.runtime import store
from backend.lib.business.runtime.definitions import INITIATIVE_EXECUTION_STEPS, OPERATOR_WORKFLOW_STEPS


class NonRetryableWorkflowError(RuntimeError):
    pass


class RetryableWorkflowError(RuntimeError):
    pass


async def run_workflow_handler(workflow: dict) -> dict:
    kind = workflow.get("kind")
    input_data = workflow.get("input") or {}
    if kind == "operator.run":
        user_id = input_data.get("user_id")
        run_id = input_data.get("operator_run_id")
        if not user_id or not run_id:
            raise NonRetryableWorkflowError("operator.run requires user_id and operator_run_id")
        async def report_progress(step_key: str, status: str, data: dict | None = None) -> None:
            await store.update_workflow_step(workflow["id"], step_key, status, output=data)

        result = await run_operator_for_user(
            user_id,
            existing_run_id=run_id,
            notify=bool(input_data.get("notify")),
            progress_callback=report_progress,
        )
        if result.get("status") not in ("complete", "budget_capped"):
            raise RetryableWorkflowError(result.get("error") or f"Operator ended with {result.get('status')}")
        await store.complete_workflow_steps(
            workflow["id"],
            result,
            terminal_status="succeeded" if result.get("status") == "complete" else "skipped",
        )
        return result

    if kind == "initiative.execute":
        user_id = input_data.get("user_id")
        action_id = input_data.get("legacy_action_id")
        if not user_id or not action_id:
            raise NonRetryableWorkflowError("initiative.execute requires user_id and legacy_action_id")
        await store.update_workflow_step(workflow["id"], "execute_approved_scope", "running")
        result = await execute_initiative(
            action_id,
            user_id,
            max_budget_usd=(workflow.get("autonomy_decision") or {}).get("max_workflow_cost_usd"),
            workflow_id=workflow.get("id"),
            business_id=workflow.get("business_id"),
        )
        if not result.get("ok"):
            message = result.get("error") or (result.get("result") or {}).get("error") or "Initiative execution failed"
            lowered = message.lower()
            if any(token in lowered for token in ("not found", "does not belong", "not approvable", "invalid user")):
                raise NonRetryableWorkflowError(message)
            raise RetryableWorkflowError(message)
        await store.update_workflow_step(
            workflow["id"], "execute_approved_scope", "succeeded", output=result
        )
        return result

    raise NonRetryableWorkflowError(f"Unknown workflow kind: {kind}")


async def run_event_handler(event: dict) -> dict:
    """Translate domain events into durable work. Unknown events are retained as
    processed facts; they may still feed analytics and future subscriptions."""
    event_type = event.get("event_type")
    payload = event.get("payload") or {}
    user_id = payload.get("user_id")

    if event_type == "initiative.approved":
        if not user_id or not payload.get("legacy_action_id"):
            raise NonRetryableWorkflowError("initiative.approved is missing identity or action")
        workflow = await store.enqueue_workflow(
            user_id,
            "initiative.execute",
            {"user_id": user_id, "legacy_action_id": payload["legacy_action_id"]},
            idempotency_key=f"initiative-execute:{payload['legacy_action_id']}:v1",
            initiative_id=payload.get("initiative_id"),
            priority=10,
            max_attempts=3,
            steps=INITIATIVE_EXECUTION_STEPS,
        )
        return {"workflow_id": workflow["id"]}

    if event_type in ("operator.requested", "goal.off_track"):
        if not user_id:
            raise NonRetryableWorkflowError(f"{event_type} is missing user_id")
        run_id = payload.get("operator_run_id") or await create_operator_run_row(user_id)
        if not run_id:
            raise RetryableWorkflowError("Could not create Operator run record")
        workflow = await store.enqueue_workflow(
            user_id,
            "operator.run",
            {"user_id": user_id, "operator_run_id": run_id, "notify": bool(payload.get("notify"))},
            idempotency_key=payload.get("workflow_key") or f"operator-run:{run_id}",
            goal_id=payload.get("goal_id"),
            priority=20 if event_type == "goal.off_track" else 30,
            steps=OPERATOR_WORKFLOW_STEPS,
        )
        return {"workflow_id": workflow["id"], "operator_run_id": run_id}

    return {"ignored": True, "event_type": event_type}
