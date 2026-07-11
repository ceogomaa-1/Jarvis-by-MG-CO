"""mgcoleads cockpit support endpoints.

Tells the frontend whether to show the "Leads" nav item (env-gated on the SAME flag the
agent uses) and serves the scored-lead pipeline for the Leads cockpit panel. The read path
reuses the same store/engine the chat tools use, so the panel and the docked Rue chat
always agree. Additive — does not touch the CRM cockpit endpoints.
"""
from fastapi import APIRouter

from backend.lib.business.leads import config, engine, store
from backend.lib.billing import entitlements, store as billing_store

router = APIRouter()


@router.get("/business/leads/status")
async def leads_status(user_id: str = ""):
    """Gate the Leads nav item: enabled iff the lead engine is configured (LEADS_MAPS_API_KEY)
    AND the user's tier includes Leads (Emperor; grandfathered users map to Emperor)."""
    if not config.leads_enabled():
        return {"enabled": False}
    tier_ok = True
    if user_id:
        caps = entitlements.for_user(user_id)
        tier_ok = bool(caps.get("leads"))
    return {"enabled": tier_ok, "tier_gated": (user_id and not tier_ok) or False}


@router.get("/business/leads/list")
async def leads_list(user_id: str, tier: str = "", pushed: str = "", limit: int = 200):
    """Scored leads for the cockpit panel, ranked by score. Optional tier / pushed filters.

    Returns the raw rows (name, contact, gap/pitch, tier, score, pushed flag) plus per-tier
    counts. Industry/city filtering is done client-side off these rows (the set is small).
    """
    if not config.leads_enabled():
        return {"enabled": False, "count": 0, "leads": [], "tier_counts": {"A": 0, "B": 0, "C": 0}}
    pushed_filter = None
    if pushed.lower() in ("true", "1", "yes"):
        pushed_filter = True
    elif pushed.lower() in ("false", "0", "no"):
        pushed_filter = False
    rows = await store.list_leads(user_id, tier=(tier or None), limit=limit, pushed=pushed_filter)
    counts = {"A": 0, "B": 0, "C": 0}
    for r in rows:
        t = (r.get("tier") or "C").upper()
        counts[t] = counts.get(t, 0) + 1
    return {"enabled": True, "count": len(rows), "leads": rows, "tier_counts": counts}


@router.post("/business/leads/discover")
async def leads_discover(payload: dict):
    """Run a lead discovery (the cockpit's "Discover Businesses" button).

    Mirrors the chat tool find_leads exactly — same engine, scoring, dedupe and cache.
    Accepts a free-form `query` ("salons in Toronto"), or a `niche` + `city` pair that we
    join into the same "<niche> in <city>" shape the engine parses.
    """
    user_id = payload.get("user_id") or ""
    if not config.leads_enabled():
        return {"ok": False, "error": "Lead engine is off (LEADS_MAPS_API_KEY not set).", "data": None}
    # Tier gate: Rue Leads is Emperor-only (real Google Places cash cost). Grandfathered
    # users map to Emperor, so existing users are unaffected.
    if user_id:
        allowed, reason = entitlements.leads_allowed(user_id)
        if not allowed:
            return {"ok": False, "error": reason, "data": None, "upgrade": "emperor"}
    query = (payload.get("query") or "").strip()
    if not query:
        niche = (payload.get("niche") or "").strip()
        city = (payload.get("city") or "").strip()
        query = f"{niche} in {city}".strip() if city else niche
    res = await engine.run_search(user_id, query, payload.get("max_results"))
    # Meter billable lookups for Emperor overage (only count a successful run that returned leads).
    if res.ok and user_id:
        count = len((res.data or {}).get("leads", [])) if isinstance(res.data, dict) else 0
        if count:
            billing_store.add_leads_usage(user_id, count)
    return {"ok": res.ok, "error": res.error, "data": res.data}


@router.post("/business/leads/push")
async def leads_push(payload: dict):
    """Bulk push selected leads into the Rue CRM (the cockpit's "push to CRM" button).

    Mirrors the chat tool exactly: select by tier and/or explicit names. Idempotent — skips
    leads already pushed; companies de-dupe on name in the user's own workspace.
    """
    user_id = payload.get("user_id") or ""
    if not config.leads_enabled():
        return {"ok": False, "error": "Lead engine is off (LEADS_MAPS_API_KEY not set).", "data": None}
    res = await engine.push_to_crm(user_id, tier=payload.get("tier"),
                                   names=payload.get("names"), limit=int(payload.get("limit", 50)))
    return {"ok": res.ok, "error": res.error, "data": res.data}
