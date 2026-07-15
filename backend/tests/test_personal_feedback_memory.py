"""Rue feedback memory must not launch an LLM classifier on ordinary chat."""
from types import SimpleNamespace

import pytest

from backend import memory


@pytest.mark.asyncio
async def test_emotional_help_request_is_not_misclassified_as_rue_feedback(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, "_client", SimpleNamespace(add=lambda *a, **k: calls.append((a, k))))

    await memory.extract_and_save_feedback_memory(
        "user-1",
        "I feel overwhelmed and depressed. Rue, I need help finding what is stopping me.",
        "I'm here with you.",
        feedback_was_requested=False,
    )

    assert calls == []


@pytest.mark.asyncio
async def test_explicit_rue_feedback_is_saved_verbatim_without_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, "_client", SimpleNamespace(add=lambda *a, **k: calls.append((a, k))))

    await memory.extract_and_save_feedback_memory(
        "user-1",
        "Rue, you're too formal. I wish you were more casual.",
        "That's fair.",
        feedback_was_requested=False,
    )

    assert len(calls) == 1
    saved_messages = calls[0][0][0]
    assert saved_messages[0]["content"].startswith("jarvis_feedback: Rue, you're too formal")
