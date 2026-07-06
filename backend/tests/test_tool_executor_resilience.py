"""Regression: a transient connector-credential fetch failure must NOT take down
the chat turn. It should come back as a normal error result the model can narrate.
Guards the bug where get_connector_for_user raised uncaught → 'Something went wrong'."""
import asyncio
import json

from backend.lib.business import tool_executor


def test_connector_fetch_exception_becomes_error_result(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("creds fetch blew up")

    monkeypatch.setattr(tool_executor, "get_connector_for_user", boom)

    out = asyncio.run(
        tool_executor.execute_tool(
            "supabase_project__run_sql",
            {"project_id": "p", "sql": "select 1"},
            "user_x",
        )
    )
    data = json.loads(out)
    assert "error" in data
    assert "supabase_project" in data["error"]  # names the connector, no crash


def test_unconnected_connector_returns_error_not_raise(monkeypatch):
    async def none_connector(*args, **kwargs):
        return None

    monkeypatch.setattr(tool_executor, "get_connector_for_user", none_connector)

    out = asyncio.run(
        tool_executor.execute_tool("notion__search", {"query": "x"}, "user_x")
    )
    data = json.loads(out)
    assert "error" in data
    assert "Not connected" in data["error"]
