"""
Regression tests for backend/memory.py — Phase 2 (JARVIS-BRAIN-MAP.md
section B5): get_relevant_memories() must distinguish "no relevant memories
found" ("") from "the Mem0 lookup itself failed" (MEMORY_LOOKUP_FAILED_NOTE),
so the system prompt doesn't imply Jarvis has zero memories of the user when
the lookup was actually rate-limited or errored.
"""
import pytest

from backend import memory
from backend.memory import MEMORY_LOOKUP_FAILED_NOTE, get_relevant_memories


@pytest.mark.asyncio
async def test_no_results_returns_empty_string(monkeypatch):
    monkeypatch.setattr(memory._client, "search", lambda *a, **k: {"results": []})
    result = await get_relevant_memories("user-1", "what's my dream job")
    assert result == ""


@pytest.mark.asyncio
async def test_results_are_formatted_as_bullet_list(monkeypatch):
    monkeypatch.setattr(
        memory._client,
        "search",
        lambda *a, **k: {"results": [{"memory": "Dream job: lead a music label"}, {"memory": "Loves chess"}]},
    )
    result = await get_relevant_memories("user-1", "what's my dream job")
    assert result == "- Dream job: lead a music label\n- Loves chess"


@pytest.mark.asyncio
async def test_search_exception_returns_lookup_failed_note(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("mem0 down")

    monkeypatch.setattr(memory._client, "search", _boom)
    result = await get_relevant_memories("user-1", "what's my dream job")
    assert result == MEMORY_LOOKUP_FAILED_NOTE
    assert result != ""
