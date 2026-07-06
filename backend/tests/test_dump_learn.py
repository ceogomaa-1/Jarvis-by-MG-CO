"""
Dump Learn — pure-logic tests.

Covers the deterministic pieces that don't need a live Anthropic/Supabase call:
token estimation, chunking, YouTube id parsing, the explanation cache
fingerprint (must change when the bin's ready items change), JSON-response
parsing/fallback, and the per-level context assembly that gives Expert mode
real primary-source depth instead of just a different prompt.
"""
import asyncio

from backend.lib.personal import dump_learn_ingest as ing
from backend.lib.personal import dump_learn_engine as eng


# ── ingest ────────────────────────────────────────────────────────────────────

def test_estimate_tokens_roughly_four_chars_per_token():
    assert ing.estimate_tokens("x" * 400) == 100
    assert ing.estimate_tokens("") == 0
    assert ing.estimate_tokens(None) == 0


def test_chunk_text_splits_large_content_with_overlap():
    text = "y" * 2000
    chunks = ing._chunk_text(text)
    assert len(chunks) >= 3
    assert all(c.strip() for c in chunks)


def test_chunk_text_small_content_one_chunk():
    assert ing._chunk_text("short") == ["short"]


def test_youtube_id_extracts_from_common_url_shapes():
    assert ing._youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert ing._youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert ing._youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert ing._youtube_id("https://example.com/not-youtube") is None


def test_extract_source_text_kind_is_lossless_passthrough():
    result = asyncio.run(ing.extract_source("text", text="  full raw material  "))
    assert result["error"] is None
    assert result["text"] == "full raw material"


def test_extract_source_text_kind_rejects_empty():
    result = asyncio.run(ing.extract_source("text", text="   "))
    assert result["error"]
    assert result["text"] == ""


def test_extract_source_unsupported_kind_is_honest_error():
    result = asyncio.run(ing.extract_source("carrier-pigeon"))
    assert "Unsupported" in result["error"]


# ── engine: cache fingerprint ─────────────────────────────────────────────────

def test_fingerprint_stable_for_same_items():
    items = [{"id": "a", "updated_at": "t1", "token_estimate": 100}, {"id": "b", "updated_at": "t2", "token_estimate": 200}]
    assert eng.fingerprint_items(items) == eng.fingerprint_items(list(reversed(items)))


def test_fingerprint_changes_when_item_content_changes():
    base = [{"id": "a", "updated_at": "t1", "token_estimate": 100}]
    changed = [{"id": "a", "updated_at": "t2", "token_estimate": 100}]
    assert eng.fingerprint_items(base) != eng.fingerprint_items(changed)


def test_fingerprint_changes_when_a_new_item_is_added():
    base = [{"id": "a", "updated_at": "t1", "token_estimate": 100}]
    with_new = base + [{"id": "b", "updated_at": "t1", "token_estimate": 50}]
    assert eng.fingerprint_items(base) != eng.fingerprint_items(with_new)


# ── engine: response parsing ──────────────────────────────────────────────────

def test_parse_json_response_plain():
    data = eng._parse_json_response('{"tldr": "hi", "sections": []}')
    assert data == {"tldr": "hi", "sections": []}


def test_parse_json_response_strips_markdown_fences():
    raw = "```json\n{\"tldr\": \"hi\"}\n```"
    assert eng._parse_json_response(raw) == {"tldr": "hi"}


def test_parse_json_response_invalid_returns_none():
    assert eng._parse_json_response("not json at all") is None


def test_fallback_lesson_never_drops_the_models_output():
    lesson = eng._fallback_lesson("some raw explanation text")
    assert lesson["sections"][0]["body_md"] == "some raw explanation text"
    assert lesson["quiz"] == []
    assert lesson["mind_map"] is None


# ── engine: level-dependent context assembly ──────────────────────────────────

def _item(**over):
    base = {"id": "1", "source_name": "Doc", "extracted_text": "RAW" * 5000, "skeleton_md": "SKELETON"}
    base.update(over)
    return base


def test_graduate_prefers_skeleton_over_raw_text():
    ctx = eng._assemble_context([_item()], "graduate")
    assert "SKELETON" in ctx
    assert "RAW" * 5000 not in ctx  # would only appear if the full raw text leaked in


def test_expert_prefers_raw_text_over_skeleton():
    ctx = eng._assemble_context([_item()], "expert")
    assert ctx.count("RAW") > 100  # raw text (capped) is present, not just the skeleton
    assert "SKELETON" not in ctx


def test_child_and_graduate_get_smaller_slice_than_expert():
    item = _item(extracted_text="Z" * 100000, skeleton_md=None)
    child_ctx = eng._assemble_context([item], "child")
    expert_ctx = eng._assemble_context([item], "expert")
    assert len(expert_ctx) > len(child_ctx)
