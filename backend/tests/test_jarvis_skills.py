"""
Rue Skills Phase 1 — lossless ingest guarantees.

The whole point of this system is that user input is NEVER silently dropped and the
LLM only adds metadata (it can't gate saving). These tests pin the pure logic that
guarantees that, and prove the original-sin "nothing useful found" skip is gone.
"""
import asyncio
import inspect

from backend.lib.business import jarvis_skills as js


def test_fallback_name_prefers_filename():
    assert js._fallback_name("whatever", "mgco-knowledge.md") == "mgco-knowledge"


def test_fallback_name_uses_first_line_when_no_filename():
    assert js._fallback_name("# Company Playbook\n\nbody...", None) == "Company Playbook"


def test_fallback_name_never_empty():
    assert js._fallback_name("", None) == "Untitled skill"


def test_fallback_metadata_defaults_to_knowledge():
    meta = js._fallback_metadata("some strategic narrative", "doc.md")
    assert meta["skill_type"] == "knowledge"
    assert meta["name"] == "doc"
    assert meta["operating_instructions"] is None


def test_chunk_text_splits_large_content_with_overlap():
    text = "x" * 2000
    chunks = js._chunk_text(text)
    assert len(chunks) >= 3                       # 2000 / 800 with overlap
    assert all(c.strip() for c in chunks)         # no empty chunks
    # Reassembled length covers the whole document (nothing dropped).
    assert sum(len(c) for c in chunks) >= len(text)


def test_chunk_text_small_content_one_chunk():
    assert js._chunk_text("short note") == ["short note"]


def test_what_changes_wording_differs_by_type():
    assert "operating rules" in js._what_changes("behavior", "Greeting Rules")
    assert "recall and cite" in js._what_changes("knowledge", "Pricing Sheet")


def test_metadata_falls_back_without_api_key(monkeypatch):
    # No API key -> safe fallback, never a network call, never a block.
    monkeypatch.setattr(js, "ANTHROPIC_API_KEY", "")
    meta = asyncio.run(js.generate_skill_metadata("a strategic narrative doc", "mgco-knowledge.md"))
    assert meta["skill_type"] == "knowledge"
    assert meta["name"] == "mgco-knowledge"


def test_empty_content_is_honest_error_not_silent_skip():
    res = asyncio.run(js.create_skill("user_test", "   "))
    assert res["status"] == "error"
    # Honest message about unreadable/empty content — NOT a content-judgment skip.
    assert "readable" in res["error"].lower()
    assert "nothing useful" not in res["error"].lower()


def test_create_skill_passes_full_content_verbatim(monkeypatch):
    # Capture what would be written to the DB and assert the FULL content is stored
    # verbatim (not truncated, not fact-extracted away).
    monkeypatch.setattr(js, "ANTHROPIC_API_KEY", "")            # force metadata fallback
    monkeypatch.setattr(js, "SUPABASE_URL", "https://x.test")
    monkeypatch.setattr(js, "SUPABASE_KEY", "service-key")

    captured = {}

    class _Resp:
        status_code = 201
        def json(self):
            return [{"id": "skill-123"}]

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None, timeout=None):
            captured["row"] = json
            return _Resp()

    monkeypatch.setattr(js.httpx, "AsyncClient", lambda *a, **k: _Client())
    # No embedding backend in this test -> chunk step is a no-op.
    monkeypatch.setattr(js, "_embed_skill_chunks", _async_zero)

    big = "STRATEGY DOC\n" + ("line of narrative content\n" * 2000)  # > 12K chars
    res = asyncio.run(js.create_skill("user_test", big, source_filename="mgco-knowledge.md"))

    assert res["status"] == "learned"
    assert captured["row"]["full_content"] == big       # verbatim, not truncated at 12K
    assert len(captured["row"]["full_content"]) > 12000


async def _async_zero(*a, **k):
    return 0


def test_behavior_block_lists_operating_instructions():
    block = js._behavior_block_from([
        {"name": "Greeting Rules", "operating_instructions": "Greet in one short line; end with a next-step question."},
        {"name": "No-instr skill", "operating_instructions": ""},  # skipped
    ])
    assert "Greeting Rules" in block
    assert "next-step question" in block
    assert "No-instr skill" not in block


def test_behavior_block_empty_when_none():
    assert js._behavior_block_from([]) == ""


def test_knowledge_block_filters_disabled_and_low_similarity():
    name_by_id = {"s1": "Pricing Sheet"}  # only s1 is enabled-knowledge
    chunks = [
        {"skill_id": "s1", "content": "Premium plan is $499/mo.", "similarity": 0.81},
        {"skill_id": "s1", "content": "irrelevant", "similarity": 0.10},   # below threshold
        {"skill_id": "s2", "content": "from a disabled skill", "similarity": 0.92},  # not enabled
    ]
    block = js._knowledge_block_from(chunks, name_by_id)
    assert "Pricing Sheet" in block          # cited by skill name
    assert "$499/mo" in block
    assert "irrelevant" not in block         # similarity filtered
    assert "disabled skill" not in block     # enabled-filtered


def test_knowledge_block_empty_when_nothing_relevant():
    assert js._knowledge_block_from([], {"s1": "X"}) == ""


def test_empty_ingest_text_is_honest_error_not_skip():
    # Behavioral guarantee: empty pasted text -> honest 'error', never a silent
    # 'skipped'/'nothing useful' content judgment.
    import backend.lib.business.knowledge_base as kb
    res = asyncio.run(kb.ingest_text("user_test", "   "))
    assert res["status"] == "error"
    assert res["status"] != "skipped"
    assert "nothing useful" not in (res.get("error") or "").lower()
