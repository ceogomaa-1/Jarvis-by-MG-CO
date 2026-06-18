"""TOOL — Lead Contact Enrichment. Best-effort, multi-source public-record lookup
for missing phone numbers / emails on a list of leads (e.g. parsed from an uploaded
CSV). Searches general web search plus people-search/brokerage/social sources
(Canada411/411.ca, WhitePages, realtor.ca, LinkedIn, Facebook) and an optional
Playwright page-read pass, merged via an LLM extraction pass.

Hard rule: never fabricate. Every returned phone/email must be traceable to a
source_url with a confidence level (high/medium/low). "Not found" is a valid,
expected result.
"""
import re

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.model_router import SONNET
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.lib.business.real_estate.web_research import fetch_pages
from backend.tools.web_search import web_search

MAX_PEOPLE = 5
MAX_PAGES_PER_PERSON = 3

_EXTRACT_SYSTEM = (
    "You extract public contact information (phone numbers and email addresses) for a "
    "named individual from research text. ONLY return a phone number or email that "
    "appears verbatim in the provided text and is clearly associated with this specific "
    "person — not a different person who happens to share the name. Never guess, "
    "complete, or normalize a number/address beyond what's written. If nothing reliable "
    "is found, return empty lists. Public sources only."
)


async def _research_person(person: dict, region: str, progress_cb=None) -> dict:
    name = (person.get("name") or "").strip()
    if not name:
        return {
            "input": person,
            "name": "",
            "found_phones": [],
            "found_emails": [],
            "status": "skipped",
            "notes": "No name provided for this row.",
            "sources_searched": [],
        }

    location_bits = " ".join(
        str(person.get(k, "")).strip()
        for k in ("address", "city", "company")
        if person.get(k)
    ).strip()

    queries = [
        f"{name} {location_bits} {region} phone number email".strip(),
        f"{name} {region} canada411 OR 411.ca OR whitepages OR realtor.ca OR linkedin".strip(),
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

    pages, _used_playwright = await fetch_pages(
        dedup_urls, max_pages=MAX_PAGES_PER_PERSON, progress_cb=progress_cb
    )
    for url, text in pages:
        combined += f"\n\nSOURCE: {url}\n{text}"

    prompt = f"""Person to research: "{name}"
Known details: {location_bits or "(none given)"}
Region: {region or "(not specified)"}

Research text below (web search snippets + page extracts):
{combined[:10000]}

Extract any phone numbers and email addresses that are explicitly tied to THIS person
(matching the name and, where possible, the known details above — not a different
person with a similar/identical name).

Return JSON only, in this exact shape:
{{"found_phones": [{{"value": "...", "source_url": "...", "confidence": "high|medium|low"}}],
"found_emails": [{{"value": "...", "source_url": "...", "confidence": "high|medium|low"}}],
"notes": "short note, e.g. why confidence is low or that this may be a different person"}}

If nothing reliable was found, return {{"found_phones": [], "found_emails": [], "notes": "Not found."}}."""

    parsed = {"found_phones": [], "found_emails": [], "notes": ""}
    try:
        raw = await call_claude(system=_EXTRACT_SYSTEM, prompt=prompt, model=SONNET, max_tokens=800)
        parsed = parse_json_response(raw) or parsed
    except Exception as e:
        parsed["notes"] = f"Extraction error: {e}"

    found_phones = parsed.get("found_phones") or []
    found_emails = parsed.get("found_emails") or []

    return {
        "input": person,
        "name": name,
        "found_phones": found_phones,
        "found_emails": found_emails,
        "status": "found" if (found_phones or found_emails) else "not_found",
        "notes": parsed.get("notes", ""),
        "sources_searched": dedup_urls[:MAX_PAGES_PER_PERSON],
    }


async def enrich_contacts(people: list[dict], region: str = "", progress_cb=None) -> ConnectorResult:
    if not people:
        return ConnectorResult(ok=False, error="people is required — a list of at least one row with a 'name'.")

    truncated = len(people) > MAX_PEOPLE
    people = people[:MAX_PEOPLE]

    results = []
    total = len(people)
    for i, person in enumerate(people, 1):
        if progress_cb:
            name = (person.get("name") or "this lead").strip()
            try:
                await progress_cb(f"Researching {name} ({i} of {total})…")
            except Exception:
                pass
        results.append(await _research_person(person, region, progress_cb=progress_cb))

    found = sum(1 for r in results if r["status"] == "found")
    total = len(results)
    summary = (
        f"Found at least one contact detail for {found} of {total} people searched. "
        "Every result includes its source URL and a confidence level (high/medium/low) — "
        "review before using, especially anything marked 'low'."
    )
    if truncated:
        summary += f" Only the first {MAX_PEOPLE} rows were processed in this call — ask again for the rest."

    return ConnectorResult(
        ok=True,
        data={
            "results": results,
            "summary": summary,
            "truncated": truncated,
        },
    )
