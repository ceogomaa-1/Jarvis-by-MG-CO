"""
Jarvis Home API (Batch 67).

  GET   /business/home                  → cached blocks + layout + settings (FAST read, no LLM)
  POST  /business/home/refresh          → recompute blocks in the background (async)
  PUT   /business/home/layout           → persist drag/resize/reorder/remove
  PUT   /business/home/settings         → persist Home settings (e.g. default_landing)
  POST  /business/home/usage            → telemetry (views, click-throughs, first-action, dwell)
  POST  /business/home/command          → Phase 2 natural-language layout command
  GET   /business/home/suggestion       → Phase 3 pending adaptive suggestion
  POST  /business/home/suggestion/{id}  → accept/reject a suggestion

The view only READS what compose_home precomputed — the heavy work runs in the
Operator pipeline / this module's background task, never on page load.
"""
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.lib.business.operator.home_composer import compose_home
from backend.lib.business import home_layout as hl
from backend.lib.business import dashboard_studio as ds

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers(extra: dict | None = None) -> dict:
    h = {**_read_headers(), "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


async def _get(client: httpx.AsyncClient, table: str, params: dict) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        resp = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_read_headers(),
                                params=params, timeout=10.0)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            return resp.json()
    except Exception as e:
        print(f"HOME_ROUTES: read {table} failed: {e}")
    return []


async def _fetch_layout_row(client: httpx.AsyncClient, user_id: str) -> dict | None:
    rows = await _get(client, "business_home_layout", {
        "select": "layout,settings,is_default", "user_id": f"eq.{user_id}", "limit": "1"})
    return rows[0] if rows else None


async def _upsert_layout_row(client: httpx.AsyncClient, user_id: str, fields: dict) -> bool:
    payload = {"user_id": user_id, "updated_at": "now()", **fields}
    try:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/business_home_layout?on_conflict=user_id",
            headers=_write_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=payload, timeout=12.0)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"HOME_ROUTES: upsert layout failed: {e}")
        return False


# ── GET /business/home ────────────────────────────────────────────────────────

@router.get("/business/home")
async def get_home(user_id: str = ""):
    if not user_id:
        return {"blocks": [], "layout": hl.default_layout(), "settings": {"default_landing": True},
                "is_default": True, "suggestion": None, "composed": False}
    async with httpx.AsyncClient() as client:
        blocks = await _get(client, "business_home_blocks", {
            "select": "block_key,title,ai_summary,evidence,primary_action,secondary_actions,score,score_breakdown,status,updated_at",
            "user_id": f"eq.{user_id}", "order": "score.desc", "limit": "20"})
        layout_row = await _fetch_layout_row(client, user_id)
        suggestions = await _get(client, "business_home_suggestions", {
            "select": "id,message,proposed_layout,evidence,created_at",
            "user_id": f"eq.{user_id}", "status": "eq.pending",
            "order": "created_at.desc", "limit": "1"})
        custom_rows = await _get(client, "business_home_custom_blocks", {
            "select": "*", "user_id": f"eq.{user_id}", "status": "eq.active", "order": "created_at.asc"})

    # Batch 68: user-created blocks render in the same grid as the precomputed ones.
    custom_views = [ds.block_to_view(r) for r in custom_rows]
    custom_specs = ds.custom_layout_specs(custom_views)

    # Importance ranking drives default order: until the user customizes, regenerate the
    # default layout from the live block score order (debuggable via score_breakdown).
    score_order = [b["block_key"] for b in blocks] if blocks else None
    is_default = True if not layout_row else bool(layout_row.get("is_default", True))
    if is_default:
        layout = hl.default_layout(score_order, custom=custom_specs)
    else:
        layout = hl.normalize_layout(layout_row.get("layout"), score_order, custom=custom_specs)
    settings = (layout_row or {}).get("settings") or {"default_landing": True}

    return {
        "blocks": blocks + custom_views,
        "layout": layout,
        "settings": settings,
        "is_default": is_default,
        "suggestion": suggestions[0] if suggestions else None,
        "composed": bool(blocks) or bool(custom_views),
    }


# ── POST /business/home/refresh ───────────────────────────────────────────────

class RefreshRequest(BaseModel):
    user_id: str


@router.post("/business/home/refresh")
async def refresh_home(request: RefreshRequest, background_tasks: BackgroundTasks):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    background_tasks.add_task(compose_home, request.user_id, None)
    return {"status": "started"}


# ── PUT /business/home/layout ─────────────────────────────────────────────────

class LayoutRequest(BaseModel):
    user_id: str
    layout: dict


@router.put("/business/home/layout")
async def save_layout(request: LayoutRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    custom_specs = ds.custom_layout_specs(await ds.list_custom_blocks(request.user_id))
    layout = hl.normalize_layout(request.layout, custom=custom_specs)
    # Re-derive logical order/sizes from the dragged grid so NL commands stay consistent
    # (valid_keys includes custom blocks so they aren't dropped).
    if layout.get("layouts", {}).get("lg"):
        valid = set(layout["sizes"].keys())
        order, sizes = hl.derive_from_layouts(layout["layouts"], valid_keys=valid)
        layout["order"], layout["sizes"] = order, sizes
    async with httpx.AsyncClient() as client:
        ok = await _upsert_layout_row(client, request.user_id, {"layout": layout, "is_default": False})
    return {"ok": ok, "layout": layout}


# ── PUT /business/home/settings ───────────────────────────────────────────────

class SettingsRequest(BaseModel):
    user_id: str
    settings: dict


@router.put("/business/home/settings")
async def save_settings(request: SettingsRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    async with httpx.AsyncClient() as client:
        ok = await _upsert_layout_row(client, request.user_id, {"settings": request.settings})
    return {"ok": ok}


# ── POST /business/home/usage ─────────────────────────────────────────────────

class UsageEvent(BaseModel):
    block_key: str | None = None
    event_type: str            # 'view' | 'click_through' | 'first_action' | 'dwell'
    position: int | None = None
    dwell_ms: int | None = None
    metadata: dict | None = None


class UsageRequest(BaseModel):
    user_id: str
    events: list[UsageEvent]


_VALID_EVENTS = {"view", "click_through", "first_action", "dwell"}


@router.post("/business/home/usage")
async def log_usage(request: UsageRequest):
    if not request.user_id or not request.events:
        return {"ok": True, "logged": 0}
    payload = [{
        "user_id": request.user_id,
        "block_key": e.block_key,
        "event_type": e.event_type,
        "position": e.position,
        "dwell_ms": e.dwell_ms,
        "metadata": e.metadata or {},
    } for e in request.events if e.event_type in _VALID_EVENTS]
    if not payload:
        return {"ok": True, "logged": 0}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_home_usage",
                headers=_write_headers({"Prefer": "return=minimal"}),
                json=payload, timeout=10.0)
        return {"ok": resp.status_code in (200, 201, 204), "logged": len(payload)}
    except Exception as e:
        print(f"HOME_ROUTES: usage insert failed: {e}")
        return {"ok": False, "logged": 0}


# ── POST /business/home/command (Phase 2 — natural-language layout) ────────────

class CommandRequest(BaseModel):
    user_id: str
    command: str


@router.post("/business/home/command")
async def layout_command(request: CommandRequest):
    if not request.user_id or not request.command:
        raise HTTPException(status_code=400, detail="user_id and command required")
    custom_specs = ds.custom_layout_specs(await ds.list_custom_blocks(request.user_id))
    async with httpx.AsyncClient() as client:
        layout_row = await _fetch_layout_row(client, request.user_id)
        current = hl.normalize_layout((layout_row or {}).get("layout"), custom=custom_specs)
        new_layout, reply, changed = hl.apply_command(current, request.command, custom=custom_specs)
        if changed:
            await _upsert_layout_row(client, request.user_id, {"layout": new_layout, "is_default": False})
    return {"ok": True, "changed": changed, "reply": reply, "layout": new_layout}


# ── Phase 3 — adaptive suggestions (suggestion-only) ──────────────────────────

@router.get("/business/home/suggestion")
async def get_suggestion(user_id: str = ""):
    if not user_id:
        return {"suggestion": None}
    async with httpx.AsyncClient() as client:
        rows = await _get(client, "business_home_suggestions", {
            "select": "id,message,proposed_layout,evidence,created_at",
            "user_id": f"eq.{user_id}", "status": "eq.pending",
            "order": "created_at.desc", "limit": "1"})
    return {"suggestion": rows[0] if rows else None}


class ResolveSuggestionRequest(BaseModel):
    user_id: str
    decision: str  # 'accept' | 'reject'


@router.post("/business/home/suggestion/{suggestion_id}")
async def resolve_suggestion(suggestion_id: str, request: ResolveSuggestionRequest):
    if request.decision not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="decision must be accept|reject")
    async with httpx.AsyncClient() as client:
        rows = await _get(client, "business_home_suggestions", {
            "select": "proposed_layout", "id": f"eq.{suggestion_id}", "limit": "1"})
        proposed = rows[0].get("proposed_layout") if rows else None
        # Mark resolved either way (suggestion-only; user is always in control).
        try:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_home_suggestions?id=eq.{suggestion_id}",
                headers=_write_headers({"Prefer": "return=minimal"}),
                json={"status": "accepted" if request.decision == "accept" else "rejected",
                      "resolved_at": "now()"}, timeout=10.0)
        except Exception as e:
            print(f"HOME_ROUTES: resolve suggestion failed: {e}")
        applied = False
        if request.decision == "accept" and proposed:
            layout = hl.normalize_layout(proposed)
            applied = await _upsert_layout_row(client, request.user_id, {"layout": layout, "is_default": False})
            return {"ok": True, "applied": applied, "layout": layout}
    return {"ok": True, "applied": False}


# ── Batch 68 — direct dashboard interactions (the grid is editable without chat) ──

class CustomItemRequest(BaseModel):
    user_id: str
    block_id: str
    item: dict


@router.post("/business/home/custom/add-item")
async def custom_add_item(request: CustomItemRequest):
    if not request.user_id or not request.block_id:
        raise HTTPException(status_code=400, detail="user_id and block_id required")
    return await ds.ui_add_item(request.user_id, request.block_id, request.item or {})


@router.post("/business/home/custom/remove-item")
async def custom_remove_item(request: CustomItemRequest):
    if not request.user_id or not request.block_id:
        raise HTTPException(status_code=400, detail="user_id and block_id required")
    return await ds.ui_remove_item(request.user_id, request.block_id, request.item or {})


class CustomBlockRequest(BaseModel):
    user_id: str
    block_id: str


@router.post("/business/home/custom/delete")
async def custom_delete(request: CustomBlockRequest):
    if not request.user_id or not request.block_id:
        raise HTTPException(status_code=400, detail="user_id and block_id required")
    return await ds.execute_dashboard_tool(
        "control", {"action": "delete_block", "block_id": request.block_id}, request.user_id)


class CustomRestoreRequest(BaseModel):
    user_id: str


@router.post("/business/home/custom/restore")
async def custom_restore(request: CustomRestoreRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await ds.execute_dashboard_tool("control", {"action": "restore"}, request.user_id)
