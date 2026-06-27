"""Creation pipeline — standalone mode + deploy routing.

Covers the offline-safe surface: the standalone generator's premium fallback, the deploy-intent
and github-route detectors, and the standalone build handler's event sequence. The live model
generation + real GitHub/Vercel deploys are not exercised here (no keys)."""
import asyncio
from types import SimpleNamespace

import pytest

from backend.lib.business.creation import standalone_generator as sg
from backend.routes.business import create as c


# ── standalone generator fallback (offline) ───────────────────────────────────
def test_fallback_is_premium_and_self_contained():
    r = sg._fallback_page("landing page for a dental clinic", {"company_name": "Brightsmile Dental"})
    assert r["is_fallback"] and r["html"].startswith("<!DOCTYPE html>")
    assert "Brightsmile Dental" in r["html"]
    assert r["project_name"] == "brightsmile-dental"
    # premium markers: tailwind CDN, a real font, scroll-reveal motion, reduced-motion guard
    assert "cdn.tailwindcss.com" in r["html"]
    assert "fonts.googleapis.com" in r["html"]
    assert "prefers-reduced-motion" in r["html"]


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


# ── standalone build handler event sequence (offline → fallback page) ─────────
def test_standalone_build_event_sequence(monkeypatch):
    monkeypatch.setattr(sg, "ANTHROPIC_API_KEY", "")  # force the offline fallback
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
