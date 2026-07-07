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


# ── _extract_text: never assume content[0] is a text block ───────────────────
# (this was the actual bug behind the empty "Explanation" card: content[0][0]
# was blindly indexed instead of filtering for type == "text")

def test_extract_text_ingest_joins_only_text_blocks():
    data = {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "hello"}]}
    assert ing._extract_text(data) == "hello"


def test_extract_text_ingest_handles_empty_content_list():
    assert ing._extract_text({"content": []}) == ""


def test_extract_text_ingest_handles_missing_content_key():
    assert ing._extract_text({}) == ""


def test_extract_text_engine_joins_only_text_blocks():
    data = {"content": [{"type": "redacted_thinking"}, {"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    assert eng._extract_text(data) == "ab"


def test_extract_text_engine_handles_empty_content_list():
    assert eng._extract_text({"content": []}) == ""


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


# ── engine: explain_bin never leaks raw JSON to the user ──────────────────────
# Regression coverage for the real production bug: a truncated/invalid model
# response used to get wrapped verbatim into the lesson body via a "never drop
# the model's output" fallback — which meant the user saw literal `{"tldr": ...`
# JSON syntax in the UI. explain_bin now retries once on a parse failure, and
# if it still can't get valid JSON, returns an honest error — never raw text.

class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body

    @property
    def text(self):
        return str(self._body)


def _usage_body(text):
    return {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 5}}


def _fake_client(post_fn):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None, timeout=None):
            return _FakeResp(200, [])  # cache miss

        async def post(self, url, headers=None, json=None, timeout=None):
            if "anthropic.com" in url:
                return post_fn()
            return _FakeResp(204, {})  # cache write

    return lambda *a, **k: _Client()


def _ready_item():
    return {"id": "1", "status": "ready", "extracted_text": "some material", "updated_at": "t1", "token_estimate": 10, "source_name": "Doc"}


def test_explain_bin_retries_on_truncated_json_then_succeeds(monkeypatch):
    monkeypatch.setattr(eng, "ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(eng, "SUPABASE_URL", "https://x.test")
    monkeypatch.setattr(eng, "SUPABASE_KEY", "service-key")

    calls = {"n": 0}
    valid = '{"tldr": "ok", "sections": [{"heading": "H", "body_md": "B"}], "mind_map": null, "quiz": []}'

    def post_fn():
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(200, _usage_body('{"tldr": "truncated mid-string'))  # invalid JSON
        return _FakeResp(200, _usage_body(valid))

    monkeypatch.setattr(eng.httpx, "AsyncClient", _fake_client(post_fn))

    result = asyncio.run(eng.explain_bin("bin1", "user1", "graduate", [_ready_item()]))

    assert calls["n"] == 2
    assert result["lesson"]["tldr"] == "ok"


def test_explain_bin_never_leaks_raw_json_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(eng, "ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(eng, "SUPABASE_URL", "https://x.test")
    monkeypatch.setattr(eng, "SUPABASE_KEY", "service-key")

    def post_fn():
        return _FakeResp(200, _usage_body('{"tldr": "still truncated'))  # always invalid

    monkeypatch.setattr(eng.httpx, "AsyncClient", _fake_client(post_fn))

    result = asyncio.run(eng.explain_bin("bin1", "user1", "graduate", [_ready_item()]))

    assert result["lesson"] is None
    assert "{" not in result["error"]  # the exact regression: raw JSON syntax must never reach the user
    assert result["error"]


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
