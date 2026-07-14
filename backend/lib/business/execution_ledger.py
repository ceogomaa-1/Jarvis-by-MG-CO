"""Durable idempotency guard around real tool calls."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 12.0


class ExecutionLedgerUnavailable(RuntimeError):
    pass


def _redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(
                marker in str(key).lower()
                for marker in ("password", "token", "secret", "api_key", "authorization")
            ) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def classify_tool_effect(tool_name: str) -> str:
    name = (tool_name or "").lower()
    financial = ("stripe__" in name and any(token in name for token in ("create", "refund", "charge", "price")))
    if financial:
        return "financial"
    action = name.split("__")[-1]
    read_prefixes = (
        "get", "list", "search", "find", "fetch", "read", "check", "lookup",
        "preview", "inspect", "retrieve", "query", "browse",
    )
    if action.startswith(read_prefixes):
        return "read"
    external_markers = (
        "send", "email", "post", "publish", "schedule", "deploy", "push", "sms",
        "call", "invite", "create_event", "update_event", "delete_event",
    )
    if any(marker in action for marker in external_markers):
        return "external_write"
    internal_markers = ("create", "update", "delete", "add", "remove", "upsert", "move", "set")
    if action.startswith(internal_markers):
        return "internal_write"
    return "unknown"


def stable_tool_call_key(round_index: int, call_index: int, tool_name: str, tool_input: dict) -> tuple[str, str]:
    canonical = json.dumps(tool_input or {}, sort_keys=True, separators=(",", ":"), default=str)
    input_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    key = f"r{round_index}:c{call_index}:{tool_name}:{input_hash[:16]}"
    return key, input_hash


async def prepare_tool_execution(
    *,
    business_id: str,
    workflow_id: str,
    legacy_action_id: str,
    round_index: int,
    call_index: int,
    tool_name: str,
    tool_input: dict,
) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ExecutionLedgerUnavailable("Supabase is not configured")
    call_key, input_hash = stable_tool_call_key(round_index, call_index, tool_name, tool_input)
    row = {
        "business_id": business_id,
        "workflow_id": workflow_id,
        "legacy_action_id": legacy_action_id,
        "tool_call_key": call_key,
        "tool_name": tool_name,
        "input_hash": input_hash,
        "input_snapshot": _redact(tool_input or {}),
        "effect_class": classify_tool_effect(tool_name),
        "status": "prepared",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_tool_executions?on_conflict=workflow_id,tool_call_key",
            headers=_headers("resolution=ignore-duplicates,return=representation"),
            json=row,
            timeout=TIMEOUT,
        )
        if response.status_code not in (200, 201):
            raise ExecutionLedgerUnavailable(f"Tool ledger unavailable: {response.text[:160]}")
        if response.json():
            record = response.json()[0]
            claimed = await client.patch(
                f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
                headers=_headers("return=representation"),
                params={"id": f"eq.{record['id']}", "status": "eq.prepared"},
                json={
                    "status": "running",
                    "attempts": 1,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=TIMEOUT,
            )
            if claimed.status_code == 200 and claimed.json():
                return {"mode": "execute", "record": claimed.json()[0]}
        existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
            headers=_headers(),
            params={
                "select": "*",
                "workflow_id": f"eq.{workflow_id}",
                "tool_call_key": f"eq.{call_key}",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )
        if existing.status_code != 200 or not existing.json():
            raise ExecutionLedgerUnavailable("Tool ledger returned no durable record")
        record = existing.json()[0]
        if record.get("status") == "succeeded":
            return {"mode": "replay", "record": record, "result_text": record.get("result_text") or "{}"}
        retryable_state = record.get("status") == "prepared" or (
            record.get("effect_class") == "read" and record.get("status") in {"running", "failed"}
        )
        if retryable_state:
            claimed = await client.patch(
                f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
                headers=_headers("return=representation"),
                params={"id": f"eq.{record['id']}", "status": f"eq.{record['status']}"},
                json={
                    "status": "running",
                    "attempts": int(record.get("attempts") or 0) + 1,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": None,
                    "error": None,
                },
                timeout=TIMEOUT,
            )
            if claimed.status_code == 200 and claimed.json():
                return {"mode": "execute", "record": claimed.json()[0]}

        # A prior write may have reached the external system even if its response
        # never reached Rue. Mark it ambiguous and require human review.
        ambiguous = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
            headers=_headers("return=representation"),
            params={"id": f"eq.{record['id']}", "status": "in.(prepared,running,failed)"},
            json={
                "status": "ambiguous",
                "error": "Prior side effect has no durable success receipt; automatic replay blocked.",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=TIMEOUT,
        )
        if ambiguous.status_code == 200 and not ambiguous.json():
            raced = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
                headers=_headers(),
                params={"select": "*", "id": f"eq.{record['id']}", "limit": "1"},
                timeout=TIMEOUT,
            )
            if raced.status_code == 200 and raced.json() and raced.json()[0].get("status") == "succeeded":
                completed = raced.json()[0]
                return {"mode": "replay", "record": completed, "result_text": completed.get("result_text") or "{}"}
    return {"mode": "ambiguous", "record": record}


async def finish_tool_execution(record_id: str, result_text: str, *, ok: bool, error: str | None = None) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_tool_executions",
            headers=_headers("return=representation"),
            params={"id": f"eq.{record_id}", "status": "eq.running"},
            json={
                "status": "succeeded" if ok else "failed",
                "result_text": str(result_text)[:20000],
                "error": str(error)[:2000] if error else None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=TIMEOUT,
        )
    if response.status_code != 200 or not response.json():
        raise ExecutionLedgerUnavailable("Could not finalize tool execution receipt")
