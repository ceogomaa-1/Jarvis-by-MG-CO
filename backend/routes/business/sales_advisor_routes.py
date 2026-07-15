"""Sales Advisor cockpit support endpoints.

Tells the frontend whether to show the "Sales Advisor" nav item (same enabled + tier gate
the chat tools use) and serves the analyze/poll/list/delete loop for the cockpit panel.
The engine is shared with the `sales__*` chat tools, so the panel and the docked Rue chat
always agree. Additive — does not touch the CRM or Leads cockpit endpoints.
"""
from fastapi import APIRouter

from backend.lib.billing import entitlements
from backend.lib.business.sales_advisor import config, engine

router = APIRouter()


@router.get("/business/sales-advisor/status")
async def sales_status(user_id: str = ""):
    """Gate the nav item: enabled iff the engine is configured AND the user's tier includes
    the MG&CO agency suite (same Emperor gate as Leads; grandfathered users map to Emperor)."""
    if not config.enabled():
        return {"enabled": False}
    tier_ok = True
    if user_id:
        try:
            caps = entitlements.for_user(user_id)
            tier_ok = bool(caps.get("leads"))
        except Exception:
            tier_ok = True  # fail open: don't hide the panel on a transient billing error
    return {"enabled": tier_ok, "tier_gated": (user_id and not tier_ok) or False}


@router.post("/business/sales-advisor/analyze")
async def sales_analyze(payload: dict):
    """Start a deep-research + pitch job (the cockpit's "Build My Pitch" button).
    Mirrors the chat tool sales__analyze_business exactly — same engine, same guards."""
    user_id = payload.get("user_id") or ""
    if not config.enabled():
        return {"ok": False, "error": "Sales Advisor is off (ANTHROPIC_API_KEY not set).", "data": None}
    if user_id:
        try:
            allowed, reason = entitlements.leads_allowed(user_id)
        except Exception:
            allowed, reason = True, ""
        if not allowed:
            return {"ok": False, "error": reason, "data": None, "upgrade": "emperor"}
    res = await engine.start_analysis(user_id,
                                      maps_url=payload.get("maps_url"),
                                      business_name=payload.get("business_name"),
                                      notes=payload.get("notes"))
    return {"ok": res.ok, "error": res.error, "data": res.data}


@router.get("/business/sales-advisor/report")
async def sales_report(user_id: str, report_id: str = ""):
    """Poll one report (status/progress while running; the full report once complete)."""
    res = await engine.get_report(user_id, report_id or None)
    return {"ok": res.ok, "error": res.error, "data": res.data}


@router.get("/business/sales-advisor/list")
async def sales_list(user_id: str, limit: int = 50):
    """Report history for the cockpit's left rail."""
    res = await engine.list_reports(user_id, limit=limit)
    return {"ok": res.ok, "error": res.error, "data": res.data}


@router.post("/business/sales-advisor/delete")
async def sales_delete(payload: dict):
    """Delete one report (cockpit history row action). Scoped to the caller's user_id."""
    user_id = payload.get("user_id") or ""
    report_id = payload.get("report_id") or ""
    if not user_id or not report_id:
        return {"ok": False, "error": "user_id and report_id are required.", "data": None}
    res = await engine.delete_report(user_id, report_id)
    return {"ok": res.ok, "error": res.error, "data": res.data}
