import pytest
import sys
import types

from backend.lib.business.connectors.buffer_conn import BufferConnector
from backend.lib.business.tool_builder import build_tools_for_user

supabase_stub = types.ModuleType("supabase")
supabase_stub.create_client = lambda *args, **kwargs: None
sys.modules.setdefault("supabase", supabase_stub)

from backend.routes.business.chat import WRITE_ACTIONS, _describe_action


def test_buffer_manifest_contains_required_fields():
    manifest = BufferConnector.manifest()

    assert manifest["type"] == "buffer"
    assert manifest["display_name"] == "Buffer"
    fields = {field["name"]: field for field in manifest["fields"]}
    assert fields["api_key"]["secret"] is True
    assert fields["api_key"]["required"] is True
    assert fields["organization_id"]["required"] is False


@pytest.mark.asyncio
async def test_buffer_tools_only_show_when_connected(monkeypatch):
    async def no_connections(user_id):
        return []

    monkeypatch.setattr("backend.lib.business.tool_builder.list_user_connections", no_connections)
    assert not any(t["name"].startswith("buffer__") for t in await build_tools_for_user("user_1"))

    async def buffer_connected(user_id):
        return [{"connector_type": "buffer", "status": "active"}]

    monkeypatch.setattr("backend.lib.business.tool_builder.list_user_connections", buffer_connected)
    names = {tool["name"] for tool in await build_tools_for_user("user_1")}

    assert "buffer__list_organizations" in names
    assert "buffer__list_channels" in names
    assert "buffer__get_scheduled_posts" in names
    assert "buffer__schedule_post" in names
    assert "buffer__add_to_queue" in names
    assert not any(name.startswith("metricool__") for name in names)


def test_buffer_write_actions_are_confirmed():
    assert "buffer__create_post" in WRITE_ACTIONS
    assert "buffer__schedule_post" in WRITE_ACTIONS
    assert "buffer__add_to_queue" in WRITE_ACTIONS
    assert "metricool__schedule_post" not in WRITE_ACTIONS

    description = _describe_action(
        "buffer__schedule_post",
        {
            "text": "Open house this weekend.",
            "channel_ids": ["ch_instagram", "ch_linkedin"],
            "publish_at": "2026-06-08T14:00:00Z",
        },
    )

    assert "Schedule Buffer post" in description
    assert "ch_instagram" in description
    assert "2026-06-08T14:00:00Z" in description


@pytest.mark.asyncio
async def test_buffer_schedule_post_validates_channel_ids():
    connector = BufferConnector({"api_key": "token", "organization_id": "org_1"})

    result = await connector.schedule_post(
        text="Post with nowhere to go",
        channel_ids=[],
        publish_at="2026-06-08T14:00:00Z",
    )

    assert result.ok is False
    assert "channel_id" in result.error


@pytest.mark.asyncio
async def test_buffer_schedule_post_validates_x_length():
    connector = BufferConnector({"api_key": "token", "organization_id": "org_1"})

    result = await connector.schedule_post(
        text="x" * 281,
        channel_ids=["ch_x"],
        publish_at="2026-06-08T14:00:00Z",
        networks=["x"],
    )

    assert result.ok is False
    assert "280" in result.error
