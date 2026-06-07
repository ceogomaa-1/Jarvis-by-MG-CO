import pytest
import sys
import types

from backend.lib.business.connectors.metricool_conn import MetricoolConnector
from backend.lib.business.tool_builder import build_tools_for_user

if "supabase" not in sys.modules or not hasattr(sys.modules.get("supabase"), "create_client"):
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.create_client = lambda *args, **kwargs: None
    sys.modules["supabase"] = supabase_stub

from backend.routes.business.chat import WRITE_ACTIONS, _describe_action


def test_metricool_manifest_contains_required_fields():
    manifest = MetricoolConnector.manifest()

    assert manifest["type"] == "metricool"
    fields = {field["name"]: field for field in manifest["fields"]}
    assert fields["access_token"]["secret"] is True
    assert fields["user_id"]["required"] is True
    assert fields["default_blog_id"]["required"] is False


@pytest.mark.asyncio
async def test_metricool_tools_only_show_when_connected(monkeypatch):
    async def no_connections(user_id):
        return []

    monkeypatch.setattr("backend.lib.business.tool_builder.list_user_connections", no_connections)
    assert not any(t["name"].startswith("metricool__") for t in await build_tools_for_user("user_1"))

    async def metricool_connected(user_id):
        return [{"connector_type": "metricool", "status": "active"}]

    monkeypatch.setattr("backend.lib.business.tool_builder.list_user_connections", metricool_connected)
    names = {t["name"] for t in await build_tools_for_user("user_1")}

    assert "metricool__list_brands" in names
    assert "metricool__get_metrics" in names
    assert "metricool__schedule_post" in names
    assert "metricool__update_scheduled_post" in names


def test_metricool_write_actions_are_confirmed():
    assert "metricool__schedule_post" in WRITE_ACTIONS
    assert "metricool__update_scheduled_post" in WRITE_ACTIONS

    description = _describe_action(
        "metricool__schedule_post",
        {
            "text": "Open house this Sunday.",
            "networks": ["instagram", "facebook"],
            "publish_at": "2026-06-08T09:00:00",
        },
    )

    assert "Schedule Metricool post" in description
    assert "instagram" in description
    assert "2026-06-08T09:00:00" in description


@pytest.mark.asyncio
async def test_metricool_schedule_post_validates_x_length():
    connector = MetricoolConnector({"access_token": "token", "user_id": "123", "default_blog_id": "456"})

    result = await connector.schedule_post(
        text="x" * 281,
        networks=["twitter"],
        publish_at="2026-06-08T09:00:00",
    )

    assert result.ok is False
    assert "280-character" in result.error
