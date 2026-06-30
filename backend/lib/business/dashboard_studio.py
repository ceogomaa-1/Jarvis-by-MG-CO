"""
Dashboard Studio (Batch 68) — Jarvis builds and edits the user's Home dashboard.

Home is no longer a fixed template. Through one tool (dashboard__control) the chat brain
creates/edits/restyles/deletes arbitrary blocks and changes the theme — conversationally,
on REAL data. Block types:
  • list   — add/remove items (e.g. "My Expenses" with amounts + a running total)
  • note   — freeform text
  • metric — a single live number (value, unit, label, delta)
  • chart  — bar/line/pie over real data points
  • news   — live headlines pulled from the web (real internet data)

Custom blocks live in business_home_custom_blocks and render in the SAME grid as the
precomputed blocks, identified by the grid key "custom:<id>". Theme lives in
business_home_layout.settings.theme. Deletes are soft (status='deleted') so "undo" works.

These edits only touch the user's own dashboard, so they execute immediately (no
hold-to-confirm — that's reserved for outward-facing writes). Everything is reversible.
"""
import os
import uuid
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

VALID_TYPES = {"list", "note", "metric", "chart", "news"}

# Default grid footprint per custom type (cols×rows on the lg breakpoint).
TYPE_SIZE = {
    "list":   {"w": 4, "h": 4},
    "note":   {"w": 4, "h": 3},
    "metric": {"w": 3, "h": 2},
    "chart":  {"w": 5, "h": 4},
    "news":   {"w": 4, "h": 4},
}


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers(extra: dict | None = None) -> dict:
    h = {**_read_headers(), "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _err(msg: str) -> dict:
    return {"error": msg}


# ── persistence ──────────────────────────────────────────────────────────────

async def _get_blocks(client: httpx.AsyncClient, user_id: str, status: str = "active") -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_home_custom_blocks",
            headers=_read_headers(),
            params={"select": "*", "user_id": f"eq.{user_id}", "status": f"eq.{status}",
                    "order": "created_at.asc"},
            timeout=10.0)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            return resp.json()
    except Exception as e:
        print(f"DASHBOARD_STUDIO: get blocks failed: {e}")
    return []


async def _get_block(client: httpx.AsyncClient, user_id: str, block_id: str) -> dict | None:
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_home_custom_blocks",
            headers=_read_headers(),
            params={"select": "*", "id": f"eq.{block_id}", "user_id": f"eq.{user_id}", "limit": "1"},
            timeout=10.0)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"DASHBOARD_STUDIO: get block failed: {e}")
    return None


async def _insert_block(client: httpx.AsyncClient, row: dict) -> dict | None:
    try:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/business_home_custom_blocks",
            headers=_write_headers({"Prefer": "return=representation"}),
            json=row, timeout=12.0)
        if resp.status_code in (200, 201) and resp.json():
            return resp.json()[0]
        print(f"DASHBOARD_STUDIO: insert status={resp.status_code} body={resp.text[:200]}")
    except Exception as e:
        print(f"DASHBOARD_STUDIO: insert failed: {e}")
    return None


async def _patch_block(client: httpx.AsyncClient, user_id: str, block_id: str, fields: dict) -> bool:
    fields = {**fields, "updated_at": _now()}
    try:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/business_home_custom_blocks?id=eq.{block_id}&user_id=eq.{user_id}",
            headers=_write_headers({"Prefer": "return=minimal"}),
            json=fields, timeout=12.0)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"DASHBOARD_STUDIO: patch failed: {e}")
        return False


# ── view shape (merged into the Home blocks list) ────────────────────────────

def block_to_view(row: dict) -> dict:
    return {
        "block_key": f"custom:{row['id']}",
        "id": row["id"],
        "custom": True,
        "custom_type": row.get("block_type"),
        "title": row.get("title", ""),
        "config": row.get("config") or {},
        "data": row.get("data") or {},
        "style": row.get("style") or {},
        "status": "ok",
    }


async def list_custom_blocks(user_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        rows = await _get_blocks(client, user_id)
    return [block_to_view(r) for r in rows]


def custom_layout_specs(views: list[dict]) -> list[dict]:
    """Grid specs (key + default size) so custom blocks join the react-grid-layout."""
    out = []
    for v in views:
        sz = TYPE_SIZE.get(v.get("custom_type"), {"w": 4, "h": 3})
        out.append({"key": v["block_key"], "w": sz["w"], "h": sz["h"]})
    return out


# ── data normalizers ─────────────────────────────────────────────────────────

def _norm_items(items, want_amount: bool) -> list[dict]:
    """Normalize list/chart items to {id, label, amount|value}."""
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append({"id": uuid.uuid4().hex[:8], "label": it})
            continue
        if not isinstance(it, dict):
            continue
        row = {"id": it.get("id") or uuid.uuid4().hex[:8], "label": str(it.get("label", it.get("name", "")))}
        amt = it.get("amount", it.get("value", it.get("cost")))
        if amt is not None:
            try:
                row["amount" if want_amount else "value"] = float(amt)
            except (TypeError, ValueError):
                pass
        out.append(row)
    return out


def _list_total(items: list[dict]) -> float:
    return round(sum(float(i.get("amount", 0) or 0) for i in items), 2)


# ── news (real web data) ─────────────────────────────────────────────────────

async def _pull_news(topic: str) -> dict:
    """Pull live headlines for a topic via the always-on web search. Real internet data."""
    out = {"topic": topic, "summary": "", "pulled_at": _now()}
    if not topic:
        return out
    try:
        from backend.lib.business.web_scrape import web_search
        text = await web_search(f"{topic} latest news this week")
        out["summary"] = (text or "").strip()[:1800]
    except Exception as e:
        print(f"DASHBOARD_STUDIO: news pull failed: {e}")
        out["summary"] = ""
    return out


# ── layout helpers (move custom blocks; reuse the Home layout model) ─────────

async def _load_layout(client: httpx.AsyncClient, user_id: str) -> dict | None:
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_home_layout",
            headers=_read_headers(),
            params={"select": "layout,settings", "user_id": f"eq.{user_id}", "limit": "1"},
            timeout=10.0)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"DASHBOARD_STUDIO: load layout failed: {e}")
    return None


async def _save_layout_fields(client: httpx.AsyncClient, user_id: str, fields: dict) -> bool:
    try:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/business_home_layout?on_conflict=user_id",
            headers=_write_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json={"user_id": user_id, "updated_at": "now()", **fields}, timeout=12.0)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"DASHBOARD_STUDIO: save layout failed: {e}")
        return False


async def set_theme(user_id: str, theme: dict) -> bool:
    """Merge a partial theme ({accent, font, density, background}) into Home settings."""
    async with httpx.AsyncClient() as client:
        row = await _load_layout(client, user_id)
        settings = (row or {}).get("settings") or {"default_landing": True}
        cur = settings.get("theme") or {}
        settings["theme"] = {**cur, **{k: v for k, v in (theme or {}).items() if v is not None}}
        return await _save_layout_fields(client, user_id, {"settings": settings})


async def _move_custom_block(client: httpx.AsyncClient, user_id: str, block_key: str, position: str) -> bool:
    from backend.lib.business import home_layout as hl
    custom_rows = await _get_blocks(client, user_id)
    custom = custom_layout_specs([block_to_view(r) for r in custom_rows])
    row = await _load_layout(client, user_id)
    layout = hl.normalize_layout((row or {}).get("layout"), custom=custom)
    order = [k for k in layout["order"] if k != block_key]
    order.insert(0, block_key) if position == "top" else order.append(block_key)
    layout["order"] = order
    layout["layouts"] = hl.build_grid_layouts(order, layout["sizes"], layout["hidden"],
                                              valid_keys=set(layout["sizes"].keys()))
    return await _save_layout_fields(client, user_id, {"layout": layout, "is_default": False})


# ── the tool: execute_dashboard_tool ─────────────────────────────────────────

async def execute_dashboard_tool(action_name: str, inp: dict, user_id: str) -> dict:
    """Dispatch dashboard__control. `action_name` is 'control'; the real verb is inp['action']."""
    if not user_id:
        return _err("No user.")
    if not SUPABASE_URL or not SUPABASE_KEY:
        return _err("Dashboard storage is unavailable.")
    action = (inp.get("action") or "").strip()

    async with httpx.AsyncClient() as client:
        # ── create ───────────────────────────────────────────────
        if action == "create_block":
            btype = (inp.get("block_type") or "").strip()
            if btype not in VALID_TYPES:
                return _err(f"block_type must be one of {sorted(VALID_TYPES)}.")
            title = (inp.get("title") or btype.title()).strip()
            config, data, style = {}, {}, (inp.get("style") or {})
            if btype == "list":
                items = _norm_items(inp.get("items"), want_amount=True)
                config = {"unit": (inp.get("metric") or {}).get("unit") or inp.get("unit") or "$"}
                data = {"items": items, "total": _list_total(items)}
            elif btype == "note":
                data = {"text": inp.get("text") or ""}
            elif btype == "metric":
                m = inp.get("metric") or {}
                data = {"value": m.get("value"), "unit": m.get("unit", ""), "label": m.get("label", title), "delta": m.get("delta")}
            elif btype == "chart":
                series = _norm_items(inp.get("items"), want_amount=False)
                config = {"kind": inp.get("chart_kind") or "bar"}
                data = {"series": series}
            elif btype == "news":
                topic = inp.get("news_topic") or title
                config = {"topic": topic}
                data = await _pull_news(topic)
            row = {
                "user_id": user_id, "block_type": btype, "title": title,
                "config": config, "data": data, "style": style or {}, "status": "active",
            }
            created = await _insert_block(client, row)
            if not created:
                return _err("Could not create the block.")
            return {"ok": True, "action": action, "block_id": created["id"],
                    "block_key": f"custom:{created['id']}", "home_changed": True,
                    "message": f"Created the {btype} block \"{title}\"."}

        # ── update (rename / replace contents / re-pull news) ─────
        if action == "update_block":
            bid = inp.get("block_id")
            block = await _get_block(client, user_id, bid) if bid else None
            if not block:
                return _err("I couldn't find that block.")
            btype = block["block_type"]
            fields: dict = {}
            if inp.get("title"):
                fields["title"] = inp["title"]
            if "style" in inp and inp["style"]:
                fields["style"] = {**(block.get("style") or {}), **inp["style"]}
            data = block.get("data") or {}
            config = block.get("config") or {}
            if btype == "list" and inp.get("items") is not None:
                items = _norm_items(inp.get("items"), want_amount=True)
                data = {"items": items, "total": _list_total(items)}
            elif btype == "note" and inp.get("text") is not None:
                data = {"text": inp["text"]}
            elif btype == "metric" and inp.get("metric"):
                data = {**data, **inp["metric"]}
            elif btype == "chart":
                if inp.get("items") is not None:
                    data = {"series": _norm_items(inp.get("items"), want_amount=False)}
                if inp.get("chart_kind"):
                    config = {**config, "kind": inp["chart_kind"]}
            elif btype == "news" and inp.get("news_topic"):
                config = {**config, "topic": inp["news_topic"]}
                data = await _pull_news(inp["news_topic"])
            fields["data"] = data
            fields["config"] = config
            ok = await _patch_block(client, user_id, bid, fields)
            return {"ok": ok, "action": action, "block_id": bid, "home_changed": True,
                    "message": "Updated the block." if ok else "Update failed."}

        # ── add / remove items (list + chart) ─────────────────────
        if action in ("add_item", "remove_item"):
            bid = inp.get("block_id")
            block = await _get_block(client, user_id, bid) if bid else None
            if not block:
                return _err("I couldn't find that block.")
            btype = block["block_type"]
            data = block.get("data") or {}
            key = "items" if btype == "list" else "series"
            want_amount = btype == "list"
            arr = list(data.get(key, []))
            if action == "add_item":
                new_items = _norm_items([inp.get("item") or {"label": inp.get("text", ""),
                                                              "amount": (inp.get("item") or {}).get("amount")}], want_amount)
                # also allow bulk via items
                if inp.get("items"):
                    new_items = _norm_items(inp["items"], want_amount)
                arr.extend(new_items)
            else:
                target = (inp.get("item") or {})
                label = str(target.get("label", inp.get("text", ""))).lower()
                tid = target.get("id")
                arr = [i for i in arr if not ((tid and i.get("id") == tid) or
                                              (label and str(i.get("label", "")).lower() == label))]
            data[key] = arr
            if btype == "list":
                data["total"] = _list_total(arr)
            ok = await _patch_block(client, user_id, bid, {"data": data})
            return {"ok": ok, "action": action, "block_id": bid, "home_changed": True,
                    "message": ("Added." if action == "add_item" else "Removed.") if ok else "Failed."}

        # ── restyle (per-block accent/emphasis) ───────────────────
        if action == "restyle_block":
            bid = inp.get("block_id")
            block = await _get_block(client, user_id, bid) if bid else None
            if not block:
                return _err("I couldn't find that block.")
            style = {**(block.get("style") or {}), **(inp.get("style") or {})}
            ok = await _patch_block(client, user_id, bid, {"style": style})
            return {"ok": ok, "action": action, "block_id": bid, "home_changed": True,
                    "message": "Restyled the block." if ok else "Failed."}

        # ── move custom block ─────────────────────────────────────
        if action == "move_block":
            bid = inp.get("block_id")
            if not bid:
                return _err("Which block should I move?")
            ok = await _move_custom_block(client, user_id, f"custom:{bid}", inp.get("position") or "top")
            return {"ok": ok, "action": action, "block_id": bid, "home_changed": True,
                    "message": "Moved the block." if ok else "Failed."}

        # ── delete (soft) + restore (undo) ────────────────────────
        if action == "delete_block":
            bid = inp.get("block_id")
            if not bid:
                return _err("Which block should I delete?")
            ok = await _patch_block(client, user_id, bid, {"status": "deleted", "deleted_at": _now()})
            return {"ok": ok, "action": action, "block_id": bid, "home_changed": True,
                    "message": "Deleted the block — say 'undo' to bring it back." if ok else "Failed."}

        if action == "restore":
            deleted = await _get_blocks(client, user_id, status="deleted")
            if not deleted:
                return _err("Nothing to undo.")
            last = sorted(deleted, key=lambda r: r.get("deleted_at") or "", reverse=True)[0]
            ok = await _patch_block(client, user_id, last["id"], {"status": "active", "deleted_at": None})
            return {"ok": ok, "action": action, "block_id": last["id"], "home_changed": True,
                    "message": f"Restored \"{last.get('title','')}\"." if ok else "Failed."}

        # ── theme (whole dashboard colors/fonts) ──────────────────
        if action == "set_theme":
            ok = await set_theme(user_id, inp.get("theme") or {})
            return {"ok": ok, "action": action, "home_changed": True,
                    "message": "Updated your dashboard theme." if ok else "Failed."}

        return _err(f"Unknown dashboard action: {action or '(none)'}")


# ── direct UI mutations (the dashboard is interactive without chat) ──────────

async def ui_add_item(user_id: str, block_id: str, item: dict) -> dict:
    return await execute_dashboard_tool("control", {"action": "add_item", "block_id": block_id, "item": item}, user_id)


async def ui_remove_item(user_id: str, block_id: str, item: dict) -> dict:
    return await execute_dashboard_tool("control", {"action": "remove_item", "block_id": block_id, "item": item}, user_id)
