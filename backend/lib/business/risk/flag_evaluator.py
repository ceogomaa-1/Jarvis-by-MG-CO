"""
Bible-aware flag evaluator. Calls Claude Sonnet 4.6 to determine which of the
user's industry Bible's risk flags are currently breached based on their
natural-language metrics blob.
"""
import json
import os

import httpx

from backend.lib.business.bible_loader import load_bible
from backend.lib.business.model_router import SONNET as EVALUATOR_MODEL

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EVALUATOR_TIMEOUT = 45.0

_EVALUATOR_SYSTEM = """\
You are a risk evaluation engine for Rue Business. Your job is to evaluate \
a business operator's current metrics against their industry's risk flags and \
return a structured assessment.

You will be given:
1. The risk flag definitions (red and yellow flags) from the user's industry Bible
2. The user's current metrics in their own words

For each flag definition, decide:
- Is it BREACHED based on the current metrics? (true/false)
- If yes, what is the dollar impact or business severity?

CRITICAL RULES:
- Only mark a flag breached if the metrics CLEARLY indicate it. If unclear, false.
- Severity: red flags breached take priority over yellow flags.
- Be conservative — better to under-report than fabricate alarms.
- Estimate dollar impact ONLY when the metrics give you enough information.

Return ONLY a valid JSON object. No markdown code fences. No commentary.

Shape:
{
  "breached_red": [
    {
      "flag": "...",
      "evidence": "...",
      "dollar_impact": "...",
      "urgency": "high" | "medium"
    }
  ],
  "breached_yellow": [
    {
      "flag": "...",
      "evidence": "...",
      "dollar_impact": "..."
    }
  ],
  "overall_severity": "red" | "yellow" | "green",
  "summary": "One sentence summary of the most pressing flag (or 'All clear' if green)"
}
"""


def _extract_risk_flags_section(industry: str) -> str:
    """Pull the RISK FLAGS section from the user's Bible. Returns empty string on miss."""
    bible = load_bible(industry)
    if not bible:
        return ""
    return bible.get("risk_flags", "")


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


async def evaluate_flags(industry: str, metrics_text: str) -> dict:
    """
    Evaluate user metrics against industry Bible risk flags.
    Returns the evaluator's structured assessment.
    """
    if not metrics_text or not metrics_text.strip():
        return {
            "breached_red": [],
            "breached_yellow": [],
            "overall_severity": "stale",
            "summary": "No metrics entered yet. Update your numbers to get a proper briefing.",
        }

    risk_section = _extract_risk_flags_section(industry)
    if not risk_section:
        return {
            "breached_red": [],
            "breached_yellow": [],
            "overall_severity": "none",
            "summary": "Industry-specific risk flags unavailable for this account.",
        }

    user_prompt = (
        f"INDUSTRY: {industry}\n\n"
        f"RISK FLAG DEFINITIONS FROM BIBLE:\n{risk_section}\n\n"
        f"USER'S CURRENT METRICS:\n{metrics_text}\n\n"
        f"Return the JSON assessment now."
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
                    "model": EVALUATOR_MODEL,
                    "max_tokens": 1500,
                    "system": _EVALUATOR_SYSTEM,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=EVALUATOR_TIMEOUT,
            )

        if resp.status_code != 200:
            print(f"FLAG_EVALUATOR: API {resp.status_code}: {resp.text[:200]}")
            return {
                "breached_red": [],
                "breached_yellow": [],
                "overall_severity": "none",
                "summary": "Could not evaluate flags this morning.",
            }

        raw = resp.json().get("content", [{}])[0].get("text", "")
        result = json.loads(_strip_code_fences(raw))

        result.setdefault("breached_red", [])
        result.setdefault("breached_yellow", [])
        if result.get("overall_severity") not in ("red", "yellow", "green", "none"):
            if result["breached_red"]:
                result["overall_severity"] = "red"
            elif result["breached_yellow"]:
                result["overall_severity"] = "yellow"
            else:
                result["overall_severity"] = "green"
        result.setdefault("summary", "")

        return result

    except json.JSONDecodeError as e:
        print(f"FLAG_EVALUATOR: JSON parse failed: {e}")
        return {
            "breached_red": [],
            "breached_yellow": [],
            "overall_severity": "none",
            "summary": "Flag evaluation parse failure — see logs.",
        }
    except Exception as e:
        print(f"FLAG_EVALUATOR: Exception: {e}")
        return {
            "breached_red": [],
            "breached_yellow": [],
            "overall_severity": "none",
            "summary": "Flag evaluation failed.",
        }
