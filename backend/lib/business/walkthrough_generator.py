import json
import os
import re

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

_SYSTEM = (
    "You are a technical trainer and SVG illustrator. "
    "Generate step-by-step walkthroughs with custom SVG illustrations. "
    "Return ONLY valid JSON. No markdown code fences. No explanation outside the JSON."
)

_PROMPT_TEMPLATE = '''You are a technical trainer creating a step-by-step walkthrough with custom SVG illustrations.

User request: "{query}"

Context from web search:
{context}

Generate a complete walkthrough. For each step decide if a visual illustration genuinely helps.

WHEN TO INCLUDE A VISUAL (needs_visual: true):
- User must locate a specific button, menu, or UI element
- Spatial layout matters (where something is on screen)
- Step involves measurements, dimensions, or physical placement
- Seeing an example clarifies the action

WHEN TO SKIP A VISUAL (needs_visual: false):
- "Log in to your account" — obvious, no layout needed
- Purely conceptual steps
- Simple text-entry steps with no spatial component

━━━━━━ SVG GENERATION RULES ━━━━━━

CRITICAL: All SVG attribute values MUST use single quotes to stay valid inside JSON strings.
Correct:  <rect x='10' y='10' fill='#0a0a0a'/>
Wrong:    <rect x="10" y="10" fill="#0a0a0a"/>

viewBox must be '0 0 600 400' for every illustration.

Color palette:
  Background:  fill='#0a0a0a'
  Panels/cards: fill='#1a1a1a' stroke='#333' stroke-width='1'
  Regular UI:  fill='#222' stroke='#444'
  HIGHLIGHTED: fill='rgba(245,158,11,0.15)' stroke='#f59e0b' stroke-width='2.5'
  Glow ring:   stroke='#f59e0b' stroke-width='1' opacity='0.4'
  Text:        fill='#e5e5e5' font-family='system-ui,sans-serif'
  Muted text:  fill='#888'
  Lines/arrows: stroke='#666' stroke-width='1.5'

FOR SOFTWARE walkthroughs — use the REAL nav items in the REAL order:

Stripe:     Home | Balances | Transactions | Customers | Products | Billing | Reports | Connect | Developers
QuickBooks: Dashboard | Banking | Sales | Expenses | Payroll | Reports | Taxes
Shopify:    Home | Orders | Products | Customers | Analytics | Marketing | Discounts | Apps
Gmail:      Compose | Inbox | Starred | Snoozed | Sent | Drafts | More
HubSpot:    Contacts | Companies | Deals | Activities | Reports | Workflows
Jira:       Board | Backlog | Active Sprints | Releases | Reports | Settings
Notion:     Search | Home | Inbox | Pages | Favorites | Workspaces
Xero:       Dashboard | Business | Accounting | Projects | Payroll | Contacts | Reports

Draw only the relevant PART of the screen — sidebar + the element being acted on.
Highlight the specific element with amber fill + amber stroke ring.

FOR PHYSICAL / TRADES walkthroughs — draw accurate technical diagrams:
- Cross-sections showing real component relationships
- Label every named part with lines/arrows
- Show measurements when relevant
- Use correct proportions

NEVER generate:
- "Component A → Component B" generic boxes
- Two-box flowcharts with arrows that represent nothing
- "JARVIS" branding or APP headers
- Any diagram that doesn't teach something specific about this exact step

If you cannot draw an accurate visual for a step, set needs_visual: false.
A clean text-only step beats a meaningless diagram.

━━━━━━ JSON FORMAT ━━━━━━

Return ONLY this JSON (no markdown, no code fences, start with {{):

{{
  "title": "Short title (max 60 chars)",
  "intro": "2-3 sentence intro",
  "steps": [
    {{
      "step_number": 1,
      "instruction": "Exact action with real UI element names",
      "detail": "Optional tip or note (empty string if none)",
      "needs_visual": false
    }},
    {{
      "step_number": 2,
      "instruction": "...",
      "detail": "...",
      "needs_visual": true,
      "visual": {{
        "type": "svg_illustration",
        "svg_content": "<svg viewBox='0 0 600 400' xmlns='http://www.w3.org/2000/svg'><rect width='600' height='400' fill='#0a0a0a'/><!-- ... full SVG here ... --></svg>",
        "caption": "Short descriptive caption"
      }}
    }}
  ]
}}

Use 4-8 steps. Make each SVG genuinely informative and accurate.'''


async def generate_walkthrough(query: str) -> dict:
    context_text, sources = await _search_with_sources(query)

    prompt = _PROMPT_TEMPLATE.format(
        query=query,
        context=context_text,
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 8096,
                    "system": _SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=90.0,
            )

        if resp.status_code != 200:
            print(f"WALKTHROUGH: Claude error {resp.status_code}: {resp.text[:200]}")
            return _fallback(query, sources)

        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        data = _parse_json(raw)
        if data:
            data["sources"] = sources
            _log_steps(data)
            return data

        print("WALKTHROUGH: Could not parse JSON, using fallback")
        return _fallback(query, sources)

    except Exception as e:
        print(f"WALKTHROUGH: Error: {e}")
        return _fallback(query, sources)


def _parse_json(raw: str) -> dict | None:
    """Robust JSON parser for Claude responses that may contain SVG content."""
    # Strip accidental markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find the outermost JSON object
    start = raw.find('{')
    if start == -1:
        return None
    depth = 0
    end = -1
    for i in range(start, len(raw)):
        if raw[i] == '{':
            depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        print(f"WALKTHROUGH: JSON parse failed: {e}")
        return None


def _log_steps(data: dict):
    steps = data.get("steps", [])
    print(f"WALKTHROUGH: Generated '{data.get('title', '')}' with {len(steps)} steps")
    for s in steps:
        has_v = s.get("needs_visual", False)
        svg_len = len(s.get("visual", {}).get("svg_content", "")) if has_v else 0
        print(f"  Step {s.get('step_number')}: needs_visual={has_v}, svg_len={svg_len}")


async def _search_with_sources(query: str) -> tuple[str, list[dict]]:
    sources = []
    if BRAVE_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": BRAVE_API_KEY,
                    },
                    params={"q": f"{query} tutorial steps", "count": 5},
                    timeout=10.0,
                )
            if resp.status_code == 200:
                results = resp.json().get("web", {}).get("results", [])
                lines = []
                for r in results[:4]:
                    title = r.get("title", "")
                    desc = r.get("description", "")
                    url = r.get("url", "")
                    if title and url:
                        sources.append({"title": title, "url": url})
                        lines.append(f"{title}: {desc}")
                return "\n".join(lines)[:1500], sources
        except Exception as e:
            print(f"WALKTHROUGH: Search error: {e}")

    try:
        from backend.tools.web_search import web_search
        text = await web_search(query=f"{query} tutorial steps how to")
        return (text or "")[:1500], sources
    except Exception:
        return "No search context available.", sources


def _fallback(query: str, sources: list = None) -> dict:
    return {
        "title": query[:60],
        "intro": f"Here is a step-by-step guide for: {query}",
        "sources": sources or [],
        "steps": [
            {
                "step_number": 1,
                "instruction": "Open the application and navigate to the relevant section.",
                "detail": "",
                "needs_visual": False,
            }
        ],
    }
