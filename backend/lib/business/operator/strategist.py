"""
Operator Cycle 1 — STRATEGIST.

Calls Claude Opus 4.7 to pick the 3-6 highest-leverage moves that close
the gap to the user's North Star this week. Returns a structured plan.

The plan drives all subsequent cycles.
"""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-7"
TIMEOUT = 60.0


_STRATEGIST_SYSTEM = """\
You are the STRATEGIST cycle of Jarvis's Operator Agent. You run autonomously \
overnight on behalf of a real business owner.

Your job: pick the 3 to 6 HIGHEST-LEVERAGE moves the business should make \
THIS WEEK to close the gap to their North Star target.

Operating posture: Hormozi × Tate × Gary V — owner energy, not advisor energy. \
You operate as if you own the company.

Rules:
- Each move must be CONCRETE — a specific action, not "improve marketing"
- Each move must be PREPARABLE OVERNIGHT — you spawn sub-agents in a later cycle to draft, design, analyze
- NO move that requires the owner to physically do something today (e.g. "hire a new GM")
- NO move that requires the owner's real-time approval to start (those are next-cycle problems)
- Prioritize moves that compound — content, systems, sequences, assets — over one-shots
- If the business is in crisis (red flags), 1-2 moves MUST be triage

Return ONLY a JSON object in this exact shape:
{
  "weekly_thesis": "One sentence — what story this week tells.",
  "moves": [
    {
      "id": "m1",
      "title": "Short imperative title",
      "rationale": "1-2 sentences — why this move, why now, what it compounds",
      "leverage_score": 95,
      "preparation_type": "campaign" | "content" | "analysis" | "system" | "research" | "outreach",
      "sub_agent_brief": "One paragraph that the Creator cycle will hand to a sub-agent — concrete enough that the sub-agent produces a ship-ready artifact"
    }
  ]
}

leverage_score is 0-100 — your honest read on impact-per-effort. Sort moves \
descending by leverage_score. Cap at 6 moves total.

No markdown. No code fences. JSON only.
"""


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


async def run_strategist(
    user_context: dict,
    industry_briefing: str,
    latest_metrics: str,
    latest_flags_summary: str,
) -> dict:
    """
    Run the Strategist cycle. Returns the parsed plan or an error dict.

    user_context: {display_name, industry, north_star_label, north_star_usd}
    industry_briefing: Bible relevant section (kept empty for v1 — operator is self-contained)
    latest_metrics: user's metrics blob from business_user_metrics
    latest_flags_summary: latest risk flag summary
    """
    prompt = (
        f"BUSINESS: {user_context.get('display_name','their business')}\n"
        f"INDUSTRY: {user_context.get('industry','general')}\n"
        f"NORTH STAR: {user_context.get('north_star_label','$1M ARR')} "
        f"({user_context.get('north_star_usd', 1_000_000)})\n\n"
        f"LATEST METRICS (from owner):\n{latest_metrics or '(no metrics yet)'}\n\n"
        f"LATEST RISK FLAGS:\n{latest_flags_summary or '(no flags)'}\n\n"
        f"INDUSTRY-SPECIFIC OPERATING WISDOM:\n{industry_briefing or '(none)'}\n\n"
        f"Pick the moves for this week now."
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
                    "max_tokens": 2048,
                    "system": _STRATEGIST_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=TIMEOUT,
            )

        if resp.status_code != 200:
            return {"error": f"Strategist API {resp.status_code}: {resp.text[:200]}"}

        raw = resp.json().get("content", [{}])[0].get("text", "")
        plan = json.loads(_strip_fences(raw))

        plan.setdefault("weekly_thesis", "")
        plan.setdefault("moves", [])
        plan["moves"] = sorted(
            plan["moves"], key=lambda m: m.get("leverage_score", 0), reverse=True
        )[:6]
        for i, m in enumerate(plan["moves"]):
            m.setdefault("id", f"m{i+1}")

        return plan

    except json.JSONDecodeError as e:
        return {"error": f"Strategist JSON parse failed: {e}"}
    except Exception as e:
        return {"error": f"Strategist exception: {e}"}
