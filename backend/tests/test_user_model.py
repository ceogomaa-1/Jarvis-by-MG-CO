"""
Regression tests for backend/user_model.py — Phase 2 (JARVIS-BRAIN-MAP.md
section B4): get_user_model() must distinguish "genuinely new user" from
"Supabase lookup failed", so summarize_user_for_prompt() doesn't tell Rue
a returning user is brand new during a transient outage, and
update_user_model() doesn't overwrite a real profile with a fresh one.
"""
import httpx
import pytest

from backend import user_model
from backend.user_model import (
    _fresh_model,
    get_user_model,
    summarize_user_for_prompt,
    update_user_model,
)


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

    async def get(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


# ─── get_user_model ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_supabase_configured_is_lookup_failed(monkeypatch):
    monkeypatch.setattr(user_model, "_SUPABASE_URL", "")
    monkeypatch.setattr(user_model, "_SUPABASE_KEY", "")
    model, lookup_failed = await get_user_model("user-1")
    assert lookup_failed is True
    assert model["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_existing_row_is_not_lookup_failed(monkeypatch):
    monkeypatch.setattr(user_model, "_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(user_model, "_SUPABASE_KEY", "test-key")
    saved = _fresh_model("user-1")
    saved["identity"]["name"] = "Mohamed"
    fake = _FakeAsyncClient(_FakeResponse(200, [{"model_data": saved}]))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    model, lookup_failed = await get_user_model("user-1")
    assert lookup_failed is False
    assert model["identity"]["name"] == "Mohamed"


@pytest.mark.asyncio
async def test_no_row_is_genuinely_new_user_not_lookup_failed(monkeypatch):
    monkeypatch.setattr(user_model, "_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(user_model, "_SUPABASE_KEY", "test-key")
    fake = _FakeAsyncClient(_FakeResponse(200, []))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    model, lookup_failed = await get_user_model("new-user")
    assert lookup_failed is False
    assert model["user_id"] == "new-user"


@pytest.mark.asyncio
async def test_non_200_is_lookup_failed(monkeypatch):
    monkeypatch.setattr(user_model, "_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(user_model, "_SUPABASE_KEY", "test-key")
    fake = _FakeAsyncClient(_FakeResponse(500, text="server error"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    model, lookup_failed = await get_user_model("user-1")
    assert lookup_failed is True
    assert model["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_request_exception_is_lookup_failed(monkeypatch):
    monkeypatch.setattr(user_model, "_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(user_model, "_SUPABASE_KEY", "test-key")
    fake = _FakeAsyncClient(exc=httpx.ConnectError("boom"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    model, lookup_failed = await get_user_model("user-1")
    assert lookup_failed is True
    assert model["user_id"] == "user-1"


# ─── summarize_user_for_prompt ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarize_says_lookup_unavailable_not_new_user(monkeypatch):
    async def _failed_lookup(user_id):
        return _fresh_model(user_id), True

    monkeypatch.setattr(user_model, "get_user_model", _failed_lookup)
    summary = await summarize_user_for_prompt("user-1")
    assert "PROFILE LOOKUP UNAVAILABLE" in summary
    assert "New user" not in summary


@pytest.mark.asyncio
async def test_summarize_says_new_user_when_genuinely_new(monkeypatch):
    async def _new_user(user_id):
        return _fresh_model(user_id), False

    monkeypatch.setattr(user_model, "get_user_model", _new_user)
    summary = await summarize_user_for_prompt("user-1")
    assert summary == "New user — still getting to know them. Ask questions."


# ─── update_user_model ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_skips_save_when_lookup_failed(monkeypatch):
    async def _failed_lookup(user_id):
        return _fresh_model(user_id), True

    async def _save_should_not_be_called(user_id, model):
        raise AssertionError("save_user_model must not be called when lookup_failed")

    monkeypatch.setattr(user_model, "get_user_model", _failed_lookup)
    monkeypatch.setattr(user_model, "save_user_model", _save_should_not_be_called)

    result = await update_user_model("user-1", "hello", "hi there")
    assert result is False
