"""TOOL 4 — Seller Contact Research. Public-source research for property owners
/ FSBO sellers: web search + (when available) headless Playwright page reads,
merged via an LLM extraction pass. Degrades gracefully without Playwright."""
import asyncio
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.model_router import SONNET
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.tools.web_search import web_search

MAX_PAGES = 5
PAGE_TIMEOUT_MS = 10_000
USER_AGENT = "Mozilla/5.0 (compatible; JarvisOS1Bot/1.0)"

_EXTRACT_SYSTEM = (
    "You extract public contact information (names, phone numbers, emails) for a "
    "property owner or FSBO seller from research text. Public sources only — "
    "never invent information that isn't present in the text."
)


def _allowed_by_robots(url: str) -> bool:
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


async def _fetch_pages(urls: list[str]) -> tuple[list[tuple[str, str]], bool]:
    """Returns (list of (url, page_text), playwright_used)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [], False

    pages: list[tuple[str, str]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            for url in urls[:MAX_PAGES]:
                if not await asyncio.to_thread(_allowed_by_robots, url):
                    continue
                try:
                    page = await browser.new_page(user_agent=USER_AGENT)
                    await page.goto(url, timeout=PAGE_TIMEOUT_MS)
                    text = await page.inner_text("body")
                    pages.append((url, text[:5000]))
                    await page.close()
                except Exception as e:
                    print(f"SELLER_RESEARCH: page fetch failed for {url}: {e}")
            await browser.close()
        return pages, True
    except Exception as e:
        print(f"SELLER_RESEARCH: Playwright unavailable at runtime: {e}")
        return [], False


async def research_seller_contacts(query: str, region: str = "") -> ConnectorResult:
    if not query:
        return ConnectorResult(ok=False, error="query (address or owner name) is required.")

    search_query = f"{query} {region} owner contact for sale by owner".strip()
    try:
        search_text = await web_search(search_query)
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Web search failed: {e}")

    urls = re.findall(r"URL: (\S+)", search_text)[:MAX_PAGES]
    pages, used_playwright = await _fetch_pages(urls)

    combined = search_text
    for url, text in pages:
        combined += f"\n\nSOURCE: {url}\n{text}"

    region_note = f" (region: {region})" if region else ""
    prompt = f"""Research target: "{query}"{region_note}

From the research below, extract any PUBLIC contact information for the property owner / seller.

{combined[:8000]}

Return JSON only:
{{"contacts": [{{"name": "...", "phone": "...", "email": "...", "source_url": "...", "confidence": "high|medium|low", "notes": "..."}}]}}

If nothing relevant is found, return {{"contacts": []}}."""

    parsed = {"contacts": []}
    try:
        raw = await call_claude(system=_EXTRACT_SYSTEM, prompt=prompt, model=SONNET, max_tokens=1200)
        parsed = parse_json_response(raw) or {"contacts": []}
    except Exception as e:
        print(f"SELLER_RESEARCH: extraction error: {e}")

    sources_block = "Sources:\n" + "\n".join(f"- {u}" for u in urls) if urls else "Sources: none found"
    note = "" if used_playwright else "Playwright wasn't available at runtime, so this is based on web search results only."

    return ConnectorResult(
        ok=True,
        data={
            "query": query,
            "contacts": parsed.get("contacts", []),
            "sources": urls,
            "sources_block": sources_block,
            "degraded_to_web_search_only": not used_playwright,
            "note": note,
        },
    )
