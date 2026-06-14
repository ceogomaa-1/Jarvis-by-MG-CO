"""
Regression tests for backend/lib/business/creation/site_generator.py — Phase 2
(JARVIS-BRAIN-MAP.md section B8): generate_site() must mark its result with
is_fallback so the chat route can tell the user when a generic emergency
template was deployed instead of the requested custom build.
"""
import httpx
import pytest

from backend.lib.business.creation import site_generator
from backend.lib.business.creation.site_generator import _fallback_site, generate_site


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

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


def _tool_use_response(**input_overrides):
    tool_input = {
        "project_name": "acme-site",
        "needs_database": False,
        "summary": "A clean landing page for Acme.",
        "layout_tsx": "",
        "globals_css": "",
        "page_tsx": "export default function Home() { return <div>Acme</div> }",
        "readme_md": "# acme-site\n",
    }
    tool_input.update(input_overrides)
    return _FakeResponse(200, {"content": [{"type": "tool_use", "name": "create_site", "input": tool_input}]})


# ─── _fallback_site ──────────────────────────────────────────────────────────

def test_fallback_site_is_marked_is_fallback():
    result = _fallback_site("build me a site for Acme", {"company_name": "Acme", "industry": "retail"})
    assert result["is_fallback"] is True
    assert "fallback" in result["summary"].lower()


# ─── generate_site ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_site_success_is_not_fallback(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_tool_use_response())
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    result = await generate_site("build me a site for Acme", {"company_name": "Acme", "industry": "retail"})
    assert result["is_fallback"] is False
    assert result["summary"] == "A clean landing page for Acme."


@pytest.mark.asyncio
async def test_generate_site_api_exception_falls_back(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(exc=httpx.ConnectError("boom"))
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    result = await generate_site("build me a site for Acme", {"company_name": "Acme", "industry": "retail"})
    assert result["is_fallback"] is True


@pytest.mark.asyncio
async def test_generate_site_non_200_falls_back(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_FakeResponse(500, text="server error"))
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    result = await generate_site("build me a site for Acme", {"company_name": "Acme", "industry": "retail"})
    assert result["is_fallback"] is True


@pytest.mark.asyncio
async def test_generate_site_missing_tool_use_falls_back(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")
    fake = _FakeAsyncClient(_FakeResponse(200, {"content": [{"type": "text", "text": "I refuse"}]}))
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    result = await generate_site("build me a site for Acme", {"company_name": "Acme", "industry": "retail"})
    assert result["is_fallback"] is True
