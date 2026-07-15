"""Sales Advisor orchestration: start job → detached research+pitch run → poll/list.

Same shape as crm_enrich: the analyze endpoint answers immediately with a report_id and
the heavy work runs as a DETACHED asyncio task (outside the HTTP request), so the Render
120s window can't kill a deep research pass. The report row doubles as the job record —
the cockpit polls get_report until status flips to complete/failed.
"""
import asyncio

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.sales_advisor import config, pitch, research, store

# Keep strong references to detached jobs so the event loop never GCs one mid-run.
_JOBS: set[asyncio.Task] = set()


def _public_row(row: dict, *, full: bool = False) -> dict:
    out = {k: row.get(k) for k in ("id", "business_name", "maps_url", "status",
                                   "progress", "error", "model", "created_at", "updated_at")}
    if full:
        out["report"] = row.get("report")
        out["profile"] = (row.get("research") or {}).get("profile")
        out["audit"] = (row.get("research") or {}).get("audit")
        out["notes"] = row.get("notes")
    return out


async def _business_context(user_id: str) -> str | None:
    """Best-effort brand context for the pitch (display name / positioning). Never fatal."""
    try:
        from backend.lib.business.brand_config import get_brand_config
        brand = await get_brand_config(user_id)
        name = brand.get("display_name")
        if name:
            return f"Brand display name: {name}"
    except Exception as e:
        print(f"SALES.engine: brand context failed: {e}")
    return None


async def _run_job(report_id: str, user_id: str, maps_url: str | None,
                   business_name: str | None, notes: str | None) -> None:
    async def progress(msg: str):
        await store.update_report(report_id, {"progress": msg})

    try:
        bundle = await research.run_research(maps_url, business_name, notes, progress=progress)
        resolved = ((bundle.get("profile") or {}).get("name")
                    or (bundle.get("target") or {}).get("name") or business_name or "Unknown")
        await store.update_report(report_id, {
            "business_name": resolved, "research": bundle,
            "progress": "Research done — building your closer pitch…"})

        block = research.research_text(bundle)
        ctx = await _business_context(user_id)
        report, usage = await pitch.generate_pitch(block, business_context=ctx)

        await store.update_report(report_id, {
            "status": "complete", "progress": "Done", "report": report,
            "model": usage.get("model")})
        print(f"SALES.engine: report {report_id} complete for '{resolved}'")
    except Exception as e:
        print(f"SALES.engine: job {report_id} failed: {e}")
        await store.update_report(report_id, {
            "status": "failed", "progress": "Failed",
            "error": f"{type(e).__name__}: {e}"})


async def start_analysis(user_id: str, *, maps_url: str | None = None,
                         business_name: str | None = None,
                         notes: str | None = None) -> ConnectorResult:
    """Validate, create the report row, and detach the research+pitch job."""
    if not config.enabled():
        return ConnectorResult(ok=False, error="Sales Advisor is off (ANTHROPIC_API_KEY not set).")
    if not store.enabled():
        return ConnectorResult(ok=False, error="Sales Advisor storage is not configured (Supabase env missing).")
    maps_url = (maps_url or "").strip() or None
    business_name = (business_name or "").strip() or None
    if not maps_url and not business_name:
        return ConnectorResult(ok=False, error="Give me a Google Maps link or the business name (city helps).")

    placeholder = business_name or "Resolving from Maps link…"
    report_id = await store.create_report(user_id, business_name=placeholder,
                                          maps_url=maps_url, notes=notes, model=config.model())
    if not report_id:
        return ConnectorResult(ok=False, error="Couldn't create the analysis job — storage write failed.")

    task = asyncio.create_task(_run_job(report_id, user_id, maps_url, business_name, notes))
    _JOBS.add(task)
    task.add_done_callback(_JOBS.discard)

    return ConnectorResult(ok=True, data={
        "report_id": report_id, "status": "running",
        "message": ("Deep research started — usually 1-3 minutes. Open the Sales Advisor panel "
                    "to watch it land, or ask me for the report when it's done.")})


async def get_report(user_id: str, report_id: str | None = None) -> ConnectorResult:
    row = await (store.get_report(user_id, report_id) if report_id else store.latest_report(user_id))
    if not row:
        return ConnectorResult(ok=False, error="No matching report found.")
    return ConnectorResult(ok=True, data=_public_row(row, full=True))


async def list_reports(user_id: str, limit: int = 50) -> ConnectorResult:
    rows = await store.list_reports(user_id, limit=limit)
    return ConnectorResult(ok=True, data={"count": len(rows), "reports": [_public_row(r) for r in rows]})


async def delete_report(user_id: str, report_id: str) -> ConnectorResult:
    ok = await store.delete_report(user_id, report_id)
    return ConnectorResult(ok=ok, data={"deleted": ok} if ok else None,
                           error=None if ok else "Delete failed.")
