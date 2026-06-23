"""mgcoleads orchestration: ingest → score → persist → list → push-to-CRM.

The money loop. run_search fetches local businesses for a query, scores/tiers them, and
persists them (deduped, cached). list_leads serves conversational follow-ups ("only A-tier").
push_to_crm turns selected leads into real Companies in the Jarvis CRM (Twenty) via the
existing guarded write tools — scrape → score → pitch → track, all inside Jarvis.
"""
from urllib.parse import urlparse

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.leads import config, scoring, store
from backend.lib.business.leads.providers import ProviderError, get_provider

# Places we never pitch: permanently closed, or B2C categories MG&CO doesn't sell to.
_DEAD_STATUSES = {"CLOSED_PERMANENTLY"}


def _parse_query(query: str) -> tuple[str, str]:
    """Best-effort split of 'dental clinics in Mississauga' → ('dental clinics', 'Mississauga')."""
    q = (query or "").strip()
    for sep in (" in ", " near ", " around "):
        if sep in q.lower():
            i = q.lower().rindex(sep)
            return q[:i].strip(), q[i + len(sep):].strip()
    return q, ""


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        h = (urlparse(url).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h or None
    except Exception:
        return None


def _city_from_address(address: str | None) -> str | None:
    if not address:
        return None
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return parts[1] if len(parts) >= 2 else None


def _public_view(rows: list[dict]) -> list[dict]:
    """Compact, ranked shape for the agent/UI (no raw payloads or secrets)."""
    out = []
    for i, r in enumerate(sorted(rows, key=lambda x: x.get("score", 0), reverse=True), 1):
        out.append({
            "rank": i, "name": r.get("name"), "tier": r.get("tier"), "score": r.get("score"),
            "category": r.get("category"), "address": r.get("address"), "phone": r.get("phone"),
            "website": r.get("website") or None, "rating": r.get("rating"),
            "review_count": r.get("review_count"), "why": r.get("why"), "pitch": r.get("pitch"),
            "pushed_to_crm": r.get("pushed_to_crm", False),
        })
    return out


async def run_search(user_id: str, query: str, max_results: int | None = None) -> ConnectorResult:
    """Ingest + score + persist leads for a query. Caches repeat queries to control API cost."""
    if not config.leads_enabled():
        return ConnectorResult(ok=False, error="Lead engine is off (LEADS_MAPS_API_KEY not set).")
    query = (query or "").strip()
    if not query:
        return ConnectorResult(ok=False, error="Give me an industry + location, e.g. 'dental clinics in Mississauga'.")
    cap = min(max_results or config.MAX_RESULTS, config.MAX_RESULTS)

    # Cache: reuse a recent identical run instead of paying the provider again.
    cached = await store.find_recent_run(user_id, query, config.CACHE_TTL_HOURS)
    if cached:
        rows = await store.list_leads_for_run(user_id, cached["id"], limit=cap)
        if rows:
            return ConnectorResult(ok=True, data={"query": query, "cached": True,
                                                  "count": len(rows), "leads": _public_view(rows)})

    industry, location = _parse_query(query)
    try:
        raw_leads, api_calls = await get_provider().search(query, cap)
    except ProviderError as e:
        return ConnectorResult(ok=False, error=f"Lead lookup failed: {e}")

    # Score + filter (B2B only; drop permanently-closed + B2C-excluded categories).
    scored: list[dict] = []
    for lead in raw_leads:
        if lead.get("business_status") in _DEAD_STATUSES or scoring.is_b2c_excluded(lead):
            continue
        s = scoring.score_lead(lead)
        scored.append({**lead, **s})

    run_id = await store.create_run(user_id, query=query, industry=industry, location=location,
                                    provider=get_provider().name, result_count=len(scored), api_calls=api_calls)

    # Persist deduped by (user, place_id): insert new, re-score existing in place.
    existing = await store.existing_by_place(user_id, [l.get("place_id") for l in scored])
    new_rows, updated = [], 0
    for l in scored:
        row = _db_row(user_id, run_id, l)
        lid = existing.get(l.get("place_id"))
        if lid:
            await store.update_lead(lid, {k: row[k] for k in
                ("run_id", "score", "tier", "signals", "why", "pitch", "rating",
                 "review_count", "website", "has_hours", "business_status", "raw")})
            updated += 1
        else:
            new_rows.append(row)
    if new_rows:
        await store.insert_leads(new_rows)

    return ConnectorResult(ok=True, data={
        "query": query, "industry": industry, "location": location, "cached": False,
        "api_calls": api_calls, "count": len(scored), "new": len(new_rows), "updated": updated,
        "tier_counts": _tier_counts(scored), "leads": _public_view(scored)})


def _db_row(user_id: str, run_id: str | None, l: dict) -> dict:
    return {
        "user_id": store._user_id_to_uuid(user_id), "run_id": run_id, "place_id": l.get("place_id"),
        "name": l.get("name") or "Unknown", "category": l.get("category"), "address": l.get("address"),
        "phone": l.get("phone"), "website": l.get("website"), "rating": l.get("rating"),
        "review_count": l.get("review_count"), "price_level": l.get("price_level"),
        "business_status": l.get("business_status"), "has_hours": l.get("has_hours", False),
        "score": l.get("score", 0), "tier": l.get("tier", "C"), "signals": l.get("signals"),
        "why": l.get("why"), "pitch": l.get("pitch"), "raw": l.get("raw"),
    }


def _tier_counts(scored: list[dict]) -> dict:
    out = {"A": 0, "B": 0, "C": 0}
    for l in scored:
        out[l.get("tier", "C")] = out.get(l.get("tier", "C"), 0) + 1
    return out


async def list_leads(user_id: str, tier: str | None = None, limit: int = 50,
                     pushed: bool | None = None) -> ConnectorResult:
    if not config.leads_enabled():
        return ConnectorResult(ok=False, error="Lead engine is off (LEADS_MAPS_API_KEY not set).")
    rows = await store.list_leads(user_id, tier=tier, limit=limit, pushed=pushed)
    return ConnectorResult(ok=True, data={"count": len(rows), "tier": tier, "leads": _public_view(rows)})


async def push_to_crm(user_id: str, *, tier: str | None = None, names: list[str] | None = None,
                      limit: int = 25) -> ConnectorResult:
    """Push selected scored leads into the Jarvis CRM as Companies (with the gap/pitch as a note).

    Selection: by tier (e.g. all A-tier), or by explicit names, or both. Already-pushed leads
    are skipped. Reuses the guarded Twenty write tools, so creates are idempotent on company name
    and scoped to the user's own workspace.
    """
    if not config.leads_enabled():
        return ConnectorResult(ok=False, error="Lead engine is off (LEADS_MAPS_API_KEY not set).")
    from backend.lib.business.twenty.client import TwentyClient
    if not await TwentyClient.configured_for_user(user_id):
        return ConnectorResult(ok=False, error="No Jarvis CRM workspace is provisioned for you yet — can't push leads.")
    from backend.lib.business.twenty.tools import execute_twenty_tool

    rows = await store.list_leads(user_id, tier=tier, limit=max(limit, 50))
    if names:
        wanted = [n.strip().lower() for n in names if n.strip()]
        rows = [r for r in rows if any(w in (r.get("name") or "").lower() for w in wanted)]
    rows = [r for r in rows if not r.get("pushed_to_crm")][:limit]
    if not rows:
        return ConnectorResult(ok=True, data={"pushed": 0, "message": "No matching un-pushed leads found."})

    pushed, failed = [], []
    for r in rows:
        name = r.get("name")
        company_inp = {"name": name, "domain": _host(r.get("website")), "city": _city_from_address(r.get("address"))}
        res = await execute_twenty_tool("create_company", company_inp, user_id)
        if not res.ok:
            failed.append({"name": name, "error": res.error}); continue
        company_id = (res.data or {}).get("id")
        note = (f"MG&CO Lead — score {r.get('score')} (tier {r.get('tier')}). {r.get('why')}. "
                f"Phone: {r.get('phone') or 'n/a'} · {r.get('address') or ''} · "
                f"{r.get('review_count') or 0} reviews{(' ' + str(r['rating']) + '★') if r.get('rating') else ''}.")
        await execute_twenty_tool("add_note", {"title": "MG&CO Lead", "body": note,
                                               "company_id": company_id, "company_query": name}, user_id)
        if r.get("id"):
            await store.update_lead(r["id"], {"pushed_to_crm": True, "crm_company_id": company_id})
        pushed.append({"name": name, "company_id": company_id, "tier": r.get("tier")})

    return ConnectorResult(ok=True, data={"pushed": len(pushed), "companies": pushed,
                                          "failed": failed, "tier": tier})
