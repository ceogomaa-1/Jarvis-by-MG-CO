"""
Morning briefing generator. Takes the flag evaluator's output + user context
and crafts the human-facing briefing message using Claude Opus 4.7.
"""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRIEFING_MODEL = "claude-opus-4-7"
BRIEFING_TIMEOUT = 45.0

_BRIEFING_SYSTEM = """\
You are Jarvis, the all-in-one business operator. You are crafting a morning briefing for a business owner.

You are NOT a generic AI assistant. You are their CFO + COO + strategic operator who has been watching their numbers overnight.

Tone: premium, confident, direct. No "Good morning!" filler. No "I hope this finds you well." \
Start with the most important thing immediately. Use the operator's industry vocabulary.

You will receive:
- The user's name and company
- The flag evaluator's assessment (which flags breached, severities, summaries)

Output a single JSON object with two fields:
{
  "briefing_text": "...",     // The user-facing message — Markdown allowed
  "suggested_action": "..."   // A SINGLE concrete instruction to feed into Creation 1.0 if the user clicks the action button
}

BRIEFING RULES:
- If severity is RED: lead with the flag, dollar impact, and one ranked action. 2-3 sentences MAX.
- If severity is YELLOW: lead with the warning, what to watch, one suggested move. 2-3 sentences MAX.
- If severity is GREEN: brief acknowledgment, one observation, no scary tone. 2 sentences MAX.
- If severity is STALE (no metrics): nudge the user to update their numbers. 1-2 sentences.
- NEVER refer to yourself in third person. You ARE Jarvis.
- NEVER end with "Let me know if you have any questions!" — end with the next concrete move.

SUGGESTED_ACTION RULES:
- It will be sent as a Creation 1.0 request. Phrase it as an imperative starting with a CREATE verb.
- Good: "Build me a 3-tier collection sequence to chase the $84K over 90 days."
- Good: "Generate a markdown ladder for the aged inventory."
- Bad: "How should I handle this?" (not a creation request)
- If severity is green or stale, set suggested_action to "" (empty string).

Return ONLY the JSON object. No code fences. No commentary.
"""


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


def _fallback_briefing(evaluator_output: dict) -> dict:
    """Surface the evaluator summary directly when the Opus call fails."""
    summary = evaluator_output.get("summary", "No briefing available this morning.")
    severity = evaluator_output.get("overall_severity", "none")
    emoji = {"red": "🔴", "yellow": "🟡", "green": "🟢", "stale": "📊"}.get(severity, "")
    return {"briefing_text": f"{emoji} {summary}".strip(), "suggested_action": ""}


async def generate_briefing(
    user_first_name: str,
    company_name: str,
    industry: str,
    evaluator_output: dict,
) -> dict:
    """
    Generate the user-facing morning briefing using Opus 4.7.
    Returns {"briefing_text": str, "suggested_action": str}.
    """
    user_prompt = (
        f"USER FIRST NAME: {user_first_name or 'there'}\n"
        f"COMPANY: {company_name or 'their business'}\n"
        f"INDUSTRY: {industry or 'general'}\n\n"
        f"EVALUATOR ASSESSMENT (JSON):\n{json.dumps(evaluator_output, indent=2)}\n\n"
        f"Craft the briefing now."
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
                    "model": BRIEFING_MODEL,
                    "max_tokens": 800,
                    "system": _BRIEFING_SYSTEM,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=BRIEFING_TIMEOUT,
            )

        if resp.status_code != 200:
            print(f"BRIEFING_GENERATOR: API {resp.status_code}: {resp.text[:200]}")
            return _fallback_briefing(evaluator_output)

        raw = resp.json().get("content", [{}])[0].get("text", "")
        result = json.loads(_strip_code_fences(raw))
        result.setdefault("briefing_text", "")
        result.setdefault("suggested_action", "")
        return result

    except json.JSONDecodeError as e:
        print(f"BRIEFING_GENERATOR: JSON parse failed: {e}")
        return _fallback_briefing(evaluator_output)
    except Exception as e:
        print(f"BRIEFING_GENERATOR: Exception: {e}")
        return _fallback_briefing(evaluator_output)
