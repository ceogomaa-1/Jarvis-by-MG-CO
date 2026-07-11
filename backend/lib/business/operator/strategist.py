"""
Operator Cycle 1 — STRATEGIST.

Batch 71 (Co-Founder Mode): the strategist now reads a LIVE business scan —
real CRM pipeline, real inbox, real lead queue, real revenue — plus the
owner's past approve/decline decisions, and is required to propose moves
that Rue can EXECUTE through wired connectors, not just describe.

Calls the smart-tier model to pick the 3-6 highest-leverage moves that close
the gap to the user's North Star this week. Returns a structured plan that
drives all subsequent cycles.
"""
import json
import os

import httpx

from backend.lib.business.model_router import OPUS

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TIMEOUT = 90.0


_STRATEGIST_SYSTEM = """\
You are the STRATEGIST cycle of Rue's Operator Agent — the co-founder of \
this business, running autonomously on behalf of a real owner who flipped \
the Co-Founder switch. You have just walked through the live state of the \
business (the scan below is REAL data pulled minutes ago, not hypotheticals).

Your job: pick the 3 to 6 HIGHEST-LEVERAGE moves the business should make \
THIS WEEK to close the gap to the North Star.

Operating posture: Hormozi × Tate × Gary V — owner energy, not advisor \
energy. You operate as if you own the company. Think outside the whole room, \
not just the box: propose the move the owner hasn't thought of, not the one \
every generic AI would suggest.

Rules:
- GROUND every move in the live scan. Reference the actual numbers, actual \
stale deals, actual unanswered emails, actual A-grade leads by name. A move \
that ignores the scan is a wasted move.
- Each move must be CONCRETE — a specific action with specific targets, not \
"improve marketing"
- STRONGLY prefer moves Rue can EXECUTE itself through the wired \
connectors listed below (send the emails, schedule the posts, update the \
CRM, push the leads). These are proposal_kind "action". Moves that only \
produce a document for the owner to read are proposal_kind "artifact" — \
allowed, but they should be the minority.
- NO move that requires the owner to physically do something today
- Respect the owner's decision history: double down on what they approve, \
stop proposing what they decline
- Prioritize moves that compound — pipeline revival, sequences, systems, \
content engines — over one-shots
- If the business is in crisis (red flags), 1-2 moves MUST be triage

THE DETECTIVE RULE: you are also the sharpest detective this business has. \
Interrogate the scan for what's MISSING — the facts that, if you had them, \
would let you propose 10x better moves or expose a flaw the owner can't see. \
Ask 0-3 questions, and ONLY when the answer materially changes what you'd do:
- Ask about things only the OWNER can know (margins, capacity, best clients, \
what actually closed last month, pricing pain, churn reasons, team bandwidth)
- NEVER ask what the scan already answers, what's on the answers record, or \
what's listed as already-asked
- NEVER ask lazy intake questions ("what's your target audience?") — ask \
like a detective who already studied the file ("Your 4 stale deals are all \
in PROPOSAL stage — what's the real objection you're hearing on price?")
- Still produce your best moves with what you have. Questions sharpen next \
cycle; they are never an excuse for weak moves now.

Return ONLY a JSON object in this exact shape:
{
  "weekly_thesis": "One sentence — what story this week tells.",
  "moves": [
    {
      "id": "m1",
      "title": "Short imperative title",
      "rationale": "1-2 sentences — why this move, why now, grounded in the scan",
      "expected_impact": "One concrete line — what changes if this ships (use numbers from the scan where possible)",
      "leverage_score": 95,
      "proposal_kind": "action" | "artifact",
      "preparation_type": "campaign" | "content" | "analysis" | "system" | "research" | "outreach",
      "execution_tools": ["google__send_email"],
      "sub_agent_brief": "One paragraph the Creator cycle hands to a sub-agent — concrete enough that the sub-agent produces a ship-ready, executable artifact with exact recipients/targets where the scan provides them"
    }
  ],
  "questions": [
    {
      "question": "The detective question — specific, references the scan",
      "why_it_matters": "One line — the flaw or blind spot this exposes",
      "unlocks": "One line — what Rue does differently once answered"
    }
  ]
}

execution_tools: the tool names the Executor would fire for this move — ONLY \
tools available per the connector list below. Empty array for "artifact" moves.

leverage_score is 0-100 — your honest read on impact-per-effort. Sort moves \
descending by leverage_score. Cap at 6 moves total. "questions" may be [].

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
    business_scan_digest: str = "",
    connector_summary: str = "",
) -> dict:
    """
    Run the Strategist cycle. Returns the parsed plan or an error dict.

    user_context: {display_name, industry, north_star_label, north_star_usd}
    industry_briefing: Bible relevant section (kept empty for v1 — operator is self-contained)
    latest_metrics: user's metrics blob from business_user_metrics
    latest_flags_summary: latest risk flag summary
    business_scan_digest: the Analyst cycle's live scan of CRM/leads/inbox/revenue/social
    connector_summary: which connectors are wired and what actions they expose
    """
    prompt = (
        f"BUSINESS: {user_context.get('display_name','their business')}\n"
        f"INDUSTRY: {user_context.get('industry','general')}\n"
        f"NORTH STAR: {user_context.get('north_star_label','$1M ARR')} "
        f"({user_context.get('north_star_usd', 1_000_000)})\n\n"
        f"LIVE BUSINESS SCAN (pulled minutes ago — this is real):\n"
        f"{business_scan_digest or '(scan unavailable — fall back to metrics below)'}\n\n"
        f"WIRED CONNECTORS (what Rue can execute):\n"
        f"{connector_summary or '(none listed)'}\n\n"
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
                    "model": OPUS,
                    "max_tokens": 3000,
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
            m.setdefault("proposal_kind", "artifact")
            m.setdefault("execution_tools", [])
            m.setdefault("expected_impact", "")

        # Detective questions: 0-3, each must actually be a question.
        questions = plan.get("questions") or []
        plan["questions"] = [
            q for q in questions
            if isinstance(q, dict) and (q.get("question") or "").strip()
        ][:3]

        return plan

    except json.JSONDecodeError as e:
        return {"error": f"Strategist JSON parse failed: {e}"}
    except Exception as e:
        return {"error": f"Strategist exception: {e}"}
