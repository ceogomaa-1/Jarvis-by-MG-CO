import base64
import os

import httpx

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

CANVAS_W = 600
CANVAS_H = 380


async def find_screenshot(query: str) -> dict:
    """
    Returns {"url": str | None, "is_fallback": bool, "svg_data_url": str | None}.
    svg_data_url is always set when url is None.
    """
    image_url = await _brave_image_search(query)
    if image_url:
        return {"url": image_url, "is_fallback": False, "svg_data_url": None}
    return {"url": None, "is_fallback": True, "svg_data_url": _fallback_svg(query)}


async def _brave_image_search(query: str) -> str | None:
    if not BRAVE_API_KEY:
        print("SCREENSHOT: BRAVE_SEARCH_API_KEY not set")
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/images/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                params={"q": f"{query} screenshot", "count": 5, "safesearch": "moderate"},
                timeout=10.0,
            )

        print(f"SCREENSHOT: Brave status={resp.status_code} query='{query[:60]}'")
        if resp.status_code != 200:
            print(f"SCREENSHOT: Brave error: {resp.text[:200]}")
            return None

        results = resp.json().get("results", [])
        print(f"SCREENSHOT: Got {len(results)} results. First 3 URLs:")
        for i, r in enumerate(results[:3]):
            props_url = (r.get("properties") or {}).get("url", "")
            direct_url = r.get("url", "")
            thumb_url = (r.get("thumbnail") or {}).get("src", "")
            print(f"  [{i}] properties.url={props_url[:80]}")
            print(f"       url={direct_url[:80]}")
            print(f"       thumbnail={thumb_url[:80]}")

        for r in results:
            url = (r.get("properties") or {}).get("url", "")
            if not url:
                url = r.get("url", "")
            if not url:
                url = (r.get("thumbnail") or {}).get("src", "")
            if url and any(ext in url.lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
                print(f"SCREENSHOT: Using: {url[:100]}")
                return url

        print("SCREENSHOT: No usable URL found — falling back to SVG")
        return None
    except Exception as e:
        print(f"SCREENSHOT: Exception: {e}")
        return None


# ─── Context-aware fallback SVG ───────────────────────────────────────────────

def _fallback_svg(query: str) -> str:
    q = query.lower()

    saas_terms = [
        "quickbooks", "stripe", "shopify", "xero", "salesforce", "hubspot",
        "slack", "notion", "figma", "github", "jira", "excel", "sheets",
        "word", "powerpoint", "outlook", "zoom", "teams", "gmail", "drive",
        "dropbox", "aws", "app", "software", "platform", "dashboard", "crm",
        "erp", "invoice", "report", "export", "import", "filter", "settings",
        "account", "billing", "subscription",
    ]
    trades_terms = [
        "framing", "plumbing", "electrical", "wiring", "carpentry", "concrete",
        "roofing", "flooring", "drywall", "pipe", "valve", "circuit", "wire",
        "nail", "screw", "wood", "door", "window", "install", "frame",
        "bracket", "stud", "joist", "beam", "foundation", "drill", "cut",
        "measure", "level", "insulation",
    ]

    if any(t in q for t in saas_terms):
        return _saas_svg(query)
    if any(t in q for t in trades_terms):
        return _diagram_svg(query)
    return _workspace_svg(query)


def _svg_b64(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _saas_svg(query: str) -> str:
    label = _esc(query[:55] + ("…" if len(query) > 55 else ""))
    q = query.lower()

    # Pick app-specific sidebar items
    if "quickbooks" in q:
        items = ["Dashboard", "Banking", "Sales", "Expenses", "Reports", "Taxes"]
    elif "stripe" in q:
        items = ["Home", "Payments", "Balances", "Customers", "Reports", "Developers"]
    elif "shopify" in q:
        items = ["Home", "Orders", "Products", "Customers", "Analytics", "Settings"]
    elif "salesforce" in q or "crm" in q:
        items = ["Home", "Leads", "Contacts", "Accounts", "Reports", "Dashboards"]
    elif "gmail" in q or "email" in q:
        items = ["Inbox", "Starred", "Sent", "Drafts", "Spam", "Labels"]
    elif "jira" in q:
        items = ["Board", "Backlog", "Sprints", "Reports", "Roadmap", "Settings"]
    else:
        items = ["Dashboard", "Reports", "Invoices", "Clients", "Settings", "Help"]

    nav_svgs = []
    active_idx = 1  # highlight second item by default
    for i, item in enumerate(items):
        cy = 72 + i * 40
        active = i == active_idx
        bg = f'fill="rgba(200,75,49,0.18)"' if active else 'fill="rgba(255,255,255,0.02)"'
        tc = "#c84b31" if active else "#777"
        fw = "600" if active else "400"
        nav_svgs.append(
            f'<rect x="8" y="{cy-15}" width="164" height="30" rx="5" {bg}/>'
            f'<circle cx="26" cy="{cy}" r="4" fill="{"#c84b31" if active else "#444"}"/>'
            f'<text x="38" y="{cy+5}" font-size="12" fill="{tc}" font-weight="{fw}" '
            f'font-family="system-ui,sans-serif">{_esc(item)}</text>'
        )
        if active:
            highlight_cy = cy

    nav_block = "\n  ".join(nav_svgs)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#13110f"/>
  <rect width="{CANVAS_W}" height="44" fill="#0d0b09"/>
  <text x="16" y="27" font-size="13" fill="#c84b31" font-weight="700" font-family="system-ui,sans-serif" letter-spacing="1">APP</text>
  <rect x="{CANVAS_W-200}" y="10" width="185" height="24" rx="4" fill="#1c1914"/>
  <text x="{CANVAS_W-190}" y="26" font-size="10" fill="#555" font-family="system-ui,sans-serif">Search…</text>
  <rect x="0" y="44" width="180" height="{CANVAS_H-44}" fill="#0d0b09"/>
  <rect x="180" y="44" width="1" height="{CANVAS_H-44}" fill="#222"/>
  {nav_block}
  <rect x="194" y="56" width="{CANVAS_W-210}" height="58" rx="6" fill="#1a1714"/>
  <rect x="208" y="68" width="160" height="9" rx="4" fill="#2a2825"/>
  <rect x="208" y="84" width="110" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="194" y="124" width="{CANVAS_W-210}" height="96" rx="6" fill="#1a1714"/>
  <rect x="208" y="138" width="200" height="9" rx="4" fill="#2a2825"/>
  <rect x="208" y="154" width="160" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="208" y="168" width="190" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="208" y="182" width="130" height="7" rx="3" fill="#1f1d1b"/>
  <circle cx="90" cy="{highlight_cy}" r="24" fill="rgba(200,75,49,0.12)" stroke="#c84b31" stroke-width="2"/>
  <circle cx="90" cy="{highlight_cy}" r="32" fill="none" stroke="#c84b31" stroke-width="0.8" opacity="0.4"/>
  <rect x="0" y="{CANVAS_H-28}" width="{CANVAS_W}" height="28" fill="rgba(0,0,0,0.55)"/>
  <text x="10" y="{CANVAS_H-10}" font-size="10" fill="#777" font-family="system-ui,sans-serif">{label}</text>
</svg>"""
    return _svg_b64(svg)


def _diagram_svg(query: str) -> str:
    label = _esc(query[:55] + ("…" if len(query) > 55 else ""))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#13110f"/>
  <text x="20" y="32" font-size="13" fill="#888" font-weight="600" font-family="system-ui,sans-serif" letter-spacing="1">DIAGRAM</text>
  <rect x="40" y="55" width="520" height="260" rx="8" fill="#1a1714" stroke="#2a2825" stroke-width="1"/>
  <rect x="70" y="80" width="200" height="120" rx="6" fill="#222" stroke="#333" stroke-width="1.5"/>
  <text x="170" y="146" font-size="11" fill="#888" text-anchor="middle" font-family="system-ui,sans-serif">Component A</text>
  <rect x="330" y="80" width="200" height="120" rx="6" fill="#222" stroke="#333" stroke-width="1.5"/>
  <text x="430" y="146" font-size="11" fill="#888" text-anchor="middle" font-family="system-ui,sans-serif">Component B</text>
  <line x1="270" y1="140" x2="330" y2="140" stroke="#444" stroke-width="1.5" stroke-dasharray="4,3"/>
  <polygon points="326,136 334,140 326,144" fill="#444"/>
  <rect x="160" y="220" width="280" height="60" rx="6" fill="#1e1b18" stroke="#2a2825" stroke-width="1"/>
  <text x="300" y="256" font-size="11" fill="#888" text-anchor="middle" font-family="system-ui,sans-serif">Base / Foundation</text>
  <circle cx="170" cy="140" r="22" fill="rgba(200,75,49,0.12)" stroke="#c84b31" stroke-width="2"/>
  <circle cx="170" cy="140" r="30" fill="none" stroke="#c84b31" stroke-width="0.8" opacity="0.45"/>
  <rect x="0" y="{CANVAS_H-28}" width="{CANVAS_W}" height="28" fill="rgba(0,0,0,0.55)"/>
  <text x="10" y="{CANVAS_H-10}" font-size="10" fill="#777" font-family="system-ui,sans-serif">{label}</text>
</svg>"""
    return _svg_b64(svg)


def _workspace_svg(query: str) -> str:
    label = _esc(query[:55] + ("…" if len(query) > 55 else ""))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#13110f"/>
  <rect x="30" y="30" width="{CANVAS_W-60}" height="{CANVAS_H-60}" rx="8" fill="#1a1714" stroke="#222" stroke-width="1"/>
  <rect x="50" y="50" width="{CANVAS_W-100}" height="36" rx="4" fill="#1e1b18"/>
  <rect x="62" y="62" width="120" height="12" rx="3" fill="#2a2825"/>
  <rect x="50" y="100" width="{CANVAS_W-100}" height="1" fill="#222"/>
  <rect x="50" y="115" width="260" height="9" rx="4" fill="#2a2825"/>
  <rect x="50" y="132" width="200" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="50" y="147" width="240" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="50" y="162" width="180" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="50" y="185" width="260" height="9" rx="4" fill="#2a2825"/>
  <rect x="50" y="202" width="220" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="50" y="217" width="190" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="{CANVAS_W-210}" y="115" width="148" height="120" rx="6" fill="#1e1b18" stroke="#2a2825" stroke-width="1"/>
  <rect x="{CANVAS_W-200}" y="126" width="128" height="8" rx="3" fill="#2a2825"/>
  <rect x="{CANVAS_W-200}" y="142" width="90" height="7" rx="3" fill="#1f1d1b"/>
  <rect x="{CANVAS_W-200}" y="157" width="110" height="7" rx="3" fill="#1f1d1b"/>
  <circle cx="130" cy="132" r="20" fill="rgba(200,75,49,0.12)" stroke="#c84b31" stroke-width="2"/>
  <circle cx="130" cy="132" r="28" fill="none" stroke="#c84b31" stroke-width="0.8" opacity="0.4"/>
  <rect x="0" y="{CANVAS_H-28}" width="{CANVAS_W}" height="28" fill="rgba(0,0,0,0.55)"/>
  <text x="10" y="{CANVAS_H-10}" font-size="10" fill="#777" font-family="system-ui,sans-serif">{label}</text>
</svg>"""
    return _svg_b64(svg)
