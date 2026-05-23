import os
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Always loaded regardless of query
_ALWAYS_INCLUDE = ["identity", "first_conversation"]

# Keyword triggers → section keys
SECTION_INTENTS: dict[str, list[str]] = {
    "operations": [
        "how does", "how do i", "how to run", "day to day", "day-to-day",
        "workflow", "process", "operate", "operation", "structure",
        "set up", "setup", "systems", "system",
    ],
    "problems": [
        "problem", "issue", "stuck", "failing", "losing", "broken",
        "wrong", "fix", "struggling", "challenge", "hurting", "hurt",
        "kill", "killing", "dying", "broke", "can't", "cannot",
        "no-show", "no show", "cancellation", "churn", "turnover",
        "attrition", "not working", "underperform", "slow", "down",
        "complaint", "negative review", "losing clients", "losing customers",
    ],
    "metrics": [
        "number", "metric", "kpi", "track", "measure", "rate",
        "percentage", "ratio", "margin", "average", "benchmark",
        "cost", "revenue", "profit", "loss", "overhead", "cash flow",
        "cashflow", "collection", "production",
    ],
    "risk_flags": [
        "risk", "warning", "alert", "danger", "red flag", "concern",
        "worry", "watch out", "careful", "losing money", "going under",
    ],
    "mindset": [
        "should i", "what would you do", "strategy", "advice",
        "approach", "philosophy", "mindset", "think about", "decide",
        "decision", "worth it", "make sense", "good idea", "bad idea",
        "recommend", "suggest", "open", "launch", "start", "scale",
        "grow", "growth", "expand",
    ],
    "daily_ops": [
        "today", "this week", "this month", "schedule", "routine",
        "habit", "morning", "daily", "weekly", "checklist", "huddle",
        "meeting", "report", "briefing",
    ],
    "moves": [
        "edge", "unfair advantage", "competitive", "differentiate",
        "stand out", "ahead", "secret", "nobody talks about",
        "hack", "trick", "shortcut", "lever", "opportunity",
    ],
}


def classify_intent(user_message: str) -> list[str]:
    """
    Returns the list of section keys to load for this query.
    Always includes 'identity' and 'first_conversation'.
    Uses keyword matching first; falls back to Claude Haiku if weak.
    """
    msg_lower = user_message.lower()

    matched: set[str] = set()
    for section_key, keywords in SECTION_INTENTS.items():
        for kw in keywords:
            if kw in msg_lower:
                matched.add(section_key)
                break

    # If 2+ sections matched via keywords, trust it
    if len(matched) >= 2:
        return _always_plus(matched)

    # Weak match — ask Claude Haiku for a better classification
    haiku_sections = _classify_with_haiku(user_message)
    if haiku_sections:
        matched.update(haiku_sections)

    # Fallback: if still nothing, load mindset + operations as safe defaults
    if not matched:
        matched = {"mindset", "operations"}

    return _always_plus(matched)


def _always_plus(matched: set[str]) -> list[str]:
    result = list(_ALWAYS_INCLUDE)
    for key in matched:
        if key not in result:
            result.append(key)
    return result


def _classify_with_haiku(user_message: str) -> list[str]:
    """Call Claude Haiku synchronously for intent classification fallback."""
    if not ANTHROPIC_API_KEY:
        return []

    prompt = (
        "Classify this business owner question into 1-3 categories that would help answer it.\n"
        "Categories: operations, problems, metrics, risk_flags, mindset, daily_ops, moves\n\n"
        f'Question: "{user_message}"\n\n'
        "Return only the category names, comma-separated. Example: metrics, problems"
    )

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 40,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=8.0,
        )
        if resp.status_code == 200:
            text = resp.json().get("content", [{}])[0].get("text", "").strip().lower()
            valid = set(SECTION_INTENTS.keys())
            return [s.strip() for s in text.split(",") if s.strip() in valid]
    except Exception:
        pass
    return []
