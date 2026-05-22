import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_SYSTEM = (
    "You are a professional technical trainer. Generate detailed, accurate step-by-step "
    "walkthroughs for software tasks. Return ONLY valid JSON. No markdown code blocks. "
    "No explanation outside the JSON."
)


async def generate_walkthrough(query: str) -> dict:
    """
    Use Claude + web search to generate a structured walkthrough for the query.
    Returns a dict with title, intro, and steps list.
    """
    search_context = await _search_context(query)

    prompt = (
        f'The user wants to learn: "{query}"\n\n'
        f"Context from web search:\n{search_context}\n\n"
        f"Generate a complete step-by-step walkthrough. Return ONLY this JSON shape:\n"
        '{\n'
        '  "title": "Short descriptive title (max 60 chars)",\n'
        '  "intro": "2-3 sentence intro explaining what we\'re about to do",\n'
        '  "steps": [\n'
        '    {\n'
        '      "step_number": 1,\n'
        '      "instruction": "Clear specific instruction referencing exact UI elements",\n'
        '      "detail": "Optional tip or warning (can be empty string)",\n'
        '      "screenshot_query": "Specific image search query for this UI state",\n'
        '      "annotation": {\n'
        '        "type": "circle",\n'
        '        "position_x_pct": 50,\n'
        '        "position_y_pct": 30,\n'
        '        "color": "#f59e0b",\n'
        '        "label": "Click here"\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "Use 4-8 steps. annotation.type can be circle, arrow, or highlight. "
        "position_x_pct and position_y_pct are 0-100 percentages of where in "
        "the screenshot the annotation should appear. Return ONLY the JSON."
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
            return _fallback(query)

        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        # Strip any accidental markdown fences
        raw = raw.strip("```json").strip("```").strip()
        if raw.startswith("{"):
            return json.loads(raw)
        # Try to extract JSON object from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        print(f"WALKTHROUGH: No JSON found in response: {raw[:200]}")
        return _fallback(query)

    except json.JSONDecodeError as e:
        print(f"WALKTHROUGH: JSON parse error: {e}")
        return _fallback(query)
    except Exception as e:
        print(f"WALKTHROUGH: Error: {e}")
        return _fallback(query)


async def _search_context(query: str) -> str:
    try:
        from backend.tools.web_search import web_search
        result = await web_search(query=f"{query} tutorial steps how to")
        return (result or "")[:1500]
    except Exception as e:
        print(f"WALKTHROUGH: Search failed: {e}")
        return "No search context available."


def _fallback(query: str) -> dict:
    return {
        "title": query[:60],
        "intro": f"Here is a general walkthrough for: {query}",
        "steps": [
            {
                "step_number": 1,
                "instruction": "Open the application and navigate to the relevant section.",
                "detail": "",
                "screenshot_query": query,
                "annotation": {
                    "type": "circle",
                    "position_x_pct": 50,
                    "position_y_pct": 50,
                    "color": "#f59e0b",
                    "label": "Start here",
                },
            }
        ],
    }
