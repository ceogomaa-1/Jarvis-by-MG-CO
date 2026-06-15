"""Best-effort listing-data lookup for an address, used to pre-fill OREA
Form 100 fields (purchase price, legal description, frontage, depth,
municipality) when not already supplied via known_values.

realtor.ca routinely blocks automated access, so this degrades to general
web search results when page fetches fail or return nothing. Always returns
a sources list; returns an empty listing_data dict if nothing reliable is
found — never guesses or invents values.
"""
import re

from backend.lib.business.model_router import SONNET
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.lib.business.real_estate.web_research import fetch_pages
from backend.tools.web_search import web_search

_EXTRACT_SYSTEM = (
    "You extract real estate listing details for a specific property from research "
    "text. ONLY return values that are explicitly stated in the provided text for "
    "THIS property. Never guess, estimate, or fill in typical values. If a field "
    "isn't found, omit it."
)


async def lookup_listing_data(address: str) -> dict:
    """Returns {"listing_data": {...}, "sources": [...], "note": "..."}."""
    if not address.strip():
        return {"listing_data": {}, "sources": [], "note": "No address provided."}

    queries = [
        f"{address} realtor.ca listing",
        f"{address} MLS listing price legal description",
    ]

    combined = ""
    all_urls: list[str] = []
    for q in queries:
        try:
            text = await web_search(q)
        except Exception as e:
            text = f"(search failed: {e})"
        all_urls.extend(re.findall(r"URL: (\S+)", text))
        combined += f"\n\n--- search: {q} ---\n{text}"

    seen: set[str] = set()
    dedup_urls: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            dedup_urls.append(u)

    pages, _used_playwright = await fetch_pages(dedup_urls, max_pages=3)
    for url, text in pages:
        combined += f"\n\nSOURCE: {url}\n{text}"

    note = ""
    if not pages and "realtor.ca" in combined.lower():
        note = (
            "realtor.ca listing pages are typically blocked for automated access — "
            "results are based on search snippets only and may be incomplete."
        )

    prompt = f"""Property address: "{address}"

Research text below (web search snippets + page extracts):
{combined[:10000]}

Extract any of the following details that are explicitly stated for THIS property:
- list_price (purchase price, numeral only, e.g. "650000")
- legal_description
- frontage (e.g. "50 ft")
- depth (e.g. "120 ft")
- municipality (city/town and province)

Return JSON only: {{"list_price": "...", "legal_description": "...", "frontage": "...", "depth": "...", "municipality": "..."}}
Omit any key you can't find. If nothing is found, return {{}}."""

    listing_data: dict = {}
    try:
        raw = await call_claude(system=_EXTRACT_SYSTEM, prompt=prompt, model=SONNET, max_tokens=500)
        parsed = parse_json_response(raw) or {}
        listing_data = {k: v for k, v in parsed.items() if v}
    except Exception as e:
        print(f"LISTING_LOOKUP: extraction error: {e}")

    return {
        "listing_data": listing_data,
        "sources": dedup_urls[:3],
        "note": note,
    }
