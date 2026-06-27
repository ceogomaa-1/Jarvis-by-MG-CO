"""Creation pipeline — standalone mode + deploy routing.

The website builder must emit only validated client artifacts. Model failures are explicit;
there is no generic fallback that can be mistaken for completed work.
"""
import asyncio
from types import SimpleNamespace

import pytest

from backend.lib.business.creation import standalone_generator as sg
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


def test_missing_api_key_fails_instead_of_shipping_fallback(monkeypatch):
    monkeypatch.setattr(sg, "ANTHROPIC_API_KEY", "")
    with pytest.raises(sg.WebsiteGenerationError, match="API key"):
        asyncio.run(
            sg.generate_standalone_page(
                "make me a landing page for Brightsmile Dental",
                {"company_name": "MG&CO Technologies", "client_name": "Brightsmile Dental"},
            )
        )


def test_validated_page_uses_client_not_account_owner(monkeypatch):
    monkeypatch.setattr(sg, "ANTHROPIC_API_KEY", "test-key")

    async def fake_call(_prompt):
        return {
            "title": "Brightsmile Dental",
            "project_name": "brightsmile-dental",
            "summary": "A complete dental website.",
            "html": _valid_html(),
        }

    monkeypatch.setattr(sg, "_call_page_model", fake_call)
    result = asyncio.run(
        sg.generate_standalone_page(
            "make me a landing page for Brightsmile Dental",
            {"company_name": "MG&CO Technologies", "client_name": "Brightsmile Dental"},
        )
    )
    assert result["is_fallback"] is False
    assert "Brightsmile Dental" in result["html"]
    assert "MG&CO Technologies" not in result["html"]


def test_sanitize_name():
    assert sg._sanitize_name("My Cool Site!!") == "my-cool-site"
    assert sg._sanitize_name("") == "landing-page"


# ── deploy routing detectors ──────────────────────────────────────────────────
@pytest.mark.parametrize("msg,expected", [
    ("deploy it", True),
    ("publish my page", True),
    ("make it live", True),
    ("push it to github", True),
    ("go live", True),
    ("what's my revenue", False),
    ("make me a landing page", False),
])
def test_is_deploy_request(msg, expected):
    assert c._is_deploy_request(msg) is expected


@pytest.mark.parametrize("msg,expected", [
    ("deploy to github", True),
    ("push the full next.js project", True),
    ("deploy it", False),
    ("publish my page", False),
])
def test_wants_github_deploy(msg, expected):
    assert c._wants_github_deploy(msg) is expected


# ── standalone build handler event sequence ───────────────────────────────────
def test_standalone_build_event_sequence(monkeypatch):
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
    monkeypatch.setattr(c, "save_standalone_creation", lambda **kwargs: asyncio.sleep(0, result=None))
    req = SimpleNamespace(message="make me a landing page for a dental clinic", user_id="", conversation_id=None)
    ctx = {"company_name": "Brightsmile Dental", "industry": "dentistry"}

    async def run():
        seq = []
        html_seen = False
        async for kind, payload in c._run_standalone_build(req, ctx, None):
            if kind == "event":
                seq.append(payload.get("type"))
                if payload.get("type") == "html_artifact":
                    html_seen = True
                    assert payload["html"].startswith("<!DOCTYPE html>")
            else:
                seq.append(f"[{kind}]")
        return seq, html_seen

    seq, html_seen = asyncio.run(run())
    assert html_seen
    assert seq.index("plan") < seq.index("html_artifact") < seq.index("complete")
    assert "[chat_message]" in seq
