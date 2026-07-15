"""Regression coverage for Personal Rue's empty-response recovery."""
from types import SimpleNamespace

import pytest

from backend import llm


def _text_result(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=None,
    )


def _tool_result(index: int):
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                id=f"tool-{index}",
                name="test_tool",
                input={"index": index},
            )
        ],
        stop_reason="tool_use",
        usage=None,
    )


def _patch_personal_runtime(monkeypatch, results):
    calls = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return results.pop(0)

    async def fake_moment(_user_id):
        return ""

    async def fake_tool(**_kwargs):
        return "tool evidence"

    monkeypatch.setattr(llm._client.messages, "create", fake_create)
    monkeypatch.setattr(llm, "get_current_moment_block", fake_moment)

    from backend import agent
    from backend.tools import registry

    tool_schema = {
        "name": "test_tool",
        "description": "test",
        "input_schema": {"type": "object", "properties": {}},
    }
    monkeypatch.setattr(agent, "ANTHROPIC_TOOLS", [])
    monkeypatch.setattr(
        registry,
        "TOOL_REGISTRY",
        {"test_tool": {"execute": fake_tool, "schema": tool_schema}},
    )
    monkeypatch.setattr(registry, "get_tools_for_claude", lambda: [tool_schema])
    return calls


@pytest.mark.asyncio
async def test_tool_round_cap_forces_tool_free_final_answer(monkeypatch):
    # Initial call + three executed tool rounds all request another tool. The
    # fifth response is the forced tool-free final answer.
    results = [_tool_result(i) for i in range(4)]
    results.append(_text_result("I hear you. Let's work through this together."))
    calls = _patch_personal_runtime(monkeypatch, results)

    answer = await llm.jarvis_think(
        user_message="I feel overwhelmed",
        conversation_history=[],
        available_tools=[{"name": "enabled"}],
        user_id="user_test",
    )

    assert answer == "I hear you. Let's work through this together."
    assert len(calls) == 5
    assert "tools" in calls[0]
    assert "tools" in calls[-2]
    assert "tools" not in calls[-1]
    assert "No more tools are available" in calls[-1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_empty_success_envelope_gets_one_recovery_completion(monkeypatch):
    results = [_text_result(""), _text_result("I'm right here with you.")]
    calls = _patch_personal_runtime(monkeypatch, results)

    answer = await llm.jarvis_think(
        user_message="Can we talk?",
        conversation_history=[],
        available_tools=None,
        user_id="user_test",
    )

    assert answer == "I'm right here with you."
    assert len(calls) == 2
    assert "tools" not in calls[-1]


@pytest.mark.asyncio
async def test_normal_text_response_is_unchanged(monkeypatch):
    results = [_text_result("Normal answer")]
    calls = _patch_personal_runtime(monkeypatch, results)

    answer = await llm.jarvis_think(
        user_message="short prompt",
        conversation_history=[],
        available_tools=None,
        user_id="user_test",
    )

    assert answer == "Normal answer"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 4096


def test_extract_text_joins_multiple_text_blocks():
    content = [
        SimpleNamespace(type="text", text="First "),
        SimpleNamespace(type="thinking", thinking="hidden"),
        SimpleNamespace(type="text", text="second"),
    ]
    assert llm._extract_text(content) == "First second"


@pytest.mark.asyncio
async def test_structured_extraction_keeps_sonnet_but_skips_companion_stack(monkeypatch):
    calls = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return _text_result('{"identity": {"name": "Mo"}}')

    monkeypatch.setattr(llm._client.messages, "create", fake_create)
    answer = await llm.extract_structured_json(
        prompt="Extract the name from: my name is Mo",
        system="Return JSON only",
        where="test_extraction",
    )

    assert answer == '{"identity": {"name": "Mo"}}'
    assert len(calls) == 1
    assert calls[0]["model"] == llm.SONNET
    assert calls[0]["system"] == "Return JSON only"
    assert "tools" not in calls[0]
    if llm.SONNET.startswith("claude-sonnet-5"):
        assert calls[0]["thinking"] == {"type": "disabled"}
