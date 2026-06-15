"""TOOL 4 — Seller Contact Research. Public-source research for property owners
/ FSBO sellers: web search + (when available) headless Playwright page reads,
merged via an LLM extraction pass. Degrades gracefully without Playwright."""
import re

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.model_router import SONNET
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.lib.business.real_estate.web_research import MAX_PAGES, fetch_pages
from backend.tools.web_search import web_search

_EXTRACT_SYSTEM = (
    "You extract public contact information (names, phone numbers, emails) for a "
    "property owner or FSBO seller from research text. Public sources only — "
    "never invent information that isn't present in the text."
)


async def research_seller_contacts(query: str, region: str = "") -> ConnectorResult:
    if not query:
        return ConnectorResult(ok=False, error="query (address or owner name) is required.")

    search_query = f"{query} {region} owner contact for sale by owner".strip()
    try:
        search_text = await web_search(search_query)
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Web search failed: {e}")

    urls = re.findall(r"URL: (\S+)", search_text)[:MAX_PAGES]
    pages, used_playwright = await fetch_pages(urls)

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
