import base64
import os

import httpx

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

# Standard canvas size all annotations use
CANVAS_W = 600
CANVAS_H = 380


async def find_screenshot(query: str) -> dict:
    """
    Search Brave image API for a relevant screenshot.
    Returns {"url": str | None, "is_fallback": bool, "svg_data_url": str}.
    svg_data_url is always populated (fallback if no real image found).
    """
    image_url = await _brave_image_search(query)
    fallback_svg = None

    if not image_url:
        fallback_svg = _generate_fallback_svg(query)
        return {"url": None, "is_fallback": True, "svg_data_url": fallback_svg}

    return {"url": image_url, "is_fallback": False, "svg_data_url": None}


async def _brave_image_search(query: str) -> str | None:
    if not BRAVE_API_KEY:
        print("SCREENSHOT: No BRAVE_SEARCH_API_KEY set — using fallback SVG")
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

        print(f"SCREENSHOT: Brave status={resp.status_code} for '{query}'")
        if resp.status_code != 200:
            print(f"SCREENSHOT: Brave error body: {resp.text[:300]}")
            return None

        data = resp.json()
        results = data.get("results", [])
        print(f"SCREENSHOT: Got {len(results)} results")

        for r in results:
            # Primary: properties.url (full-size image)
            url = (r.get("properties") or {}).get("url", "")
            # Fallback: direct url field
            if not url:
                url = r.get("url", "")
            # Second fallback: thumbnail
            if not url:
                url = (r.get("thumbnail") or {}).get("src", "")

            if url and any(ext in url.lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
                print(f"SCREENSHOT: Using image URL: {url[:100]}")
                return url

        print("SCREENSHOT: No usable image URL found — falling back to SVG")
        return None

    except Exception as e:
        print(f"SCREENSHOT: Exception: {e}")
        return None


def _generate_fallback_svg(label: str = "") -> str:
    """Generate a clean dark SaaS UI mockup as a base64 data URL."""
    short_label = label[:55] + ("…" if len(label) > 55 else "")
    # Escape XML special chars
    short_label = short_label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    nav_items = [
        ("Dashboard", 68),
        ("Reports",   112),
        ("Invoices",  156),
        ("Clients",   200),
        ("Settings",  244),
    ]

    nav_svgs = []
    for i, (name, cy) in enumerate(nav_items):
        active = i == 1  # highlight "Reports" by default
        bg_fill = 'fill="rgba(200,75,49,0.18)"' if active else 'fill="rgba(255,255,255,0.02)"'
        text_fill = '#c84b31' if active else '#888888'
        dot_fill = '#c84b31' if active else '#444444'
        nav_svgs.append(
            f'<rect x="8" y="{cy - 18}" width="164" height="36" rx="6" {bg_fill}/>'
            f'<circle cx="28" cy="{cy}" r="5" fill="{dot_fill}"/>'
            f'<text x="42" y="{cy + 5}" font-size="12" fill="{text_fill}" '
            f'font-family="system-ui,sans-serif" font-weight="{"600" if active else "400"}">{name}</text>'
        )
    nav_block = "\n  ".join(nav_svgs)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#13110f"/>

  <!-- Top bar -->
  <rect width="{CANVAS_W}" height="48" fill="#0e0c0a"/>
  <rect x="16" y="14" width="90" height="20" rx="4" fill="#1e1b18"/>
  <text x="26" y="28" font-size="11" fill="#c84b31" font-family="system-ui,sans-serif" font-weight="600" letter-spacing="2">JARVIS</text>
  <rect x="{CANVAS_W - 200}" y="12" width="180" height="24" rx="4" fill="#1e1b18"/>
  <text x="{CANVAS_W - 188}" y="28" font-size="10" fill="#555" font-family="system-ui,sans-serif">Search...</text>

  <!-- Sidebar -->
  <rect x="0" y="48" width="180" height="{CANVAS_H - 48}" fill="#0e0c0a"/>
  <rect x="180" y="48" width="1" height="{CANVAS_H - 48}" fill="#222"/>
  {nav_block}

  <!-- Main content -->
  <rect x="196" y="60" width="{CANVAS_W - 212}" height="64" rx="6" fill="#1a1714"/>
  <rect x="210" y="74" width="160" height="10" rx="5" fill="#2a2825"/>
  <rect x="210" y="92" width="100" height="8" rx="4" fill="#222"/>

  <rect x="196" y="136" width="{CANVAS_W - 212}" height="100" rx="6" fill="#1a1714"/>
  <rect x="210" y="152" width="220" height="8" rx="4" fill="#2a2825"/>
  <rect x="210" y="168" width="180" height="7" rx="3" fill="#222"/>
  <rect x="210" y="182" width="200" height="7" rx="3" fill="#222"/>
  <rect x="210" y="196" width="140" height="7" rx="3" fill="#222"/>

  <rect x="196" y="248" width="{CANVAS_W - 212}" height="64" rx="6" fill="#1a1714"/>
  <rect x="210" y="262" width="180" height="8" rx="4" fill="#2a2825"/>
  <rect x="210" y="278" width="120" height="7" rx="3" fill="#222"/>

  <!-- Highlight circle on Reports nav item -->
  <circle cx="90" cy="112" r="26" fill="rgba(200,75,49,0.12)" stroke="#c84b31" stroke-width="2"/>
  <circle cx="90" cy="112" r="34" fill="none" stroke="#c84b31" stroke-width="1" opacity="0.4"/>

  <!-- Label bar -->
  <rect x="0" y="{CANVAS_H - 30}" width="{CANVAS_W}" height="30" fill="rgba(0,0,0,0.6)"/>
  <text x="10" y="{CANVAS_H - 11}" font-size="10" fill="#888" font-family="system-ui,sans-serif">{short_label}</text>
</svg>"""

    b64 = base64.b64encode(svg.encode("utf-8")).decode()
    return f"data:image/svg+xml;base64,{b64}"
