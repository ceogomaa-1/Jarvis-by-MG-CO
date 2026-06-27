"""Best-effort grounding for website build requests.

When a user says "this client from my CRM", the website builder previously
skipped the CRM and sent only the account owner's profile to the model.  This
module resolves the named client, discovers a website URL when available, and
scrapes the current site before design begins.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.twenty.tools import execute_twenty_tool
from backend.lib.business.web_scrape import scrape
from backend.tools.web_search import web_search
from backend.lib.business.creation.website_quality import (
    extract_client_name,
    extract_url,
    normalise_url,
)


_WEBSITE_FIELD_NAMES = [
    "website",
    "website url",
    "website link",
    "domain",
    "url",
]
_DIRECTORY_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "yelp.com",
    "tripadvisor.com",
    "yellowpages.ca",
    "restaurantguru.com",
    "doordash.com",
    "ubereats.com",
    "skipthedishes.com",
}


async def enrich_website_context(
    user_id: str,
    user_message: str,
    context: dict | None = None,
) -> dict:
    """Return a copy of ``context`` enriched with target/research information.

    Every external read is best-effort. Missing CRM data must not crash a build,
    but it also must not be replaced with invented facts.
    """
    enriched = dict(context or {})
    client_name = enriched.get("client_name") or extract_client_name(user_message)
    website_url = enriched.get("website_url") or extract_url(user_message)

    if client_name:
        enriched["client_name"] = client_name

    if not website_url and user_id and client_name:
        website_url, crm_context = await _read_owned_crm(user_id, client_name)
        if crm_context:
            enriched["crm_context"] = crm_context

    if not website_url and user_id and client_name:
        website_url, ghl_context = await _read_gohighlevel(user_id, client_name)
        if ghl_context:
            enriched["crm_context"] = _merge_context(
                enriched.get("crm_context", ""),
                ghl_context,
            )

    if not website_url and client_name:
        website_url, search_context = await _search_for_official_site(client_name)
        if search_context:
            enriched["web_search_context"] = search_context

    if website_url:
        enriched["website_url"] = website_url
        try:
            result = await scrape(website_url, max_pages=5)
        except Exception as exc:
            enriched["website_research_error"] = f"{type(exc).__name__}"
        else:
            if result.get("text"):
                enriched["website_research"] = result["text"][:30_000]
                enriched["website_url"] = result.get("url") or website_url
                enriched["website_title"] = result.get("title") or ""
            elif result.get("error"):
                enriched["website_research_error"] = str(result["error"])[:300]

    if not enriched.get("website_research") and enriched.get("web_search_context"):
        enriched["website_research"] = enriched["web_search_context"]
        enriched["research_is_search_only"] = True

    return enriched


async def _read_owned_crm(user_id: str, client_name: str) -> tuple[str, str]:
    try:
        result = await execute_twenty_tool(
            "read_fields",
            {
                "object_type": "company",
                "query": client_name,
                "fields": _WEBSITE_FIELD_NAMES,
            },
            user_id,
        )
    except Exception:
        return "", ""
    if not result.ok:
        return "", ""

    data = result.data or {}
    fields = data.get("fields") or {}
    url = _find_website_value(fields)
    context = _format_crm_context(data.get("label") or client_name, fields)
    return url, context


async def _read_gohighlevel(user_id: str, client_name: str) -> tuple[str, str]:
    try:
        connector = await get_connector_for_user(user_id, "gohighlevel")
        if not connector:
            return "", ""
        result = await connector.search_contacts_v2(query=client_name, limit=5)
    except Exception:
        return "", ""
    if not result.ok:
        return "", ""

    data = result.data or {}
    url = _find_website_value(data)
    contacts = data.get("contacts") if isinstance(data, dict) else None
    if not isinstance(contacts, list):
        contacts = []
    safe_bits: list[str] = []
    for contact in contacts[:3]:
        if not isinstance(contact, dict):
            continue
        label = (
            contact.get("companyName")
            or contact.get("name")
            or "CRM contact"
        )
        safe_bits.append(str(label)[:160])
    context = "GoHighLevel matches: " + ", ".join(safe_bits) if safe_bits else ""
    return url, context


def _find_website_value(value: Any, parent_key: str = "") -> str:
    """Find URL-like data only under website/domain/url-shaped keys."""
    if isinstance(value, dict):
        for key, child in value.items():
            low_key = str(key).lower()
            if any(token in low_key for token in ("website", "domain", "url", "link")):
                found = normalise_url(child)
                if found:
                    return found
            found = _find_website_value(child, low_key)
            if found:
                return found
        return ""
    if isinstance(value, list):
        for child in value:
            found = _find_website_value(child, parent_key)
            if found:
                return found
        return ""
    if any(token in parent_key for token in ("website", "domain", "url", "link")):
        return normalise_url(value)
    return ""


def _format_crm_context(label: str, fields: dict) -> str:
    rows = [f"CRM company: {label}"]
    for key, value in fields.items():
        if value in (None, "", [], {}):
            continue
        rows.append(f"{key}: {str(value)[:500]}")
    return "\n".join(rows)[:4_000]


def _merge_context(left: str, right: str) -> str:
    return "\n".join(part for part in (left, right) if part)[:4_000]


async def _search_for_official_site(client_name: str) -> tuple[str, str]:
    """Use exact-name web search when CRM data does not expose a website URL."""
    try:
        results = await web_search(f'"{client_name}" official website')
    except Exception:
        return "", ""
    if not results or results.startswith("No results found"):
        return "", ""

    candidates = re.findall(r"^URL:\s*(https?://\S+)", results, re.MULTILINE)
    scored: list[tuple[int, str]] = []
    name_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", client_name.lower())
        if len(token) >= 4 and token not in {"family", "restaurant", "company", "business"}
    }
    for url in candidates:
        host = urlparse(url.rstrip(".,)")).netloc.lower().removeprefix("www.")
        if not host or any(host == domain or host.endswith(f".{domain}") for domain in _DIRECTORY_DOMAINS):
            continue
        score = sum(1 for token in name_tokens if token in host)
        scored.append((score, url.rstrip(".,)")))
    scored.sort(key=lambda item: item[0], reverse=True)
    return (scored[0][1] if scored else ""), results[:8_000]
