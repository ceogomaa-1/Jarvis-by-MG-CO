"""
Rue GO (Batch 70) — website__create / walkthrough__generate chat tools.

These wrap the existing /business/create and /business/show-me-how generators,
so the tests mock the same module-level functions test_creation_modes.py mocks
(backend.routes.business.create.*) plus the walkthrough generator, and assert
the adapter produces a renderable result with no duplicated generation logic.
"""
import asyncio

import pytest

from backend.lib.business.creation import chat_tools as ct
from backend.routes.business import create as c


def _valid_html(name="Brightsmile Dental"):
    sections = "".join(
        f"<section><h2>Section {i}</h2><p>{'Detailed client copy. ' * 90}</p></section>"
        for i in range(6)
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title><style>@media (prefers-reduced-motion: reduce) {{ * {{ animation: none }} }}</style>
</head><body><nav><a href="#contact">{name}</a></nav>{sections}
<a id="contact" href="mailto:hello@example.com">Contact</a></body></html>"""


def test_website_create_build_returns_renderable_artifact(monkeypatch):
    async def fake_generate(_message, _context):
        return {
            "title": "Brightsmile Dental",
            "project_name": "brightsmile-dental",
            "summary": "A complete dental website.",
            "html": _valid_html(),
            "is_fallback": False,
        }

    async def fake_enrich(_user_id, _message, context):
        return {**context, "client_name": "Brightsmile Dental"}

    monkeypatch.setattr(c, "generate_standalone_page", fake_generate)
    monkeypatch.setattr(c, "enrich_website_context", fake_enrich)
    monkeypatch.setattr(c, "save_standalone_creation", lambda **kwargs: asyncio.sleep(0, result="creation-1"))

    progress = []

    async def progress_cb(msg):
        progress.append(msg)

    result = asyncio.run(ct.run_website_create(
        {"action": "build", "brief": "make me a landing page for a dental clinic"},
        user_id="", progress_cb=progress_cb,
    ))

    assert result["ok"] is True
    assert result["render_as"] == "creation"
    assert result["title"] == "Brightsmile Dental"
    assert result["html"].startswith("<!DOCTYPE html>")
    assert progress  # at least one stage was reported


def test_website_create_missing_brief_errors_without_calling_generator(monkeypatch):
    called = False

    async def fake_generate(_message, _context):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(c, "generate_standalone_page", fake_generate)
    result = asyncio.run(ct.run_website_create({"action": "build", "brief": ""}, user_id=""))
    assert "error" in result
    assert called is False


def test_website_create_edit_updates_saved_creation(monkeypatch):
    original = _valid_html("Brightsmile Dental")
    edited_html = original.replace("Brightsmile Dental", "Brightsmile Family Dental", 1)

    async def fake_latest(_user_id):
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "kind": "standalone",
            "title": "Brightsmile Dental",
            "company_name": "Brightsmile Dental",
            "preview_html": original,
            "files": [{"path": "index.html", "content": original}],
            "user_message": "Build a website for Brightsmile Dental",
            "live_url": "https://brightsmile.vercel.app",
        }

    async def fake_edit(html, instruction, context):
        assert html == original
        return {"html": edited_html, "summary": "Updated only the hero headline."}

    async def fake_update(creation_id, html, summary, *, has_live_deployment):
        return None

    monkeypatch.setattr(c, "get_latest_deployable", fake_latest)
    monkeypatch.setattr(c, "edit_standalone_page", fake_edit)
    monkeypatch.setattr(c, "update_standalone_html", fake_update)

    result = asyncio.run(ct.run_website_create(
        {"action": "edit", "brief": "change the hero headline"}, user_id="user-test",
    ))

    assert result["ok"] is True
    assert result["creation_id"] == "11111111-1111-1111-1111-111111111111"
    assert "Brightsmile Family Dental" in result["html"]


def test_walkthrough_generate_returns_renderable_artifact(monkeypatch):
    async def fake_generate(_query):
        return {
            "title": "How to invoice a client",
            "intro": "Quick guide.",
            "steps": [{"step_number": 1, "instruction": "Open Invoices.", "needs_visual": False}],
            "sources": [],
        }

    monkeypatch.setattr(ct, "generate_walkthrough", fake_generate)
    result = asyncio.run(ct.run_walkthrough({"topic": "how to invoice a client"}, user_id=""))

    assert result["ok"] is True
    assert result["render_as"] == "walkthrough"
    assert result["title"] == "How to invoice a client"
    assert len(result["steps"]) == 1


def test_walkthrough_generate_missing_topic_errors():
    result = asyncio.run(ct.run_walkthrough({"topic": ""}, user_id=""))
    assert "error" in result
