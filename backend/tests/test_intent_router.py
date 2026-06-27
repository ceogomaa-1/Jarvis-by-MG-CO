"""
Regression tests for backend/lib/business/intent_router.py — the single
intent-classification call that replaced the frontend regex cascade
(agentEditDetector / showMeHowDetector / creationDetector / isDeployConfirmation,
see JARVIS-BRAIN-MAP.md section E).

These tests cover the deterministic short-circuits and the response-parsing /
fallback robustness with a mocked Anthropic call. The semantic classification
quality (does the model actually pick "chat" for "adjust the agent's greeting"
vs "create" for "build me a voice agent", etc.) was verified live against the
real Anthropic API for the full scenario list in JARVIS-BRAIN-MAP.md section D
and is not re-asserted here against a mocked model.
"""
import httpx
import pytest

from backend.lib.business import intent_router
from backend.lib.business.intent_router import classify_message_intent


# ─── Deterministic short-circuits (no model call) ──────────────────────────

@pytest.mark.asyncio
async def test_attachments_always_chat():
    result = await classify_message_intent("build me a website", has_attachments=True)
    assert result == {"intent": "chat", "reason": "attachments-or-empty"}


@pytest.mark.asyncio
async def test_empty_message_is_chat():
    result = await classify_message_intent("   ")
    assert result == {"intent": "chat", "reason": "attachments-or-empty"}


@pytest.mark.asyncio
async def test_no_api_key_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "")
    result = await classify_message_intent("help me think through my pricing strategy")
    assert result == {"intent": "chat", "reason": "no-api-key"}


@pytest.mark.asyncio
async def test_website_build_short_circuits_to_create():
    # Explicit website/landing-page builds are deterministically routed to the creation
    # pipeline BEFORE any model call (the fix for site asks misrouting to chat).
    for msg in ("build me a website", "make me a landing page for a dental clinic",
                "now deploy it to github and vercel", "publish it live"):
        result = await classify_message_intent(msg)
        assert result == {"intent": "create", "reason": "website-build-shortcircuit"}, msg


# ─── Response parsing / fallback robustness (mocked Anthropic call) ───────

class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


def _anthropic_response(text):
    return _FakeResponse(200, {"content": [{"text": text}]})


@pytest.mark.asyncio
async def test_valid_classification_passthrough(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_anthropic_response('{"intent": "create", "reason": "user wants a new agent"}'))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("build me a voice agent")
    assert result == {"intent": "create", "reason": "user wants a new agent"}


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_anthropic_response('```json\n{"intent": "show_me_how", "reason": "tutorial"}\n```'))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("how do I connect Stripe")
    assert result == {"intent": "show_me_how", "reason": "tutorial"}


@pytest.mark.asyncio
async def test_invalid_intent_value_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_anthropic_response('{"intent": "delete_everything", "reason": "??"}'))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("do something")
    assert result == {"intent": "chat", "reason": "fallback-default"}


@pytest.mark.asyncio
async def test_non_200_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_FakeResponse(500, text="server error"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("help me think through my pricing strategy")
    assert result == {"intent": "chat", "reason": "fallback-default"}


@pytest.mark.asyncio
async def test_request_exception_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(exc=httpx.ConnectError("boom"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("help me think through my pricing strategy")
    assert result == {"intent": "chat", "reason": "fallback-default"}


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(intent_router, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_anthropic_response("not json at all"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    result = await classify_message_intent("help me think through my pricing strategy")
    assert result == {"intent": "chat", "reason": "fallback-default"}
