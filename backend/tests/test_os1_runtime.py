"""Batch 77 durable runtime tests (no network)."""
import asyncio

import pytest

from backend.lib.business.runtime import handlers, worker


def test_unknown_workflow_kind_is_never_retried():
    with pytest.raises(handlers.NonRetryableWorkflowError):
        asyncio.run(handlers.run_workflow_handler({"kind": "unknown", "input": {}}))


def test_operator_workflow_requires_durable_run_identity():
    with pytest.raises(handlers.NonRetryableWorkflowError):
        asyncio.run(handlers.run_workflow_handler({"kind": "operator.run", "input": {"user_id": "user_x"}}))


def test_approved_event_collapses_to_idempotent_execution_workflow(monkeypatch):
    captured = {}

    async def fake_enqueue(user_id, kind, input_data, **kwargs):
        captured.update({"user_id": user_id, "kind": kind, "input": input_data, **kwargs})
        return {"id": "workflow-1"}

    monkeypatch.setattr(handlers.store, "enqueue_workflow", fake_enqueue)
    result = asyncio.run(handlers.run_event_handler({
        "event_type": "initiative.approved",
        "payload": {"user_id": "user_abc", "legacy_action_id": "action-123"},
    }))
    assert result["workflow_id"] == "workflow-1"
    assert captured["kind"] == "initiative.execute"
    assert captured["idempotency_key"] == "initiative-execute:action-123:v1"
    assert captured["priority"] == 10


def test_claimed_workflow_completes_and_cancels_heartbeat(monkeypatch):
    calls = []

    async def fake_append(*args, **kwargs):
        calls.append("started")

    async def fake_handler(workflow):
        return {"status": "complete"}

    async def fake_complete(workflow, output):
        calls.append(("complete", output))
        return True

    async def fake_extend(*args, **kwargs):
        return True

    monkeypatch.setattr(worker.store, "append_workflow_event", fake_append)
    monkeypatch.setattr(worker, "run_workflow_handler", fake_handler)
    monkeypatch.setattr(worker.store, "complete_workflow", fake_complete)
    monkeypatch.setattr(worker.store, "extend_workflow_lease", fake_extend)

    result = asyncio.run(worker._execute_claimed_workflow({
        "id": "wf-1", "kind": "operator.run", "lease_owner": worker.WORKER_NAME,
        "attempts": 1, "max_attempts": 5,
    }))
    assert result["status"] == "succeeded"
    assert ("complete", {"status": "complete"}) in calls


def test_nonretryable_failure_goes_directly_to_dead_letter(monkeypatch):
    async def fake_append(*args, **kwargs):
        return None

    async def fake_handler(workflow):
        raise handlers.NonRetryableWorkflowError("bad contract")

    async def fake_fail(workflow, error, retryable=True):
        assert retryable is False
        return {"ok": True, "retrying": False, "status": "dead_letter"}

    monkeypatch.setattr(worker.store, "append_workflow_event", fake_append)
    monkeypatch.setattr(worker, "run_workflow_handler", fake_handler)
    monkeypatch.setattr(worker.store, "fail_workflow", fake_fail)

    result = asyncio.run(worker._execute_claimed_workflow({
        "id": "wf-2", "lease_owner": worker.WORKER_NAME, "attempts": 1, "max_attempts": 5,
    }))
    assert result["status"] == "dead_letter"
    assert result["retrying"] is False
