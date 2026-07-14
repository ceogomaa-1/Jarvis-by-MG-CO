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

    async def fake_authorize(*args, **kwargs):
        return {"allowed": True, "reason": "test"}

    monkeypatch.setattr(worker.store, "append_workflow_event", fake_append)
    monkeypatch.setattr(worker, "run_workflow_handler", fake_handler)
    monkeypatch.setattr(worker.store, "complete_workflow", fake_complete)
    monkeypatch.setattr(worker.store, "extend_workflow_lease", fake_extend)
    monkeypatch.setattr(worker, "authorize_workflow", fake_authorize)

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

    async def fake_authorize(*args, **kwargs):
        return {"allowed": True, "reason": "test"}

    monkeypatch.setattr(worker.store, "append_workflow_event", fake_append)
    monkeypatch.setattr(worker, "run_workflow_handler", fake_handler)
    monkeypatch.setattr(worker.store, "fail_workflow", fake_fail)
    monkeypatch.setattr(worker, "authorize_workflow", fake_authorize)

    result = asyncio.run(worker._execute_claimed_workflow({
        "id": "wf-2", "lease_owner": worker.WORKER_NAME, "attempts": 1, "max_attempts": 5,
    }))
    assert result["status"] == "dead_letter"
    assert result["retrying"] is False


def test_governor_denial_cancels_without_running_handler(monkeypatch):
    calls = []

    async def fake_append(*args, **kwargs):
        return None

    async def fake_authorize(*args, **kwargs):
        return {"allowed": False, "reason": "monthly_capacity_exhausted"}

    async def fake_deny(workflow, decision):
        calls.append((workflow["id"], decision["reason"]))
        return True

    async def must_not_run(workflow):
        raise AssertionError("denied workflow executed")

    async def fake_mark(*args, **kwargs):
        return None

    monkeypatch.setattr(worker.store, "append_workflow_event", fake_append)
    monkeypatch.setattr(worker, "authorize_workflow", fake_authorize)
    monkeypatch.setattr(worker.store, "deny_workflow", fake_deny)
    monkeypatch.setattr(worker, "run_workflow_handler", must_not_run)
    monkeypatch.setattr(worker, "mark_operator_run_skipped", fake_mark)

    result = asyncio.run(worker._execute_claimed_workflow({
        "id": "wf-denied",
        "kind": "operator.run",
        "input": {"operator_run_id": "run-1"},
        "lease_owner": worker.WORKER_NAME,
    }))
    assert result["status"] == "cancelled"
    assert calls == [("wf-denied", "monthly_capacity_exhausted")]
