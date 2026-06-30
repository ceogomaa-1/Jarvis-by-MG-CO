"""
Operator Cycle 2 — RESEARCHER.

Calls Claude Sonnet 4.6 with web_search enabled to back each strategist move
with real-world research, competitor data, and current market context.

Output is fed into Creator cycle so sub-agents have current data.
"""
import json
import os

import httpx

from backend.lib.business.model_router import SONNET as MODEL

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TIMEOUT = 90.0


_RESEARCHER_SYSTEM = """\
You are the RESEARCHER cycle of Jarvis's Operator Agent. The Strategist has \
identified moves for this week. Your job: enrich each move with current \
real-world data using web_search.

For each move, find:
- 2-3 specific data points or facts that strengthen the move (with sources)
- 1 competitive insight relevant to the industry
- 1 risk or counter-argument the Creator should account for

Be specific. "Industry growing" is useless. "Q3 2025 IBISWorld data shows \
local salon revenue up 4.1% YoY" is useful.

Return ONLY a JSON object:
{
  "research": {
    "m1": {
      "facts": ["...", "..."],
      "competitive_insight": "...",
      "counter_argument": "...",
      "sources": ["https://...", "..."]
    },
    "m2": { ... }
  }
}

If a move doesn't need external research (e.g. internal process), return an \
empty facts array and a note in counter_argument explaining why.

No markdown. No code fences. JSON only.
"""


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


async def run_researcher(strategist_plan: dict, industry: str) -> dict:
    """Enrich the strategist plan with current research."""
    if not strategist_plan.get("moves"):
        return {"research": {}}

    moves_summary = "\n".join(
        f"- {m['id']}: {m['title']} — {m.get('rationale','')}"
        for m in strategist_plan["moves"]
    )

    prompt = (
        f"INDUSTRY: {industry}\n\n"
        f"STRATEGIST MOVES TO RESEARCH:\n{moves_summary}\n\n"
        f"Use web_search to enrich each move with current data. Return JSON now."
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
                    "model": MODEL,
                    "max_tokens": 3000,
                    "system": _RESEARCHER_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                },
                timeout=TIMEOUT,
            )

        if resp.status_code != 200:
            return {"error": f"Researcher API {resp.status_code}: {resp.text[:200]}", "research": {}}

        content_blocks = resp.json().get("content", [])
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        full_text = "\n".join(text_parts).strip()

        if not full_text:
            return {"research": {}, "warning": "No text content from researcher"}

        parsed = json.loads(_strip_fences(full_text))
        parsed.setdefault("research", {})
        return parsed

    except json.JSONDecodeError as e:
        return {"error": f"Researcher JSON parse: {e}", "research": {}}
    except Exception as e:
        return {"error": f"Researcher exception: {e}", "research": {}}
