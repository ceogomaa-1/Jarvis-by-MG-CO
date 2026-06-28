import pytest

from backend.lib.business.memory import should_extract_memories
from backend.lib.business.model_router import HAIKU, OPUS, SONNET, select_model
from backend.lib.business.prompt_budget import cap_tool_result, clip_text, trim_history


def test_trim_history_keeps_newest_messages_inside_total_budget():
    history = [
        {"role": "user", "content": "old-" + "a" * 100},
        {"role": "assistant", "content": "middle-" + "b" * 100},
        {"role": "user", "content": "new-" + "c" * 100},
    ]
    result = trim_history(history, char_cap=150, max_messages=10)
    assert result[-1]["content"].startswith("new-")
    assert sum(len(message["content"]) for message in result) <= 150
    assert all(message["role"] in ("user", "assistant") for message in result)


def test_clip_text_and_tool_results_have_hard_caps():
    text = "A" * 20_000 + "THE-END"
    assert len(clip_text(text, 1_000)) <= 1_000
    assert clip_text(text, 1_000).endswith("THE-END")
    assert len(cap_tool_result("x" * 100_000)) <= 24_000


def test_model_router_uses_cheap_tier_for_small_asks_but_not_complex_or_files():
    assert select_model("What time is it?") == HAIKU
    assert select_model("Can you check my calendar?") == HAIKU
    assert select_model("Create a comprehensive five-year growth strategy") == OPUS
    assert select_model("Analyze this", has_attachments=True) == SONNET


def test_memory_extraction_only_runs_for_durable_user_context():
    assert should_extract_memories("Thanks!") is False
    assert should_extract_memories("Can you check tomorrow's weather?") is False
    assert should_extract_memories("My business is a dental clinic in Oshawa") is True


@pytest.mark.asyncio
async def test_cost_control_probe_reports_active_revision():
    from backend.routes.business.chat import get_cost_controls

    result = await get_cost_controls()
    assert result["revision"] == "prompt-cache-v2"
    assert result["website_workflow_revision"] == "surgical-edit-v1"
    assert result["automatic_conversation_caching"] is True
    assert result["history_char_cap"] > 0
