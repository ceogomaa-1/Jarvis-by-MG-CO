"""
Read a user's GoHighLevel structure + data — strictly read-only.

Everything goes through the existing GoHighLevelConnector
(get_connector_for_user(user_id, "gohighlevel")), so it respects the user's stored
Private Integration token + Location ID and never mutates GHL.

Structure: pipelines (+ ordered stages), custom field definitions, tags.
Data: async generators that page through ALL contacts / opportunities, plus
per-contact notes + tasks, and businesses (companies).
"""
from typing import AsyncIterator

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user

_PAGE = 100


async def get_ghl(user_id: str, account_label: str = "default"):
    """Return the user's authenticated GHL connector, or None if not connected."""
    return await get_connector_for_user(user_id, "gohighlevel", account_label)


# ── structure ────────────────────────────────────────────────────────────────
async def read_structure(ghl) -> ConnectorResult:
    """
    Read the full GHL configuration we mirror into Twenty:
      { pipelines: [{id, name, stages:[{id, name}]}],
        custom_fields: [{id, name, dataType, model, options}],
        tags: [{id, name}] }
    Partial failures are surfaced per-section rather than aborting everything.
    """
    out: dict = {"pipelines": [], "custom_fields": [], "tags": [], "warnings": []}

    pipes = await ghl.list_pipelines()
    if pipes.ok:
        for p in (pipes.data or {}).get("pipelines", []):
            out["pipelines"].append({
                "id": p.get("id"),
                "name": p.get("name") or "Pipeline",
                "stages": [
                    {"id": s.get("id"), "name": s.get("name") or "Stage"}
                    for s in (p.get("stages") or [])
                ],
            })
    else:
        out["warnings"].append(f"pipelines: {pipes.error}")

    cf = await ghl.get_custom_fields()
    if cf.ok:
        out["custom_fields"] = (cf.data or {}).get("customFields", []) or []
    else:
        out["warnings"].append(f"custom_fields: {cf.error}")

    tags = await ghl.get_tags()
    if tags.ok:
        out["tags"] = (tags.data or {}).get("tags", []) or []
    else:
        out["warnings"].append(f"tags: {tags.error}")

    return ConnectorResult(ok=True, data=out)


# ── data (paged) ─────────────────────────────────────────────────────────────
async def iter_contacts(ghl, *, max_records: int | None = None) -> AsyncIterator[dict]:
    """Yield every contact, paging via meta.startAfter / meta.startAfterId."""
    yielded = 0
    start_after = start_after_id = None
    for _ in range(10_000):  # safety cap
        res = await ghl.list_contacts_v2(limit=_PAGE, start_after_id=start_after_id, start_after=start_after)
        if not res.ok:
            return
        data = res.data or {}
        contacts = data.get("contacts", []) or []
        if not contacts:
            return
        for c in contacts:
            yield c
            yielded += 1
            if max_records and yielded >= max_records:
                return
        meta = data.get("meta", {}) or {}
        start_after = meta.get("startAfter")
        start_after_id = meta.get("startAfterId")
        if not start_after_id and not start_after:
            return


async def iter_opportunities(ghl, pipeline_id: str, *, max_records: int | None = None) -> AsyncIterator[dict]:
    """Yield every opportunity in one pipeline, paging via meta cursors."""
    yielded = 0
    start_after = start_after_id = None
    for _ in range(10_000):
        res = await ghl.search_opportunities_page(
            pipeline_id, limit=_PAGE, start_after=start_after, start_after_id=start_after_id
        )
        if not res.ok:
            return
        data = res.data or {}
        opps = data.get("opportunities", []) or []
        if not opps:
            return
        for o in opps:
            yield o
            yielded += 1
            if max_records and yielded >= max_records:
                return
        meta = data.get("meta", {}) or {}
        start_after = meta.get("startAfter")
        start_after_id = meta.get("startAfterId")
        if not start_after_id and not start_after:
            return


async def get_contact_notes(ghl, contact_id: str) -> list[dict]:
    res = await ghl.get_contact_notes(contact_id)
    if not res.ok:
        return []
    return (res.data or {}).get("notes", []) or []


async def get_contact_tasks(ghl, contact_id: str) -> list[dict]:
    res = await ghl.get_contact_tasks(contact_id)
    if not res.ok:
        return []
    return (res.data or {}).get("tasks", []) or []


async def list_businesses(ghl) -> list[dict]:
    res = await ghl.list_businesses()
    if not res.ok:
        return []
    return (res.data or {}).get("businesses", []) or []
