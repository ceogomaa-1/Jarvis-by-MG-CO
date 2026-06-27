"""Regression tests for the validated Next.js site generator.

Generation failures must stop before GitHub/Vercel instead of deploying a
generic emergency template.
"""

import pytest

from backend.lib.business.creation import site_generator
from backend.lib.business.creation.site_generator import generate_site


def _valid_page(name="Acme"):
    sections = "\n".join(
        f"<section><h2>{name} section {i}</h2><p>{'Specific useful copy. ' * 70}</p></section>"
        for i in range(6)
    )
    return f'''"use client"

import {{ motion }} from "motion/react"

export default function Home() {{
  return <main><nav>{name}</nav>{sections}<a href="#contact">Contact</a></main>
}}
'''


def _tool_result(**input_overrides):
    tool_input = {
        "project_name": "acme-site",
        "needs_database": False,
        "summary": "A clean landing page for Acme.",
        "layout_tsx": (
            'import "./globals.css"\n'
            "export default function Layout({ children }: { children: React.ReactNode }) "
            "{ return <html><body>{children}</body></html> }"
        ),
        "globals_css": (
            "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n"
            ":root { --bg: #fff; --accent: #123; }"
        ),
        "page_tsx": _valid_page(),
        "readme_md": "# acme-site\n",
    }
    tool_input.update(input_overrides)
    return tool_input


def test_legacy_fallback_is_disabled():
    with pytest.raises(site_generator.SiteGenerationError, match="disabled"):
        site_generator._fallback_site(
            "build me a site for Acme",
            {"company_name": "Acme", "industry": "retail"},
        )


@pytest.mark.asyncio
async def test_generate_site_success_is_not_fallback(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")

    async def fake_call(_prompt):
        return _tool_result()

    monkeypatch.setattr(site_generator, "_call_site_model", fake_call)
    result = await generate_site(
        "build me a site for Acme",
        {"company_name": "MG&CO", "client_name": "Acme", "industry": "retail"},
    )
    assert result["is_fallback"] is False
    assert result["summary"] == "A clean landing page for Acme."


@pytest.mark.asyncio
async def test_generate_site_api_exception_fails_closed(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")

    async def fake_call(_prompt):
        raise TimeoutError("boom")

    monkeypatch.setattr(site_generator, "_call_site_model", fake_call)
    with pytest.raises(site_generator.SiteGenerationError, match="Nothing was pushed"):
        await generate_site(
            "build me a site for Acme",
            {"company_name": "MG&CO", "client_name": "Acme", "industry": "retail"},
        )


@pytest.mark.asyncio
async def test_generate_site_rejects_account_owner_brand_leak(monkeypatch):
    monkeypatch.setattr(site_generator, "ANTHROPIC_API_KEY", "test-key")

    async def fake_call(_prompt):
        return _tool_result(page_tsx=_valid_page("MG&CO"))

    monkeypatch.setattr(site_generator, "_call_site_model", fake_call)
    with pytest.raises(site_generator.SiteGenerationError, match="account owner's company"):
        await generate_site(
            "build me a site for Acme",
            {"company_name": "MG&CO", "client_name": "Acme", "industry": "retail"},
        )


def test_crm_mention_does_not_enable_database():
    assert site_generator._needs_db(
        "Build a website for this restaurant client from my CRM"
    ) is False
    assert site_generator._needs_db(
        "Build a restaurant website with an online reservation form"
    ) is True
