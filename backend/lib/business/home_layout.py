"""
Jarvis Home layout model + natural-language layout commands (Batch 67, Phases 1–2).

The layout JSON is the source of truth for what the grid shows and where:

    {
      "version": 1,
      "order":   ["daily_briefing", ...],      # logical order → drives default grid + stacking
      "sizes":   {"daily_briefing": {"w":12,"h":2}, ...},
      "hidden":  ["revenue_metrics"],          # hidden block keys
      "layouts": {"lg":[...], "md":[...], "sm":[...], "xs":[...]}  # react-grid-layout positions
    }

Two worlds stay consistent:
  • Free-form drag/resize (react-grid-layout) writes `layouts` directly. On save we
    re-derive `order`/`sizes` from `layouts.lg` so NL commands keep working.
  • NL commands ("move CRM to top", "make Leads bigger", "build me a CEO dashboard")
    mutate `order`/`sizes`/`hidden`, then regenerate `layouts` deterministically.

Nothing here calls a model — the parser is deterministic (the chat route may fall back
to it). Pure functions only, so it's unit-testable in isolation.
"""
import re

# Canonical block identities — must match home_composer.BLOCK_KEYS.
BLOCK_KEYS = [
    "daily_briefing",
    "highest_value_client",
    "biggest_risk",
    "best_lead",
    "urgent_follow_up",
    "pipeline_status",
    "revenue_metrics",
    "calendar_intelligence",
    "tasks_priorities",
    "ai_recommendations",
]

DEFAULT_ORDER = list(BLOCK_KEYS)

DEFAULT_SIZES = {
    "daily_briefing":        {"w": 12, "h": 2},
    "highest_value_client":  {"w": 4,  "h": 3},
    "biggest_risk":          {"w": 4,  "h": 3},
    "best_lead":             {"w": 4,  "h": 3},
    "urgent_follow_up":      {"w": 4,  "h": 3},
    "pipeline_status":       {"w": 4,  "h": 3},
    "revenue_metrics":       {"w": 4,  "h": 3},
    "calendar_intelligence": {"w": 6,  "h": 3},
    "tasks_priorities":      {"w": 3,  "h": 3},
    "ai_recommendations":    {"w": 3,  "h": 3},
}

COLS = {"lg": 12, "md": 10, "sm": 6, "xs": 1}
MIN_W, MIN_H = 3, 2

# Friendly names → block_key. Order matters: longer/specific phrases first.
_SYNONYMS = [
    (r"daily\s*brief|briefing|morning\s*summary|overview", "daily_briefing"),
    (r"highest[-\s]*value|top\s*client|best\s*client|key\s*account", "highest_value_client"),
    (r"\brisk", "biggest_risk"),
    (r"best\s*lead|new\s*lead|overnight\s*lead|\bleads?\b", "best_lead"),
    (r"follow[-\s]*ups?|urgent", "urgent_follow_up"),
    (r"pipeline|\bcrm\b|deals?", "pipeline_status"),
    (r"revenue|metrics|numbers|kpis?|sales\s*figures", "revenue_metrics"),
    (r"calendar|meetings?|schedule|agenda", "calendar_intelligence"),
    (r"tasks?|to[-\s]?dos?|priorities|priority", "tasks_priorities"),
    (r"recommendations?|advice|suggestions?|ideas", "ai_recommendations"),
]


def resolve_block(name: str) -> str | None:
    """Map a user phrase to a canonical block_key (synonym-aware)."""
    t = (name or "").strip().lower()
    if not t:
        return None
    if t in BLOCK_KEYS:
        return t
    for pat, key in _SYNONYMS:
        if re.search(pat, t):
            return key
    return None


def _clamp_size(w: int, h: int, cols: int) -> tuple[int, int]:
    w = max(1, min(int(w), cols))
    h = max(MIN_H, int(h))
    return w, h


def build_grid_layouts(order: list[str], sizes: dict, hidden: list[str]) -> dict:
    """Deterministically pack visible blocks into react-grid-layout positions per breakpoint."""
    hidden_set = set(hidden or [])
    visible = [k for k in order if k in BLOCK_KEYS and k not in hidden_set]
    layouts: dict[str, list] = {}
    for bp, cols in COLS.items():
        items, x, y, row_h = [], 0, 0, 0
        for k in visible:
            sz = sizes.get(k) or DEFAULT_SIZES.get(k, {"w": 4, "h": 3})
            w, h = _clamp_size(sz.get("w", 4), sz.get("h", 3), cols)
            if cols == 1:
                w = 1
            if x + w > cols:
                x, y, row_h = 0, y + row_h, 0
            items.append({
                "i": k, "x": x, "y": y, "w": w, "h": h,
                "minW": min(MIN_W, cols), "minH": MIN_H,
            })
            x += w
            row_h = max(row_h, h)
        layouts[bp] = items
    return layouts


def default_layout(order_override: list[str] | None = None) -> dict:
    """A fresh default layout. `order_override` lets the importance ranking (block scores)
    drive the order for users who haven't customized yet."""
    order = [k for k in (order_override or DEFAULT_ORDER) if k in BLOCK_KEYS]
    # Append any blocks the override omitted so nothing is silently dropped.
    for k in DEFAULT_ORDER:
        if k not in order:
            order.append(k)
    sizes = {k: dict(DEFAULT_SIZES[k]) for k in BLOCK_KEYS}
    hidden: list[str] = []
    return {
        "version": 1,
        "order": order,
        "sizes": sizes,
        "hidden": hidden,
        "layouts": build_grid_layouts(order, sizes, hidden),
    }


def derive_from_layouts(layouts: dict) -> tuple[list[str], dict]:
    """Re-derive logical order + sizes from react-grid-layout `lg` positions (after a drag)."""
    lg = (layouts or {}).get("lg") or []
    items = [it for it in lg if it.get("i") in BLOCK_KEYS]
    items.sort(key=lambda it: (it.get("y", 0), it.get("x", 0)))
    order = [it["i"] for it in items]
    sizes = {it["i"]: {"w": int(it.get("w", 4)), "h": int(it.get("h", 3))} for it in items}
    for k in BLOCK_KEYS:
        order.append(k) if k not in order else None
        sizes.setdefault(k, dict(DEFAULT_SIZES[k]))
    return order, sizes


def normalize_layout(obj: dict | None, order_override: list[str] | None = None) -> dict:
    """Coerce any stored/blank layout into the full, renderable shape."""
    if not obj or not isinstance(obj, dict) or not obj.get("order"):
        return default_layout(order_override)
    order = [k for k in obj.get("order", []) if k in BLOCK_KEYS]
    for k in DEFAULT_ORDER:
        if k not in order:
            order.append(k)
    sizes = {k: (obj.get("sizes", {}).get(k) or dict(DEFAULT_SIZES[k])) for k in BLOCK_KEYS}
    hidden = [k for k in obj.get("hidden", []) if k in BLOCK_KEYS]
    layouts = obj.get("layouts") or build_grid_layouts(order, sizes, hidden)
    return {"version": 1, "order": order, "sizes": sizes, "hidden": hidden, "layouts": layouts}


# ── presets (for "build me a … dashboard") ───────────────────────────────────

PRESETS = {
    "ceo": {
        "label": "CEO dashboard",
        "order": ["daily_briefing", "revenue_metrics", "biggest_risk", "ai_recommendations",
                  "pipeline_status", "highest_value_client", "calendar_intelligence",
                  "urgent_follow_up", "tasks_priorities", "best_lead"],
        "big": {"revenue_metrics": {"w": 6, "h": 3}, "ai_recommendations": {"w": 6, "h": 3}},
        "hidden": [],
    },
    "sales": {
        "label": "sales dashboard",
        "order": ["daily_briefing", "pipeline_status", "best_lead", "highest_value_client",
                  "urgent_follow_up", "calendar_intelligence", "ai_recommendations",
                  "revenue_metrics", "tasks_priorities", "biggest_risk"],
        "big": {"pipeline_status": {"w": 6, "h": 3}, "best_lead": {"w": 6, "h": 3}},
        "hidden": [],
    },
    "operations": {
        "label": "operations dashboard",
        "order": ["daily_briefing", "tasks_priorities", "calendar_intelligence", "urgent_follow_up",
                  "biggest_risk", "pipeline_status", "ai_recommendations", "revenue_metrics",
                  "highest_value_client", "best_lead"],
        "big": {"tasks_priorities": {"w": 6, "h": 3}, "calendar_intelligence": {"w": 6, "h": 3}},
        "hidden": [],
    },
}


def _match_preset(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bceo\b|executive|founder", t):
        return "ceo"
    if re.search(r"\bsales\b|revenue\s*team|pipeline\s*focused|sell", t):
        return "sales"
    if re.search(r"operations?|ops\b|agency|restaurant|fulfillment|delivery|service\s*business", t):
        return "operations"
    return None


def _build_preset(name: str) -> dict:
    spec = PRESETS[name]
    sizes = {k: dict(DEFAULT_SIZES[k]) for k in BLOCK_KEYS}
    sizes.update({k: dict(v) for k, v in spec.get("big", {}).items()})
    order = [k for k in spec["order"] if k in BLOCK_KEYS]
    for k in DEFAULT_ORDER:
        if k not in order:
            order.append(k)
    hidden = list(spec.get("hidden", []))
    return {"version": 1, "order": order, "sizes": sizes, "hidden": hidden,
            "layouts": build_grid_layouts(order, sizes, hidden)}


# ── command parser ───────────────────────────────────────────────────────────

def parse_command(text: str) -> dict | None:
    """Deterministically parse a Home layout command. Returns an op dict or None."""
    t = (text or "").strip().lower()
    if not t:
        return None

    if re.search(r"\breset\b|default\s*layout|start\s*over|restore\s*default", t):
        return {"op": "reset"}

    if re.search(r"build|make|create|set\s*up|design|give\s*me", t) and re.search(r"dashboard|layout|home|workspace|cockpit", t):
        return {"op": "preset", "preset": _match_preset(t) or "ceo"}

    # hide / remove
    m = re.search(r"\b(hide|remove|drop|get\s*rid\s*of|take\s*(?:out|off))\b\s+(?:the\s+)?(.+)", t)
    if m:
        key = resolve_block(m.group(2))
        if key:
            return {"op": "hide", "target": key}

    # show / add back
    m = re.search(r"\b(show|add\s*back|bring\s*back|unhide|restore)\b\s+(?:the\s+)?(.+)", t)
    if m:
        key = resolve_block(m.group(2))
        if key:
            return {"op": "show", "target": key}

    # move to top / bottom
    m = re.search(r"\b(?:move|put|bring|pin)\b\s+(?:the\s+)?(.+?)\s+(?:to\s+|at\s+|on\s+)?(?:the\s+)?(top|first|bottom|last|up|down)\b", t)
    if m:
        key = resolve_block(m.group(1))
        where = m.group(2)
        if key:
            if where in ("top", "first"):
                return {"op": "move", "target": key, "where": "top"}
            if where in ("bottom", "last"):
                return {"op": "move", "target": key, "where": "bottom"}
            return {"op": "move", "target": key, "where": where}  # up | down

    # bigger / smaller
    m = re.search(r"\bmake\b\s+(?:the\s+)?(.+?)\s+(bigger|larger|wider|smaller|narrower|tinier)\b", t) \
        or re.search(r"\b(.+?)\s+(bigger|larger|wider|smaller|narrower|tinier)\b", t)
    if m:
        key = resolve_block(m.group(1))
        if key:
            grow = m.group(2) in ("bigger", "larger", "wider")
            return {"op": "resize", "target": key, "grow": grow}

    return None


def apply_command(layout_obj: dict | None, text: str) -> tuple[dict, str, bool]:
    """Apply a parsed NL command. Returns (new_layout, reply_text, changed)."""
    layout = normalize_layout(layout_obj)
    op = parse_command(text)
    if not op:
        return layout, "I couldn't tell what to change. Try: \"move CRM to the top\", \"make Leads bigger\", \"hide revenue\", or \"build me a CEO dashboard\".", False

    titles = {k: k.replace("_", " ").title() for k in BLOCK_KEYS}

    if op["op"] == "reset":
        return default_layout(), "Reset Home to the default layout.", True

    if op["op"] == "preset":
        preset = op["preset"]
        new = _build_preset(preset)
        return new, f"Built you a {PRESETS[preset]['label']} — reorganized Home around it.", True

    order = list(layout["order"])
    sizes = dict(layout["sizes"])
    hidden = list(layout["hidden"])
    target = op.get("target")

    if op["op"] == "hide":
        if target not in hidden:
            hidden.append(target)
        reply = f"Hid {titles.get(target, target)}."
    elif op["op"] == "show":
        hidden = [h for h in hidden if h != target]
        reply = f"{titles.get(target, target)} is back."
    elif op["op"] == "move":
        order = [k for k in order if k != target]
        where = op.get("where")
        if where == "top":
            order.insert(0, target)
        elif where == "bottom":
            order.append(target)
        elif where in ("up", "down"):
            # operate on visible order so "up"/"down" feels right
            idx = next((i for i, k in enumerate(layout["order"]) if k == target), 0)
            new_idx = max(0, idx - 1) if where == "up" else min(len(order), idx + 1)
            order.insert(new_idx, target)
        reply = f"Moved {titles.get(target, target)} {'to the top' if where=='top' else 'to the bottom' if where=='bottom' else where}."
    elif op["op"] == "resize":
        sz = dict(sizes.get(target, DEFAULT_SIZES[target]))
        if op["grow"]:
            sz["w"] = min(12, sz["w"] + (4 if sz["w"] <= 6 else 2))
            sz["h"] = min(6, sz["h"] + 1)
        else:
            sz["w"] = max(MIN_W, sz["w"] - 2)
            sz["h"] = max(MIN_H, sz["h"] - 1)
        sizes[target] = sz
        reply = f"Made {titles.get(target, target)} {'bigger' if op['grow'] else 'smaller'}."
    else:
        return layout, "I couldn't apply that change.", False

    new_layout = {
        "version": 1, "order": order, "sizes": sizes, "hidden": hidden,
        "layouts": build_grid_layouts(order, sizes, hidden),
    }
    return new_layout, reply, True


def is_home_layout_command(text: str) -> bool:
    """Cheap gate the chat route uses to detect a Home-customization message."""
    return parse_command(text) is not None
