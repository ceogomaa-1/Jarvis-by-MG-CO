import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

_SYSTEM = (
    "You are a professional technical trainer. Generate detailed, accurate step-by-step "
    "walkthroughs for software tasks. Return ONLY valid JSON. No markdown, no code blocks."
)


async def generate_walkthrough(query: str) -> dict:
    """Generate structured walkthrough using Claude + web search context."""
    context_text, sources = await _search_with_sources(query)

    prompt = (
        f'The user wants to learn: "{query}"\n\n'
        f"Context from web search:\n{context_text}\n\n"
        "Generate a complete step-by-step walkthrough. Return ONLY this JSON:\n"
        "{\n"
        '  "title": "Short title (max 60 chars)",\n'
        '  "intro": "2-3 sentence intro",\n'
        '  "steps": [\n'
        '    {\n'
        '      "step_number": 1,\n'
        '      "instruction": "Exact UI instruction with element names",\n'
        '      "detail": "Optional tip or warning (empty string if none)",\n'
        '      "screenshot_query": "Specific image search for this UI screen",\n'
        '      "annotations": [\n'
        '        {\n'
        '          "type": "circle",\n'
        '          "x": 90,\n'
        '          "y": 112,\n'
        '          "radius": 28,\n'
        '          "color": "#f59e0b",\n'
        '          "label": "Click here"\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "ANNOTATION RULES:\n"
        "- x, y, radius are pixel coordinates for a 600x380 image\n"
        "- x=0,y=0 is top-left. Sidebar is x=0-180. Top bar is y=0-48.\n"
        "- annotation.type: circle, arrow, or highlight\n"
        "- For arrow: add 'x2', 'y2' for the arrowhead tip\n"
        "- For highlight: add 'width', 'height' for the highlight box\n"
        "- color should be one of: #f59e0b, #3b82f6, #10b981, #ef4444, #c84b31\n"
        "Use 4-8 steps. Return ONLY the JSON."
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
                    "max_tokens": 4096,
                    "system": _SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )

        if resp.status_code != 200:
            print(f"WALKTHROUGH: Claude error {resp.status_code}: {resp.text[:200]}")
            return _fallback(query, sources)

        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        raw = raw.strip("```json").strip("```").strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1:
            print(f"WALKTHROUGH: No JSON in response: {raw[:200]}")
            return _fallback(query, sources)

        data = json.loads(raw[start:end])
        data["sources"] = sources
        return data

    except json.JSONDecodeError as e:
        print(f"WALKTHROUGH: JSON parse error: {e}")
        return _fallback(query, sources)
    except Exception as e:
        print(f"WALKTHROUGH: Error: {e}")
        return _fallback(query, sources)


async def _search_with_sources(query: str) -> tuple[str, list[dict]]:
    """Search web and return (context_text, sources_list)."""
    sources = []

    # Try Brave web search for context + sources
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
            print(f"WALKTHROUGH: Brave search error: {e}")

    # Fallback to existing web_search tool
    try:
        from backend.tools.web_search import web_search
        text = await web_search(query=f"{query} tutorial steps how to")
        return (text or "")[:1500], sources
    except Exception as e:
        print(f"WALKTHROUGH: web_search fallback error: {e}")
        return "No search context available.", sources


def _fallback(query: str, sources: list = None) -> dict:
    return {
        "title": query[:60],
        "intro": f"Here is a step-by-step guide for: {query}",
        "sources": sources or [],
        "steps": [
            {
                "step_number": 1,
                "instruction": "Open the application and navigate to the main menu.",
                "detail": "",
                "screenshot_query": query,
                "annotations": [
                    {"type": "circle", "x": 90, "y": 112, "radius": 26,
                     "color": "#f59e0b", "label": "Start here"}
                ],
            }
        ],
    }
