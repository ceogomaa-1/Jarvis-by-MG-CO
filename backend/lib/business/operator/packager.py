"""
Operator Cycle 4 — PACKAGER.

Batch 71 (Co-Founder Mode): cards are no longer read-only artifacts — each
card that can be executed carries an execution_plan (the exact steps + tools
the Executor agent fires when the owner taps Approve). The card is a
contract: "approve this, and here is precisely what Jarvis will do."

Reviews everything the prior cycles produced and writes the approval queue.
Runs on the smart-tier model because the packaging quality is what the user
sees in the morning — it earns the spend.
"""
import json
import os

import httpx

from backend.lib.business.model_router import OPUS

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TIMEOUT = 90.0


_PACKAGER_SYSTEM = """\
You are the PACKAGER cycle of Jarvis's Operator Agent. The prior cycles ran \
overnight and produced artifacts for a real business owner who enabled \
Co-Founder Mode. Your job: package each artifact as a card in the owner's \
approval queue.

THE CONTRACT: when the owner taps APPROVE on a card, Jarvis's Executor agent \
runs the card's execution_plan for real — sends the emails, schedules the \
posts, writes to the CRM. So the plan must be honest, specific, and only use \
tools that are actually wired (see connector list in the user message).

For each creator artifact, decide:
- action_type: one of "email_draft", "sms_draft", "landing_page", \
"campaign_bundle", "report", "analysis", "research_brief", "strategy_doc", \
"outreach_sequence", "crm_update", "social_posts"
- internal_or_external:
    - "external" = executing would touch the outside world (send email/SMS, \
publish, post, schedule)
    - "internal" = preparation or internal records only (analysis, strategy \
doc, CRM hygiene)
- priority: 1-100, LOWER = more urgent
- expected_impact: one concrete line — what changes if this executes
- title: short, action-oriented ("Send revival emails to 4 stale deals")
- description: 1 sentence — what this card does
- execution_plan:
    - mode: "auto" if Jarvis can execute this itself with the wired tools \
when approved; "manual" if the owner must act by hand (missing connector, or \
pure reading material)
    - steps: 2-6 short imperative strings — EXACTLY what the Executor will \
do, in order, with real targets from the artifact ("Send the drafted email \
to sarah@acme.co", "Schedule 3 LinkedIn posts for Tue/Thu/Sat 9am")
    - tools: the tool names the Executor will call (e.g. \
["google__send_email"]). Empty array when mode is "manual".

Return ONLY JSON:
{
  "morning_message": "One paragraph the owner reads first — what got done, what's queued, what's most urgent. Owner energy, no fluff.",
  "cards": [
    {
      "move_id": "m1",
      "action_type": "...",
      "internal_or_external": "external",
      "title": "...",
      "description": "...",
      "expected_impact": "...",
      "priority": 25,
      "connector_type": "google",
      "execution_plan": {"mode": "auto", "steps": ["..."], "tools": ["google__send_email"]},
      "artifact_markdown": "(pass through the creator's artifact verbatim)"
    }
  ]
}

Never mark mode "auto" with a tool that is not in the wired connector list. \
No markdown. No code fences.
"""


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


async def run_packager(
    strategist_plan: dict,
    creator_outputs: list[dict],
    business_name: str,
    north_star_label: str,
    connector_summary: str = "",
) -> dict:
    """Package the creator outputs into approval cards with execution plans."""
    if not creator_outputs:
        return {"morning_message": "Operator ran but produced no artifacts.", "cards": []}

    moves_by_id = {m.get("id"): m for m in strategist_plan.get("moves", [])}

    summary_for_llm = []
    for c in creator_outputs:
        if not c.get("ok"):
            continue
        move = moves_by_id.get(c.get("move_id"), {})
        summary_for_llm.append({
            "move_id": c.get("move_id"),
            "title": c.get("title"),
            "preparation_type": c.get("preparation_type"),
            "proposal_kind": move.get("proposal_kind", "artifact"),
            "planned_execution_tools": move.get("execution_tools", []),
            "expected_impact": move.get("expected_impact", ""),
            "artifact_excerpt": (c.get("artifact") or "")[:700],
            "artifact_length": len(c.get("artifact") or ""),
        })

    prompt = (
        f"BUSINESS: {business_name}\n"
        f"NORTH STAR: {north_star_label}\n"
        f"WEEKLY THESIS: {strategist_plan.get('weekly_thesis','')}\n\n"
        f"WIRED CONNECTORS (only these are executable):\n{connector_summary or '(none)'}\n\n"
        f"CREATOR ARTIFACTS (excerpts):\n{json.dumps(summary_for_llm, indent=2)}\n\n"
        f"Package each artifact as an approval card with an honest execution_plan. Return JSON now."
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
                    "max_tokens": 4000,
                    "system": _PACKAGER_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=TIMEOUT,
            )

        if resp.status_code != 200:
            return {"error": f"Packager API {resp.status_code}", "cards": [], "morning_message": ""}

        text = resp.json().get("content", [{}])[0].get("text", "")
        parsed = json.loads(_strip_fences(text))

        # Re-attach the FULL artifact_markdown (packager only saw excerpts)
        artifact_by_move = {c["move_id"]: c.get("artifact", "") for c in creator_outputs if c.get("ok")}
        for card in parsed.get("cards", []):
            mid = card.get("move_id")
            if mid and (not card.get("artifact_markdown") or len(card.get("artifact_markdown", "")) < 200):
                card["artifact_markdown"] = artifact_by_move.get(mid, card.get("artifact_markdown", ""))
            card.setdefault("action_type", "report")
            card.setdefault("internal_or_external", "internal")
            card.setdefault("priority", 50)
            card.setdefault("connector_type", "")
            card.setdefault("title", "Untitled action")
            card.setdefault("description", "")
            card.setdefault("expected_impact", "")
            plan = card.get("execution_plan") or {}
            plan.setdefault("mode", "manual")
            plan.setdefault("steps", [])
            plan.setdefault("tools", [])
            # An "auto" plan with no steps or no tools is not a real plan — demote it.
            if plan["mode"] == "auto" and (not plan["steps"] or not plan["tools"]):
                plan["mode"] = "manual"
            card["execution_plan"] = plan

        parsed.setdefault("morning_message", "")
        parsed.setdefault("cards", [])
        return parsed

    except json.JSONDecodeError as e:
        return {"error": f"Packager JSON: {e}", "cards": [], "morning_message": ""}
    except Exception as e:
        return {"error": f"Packager exception: {e}", "cards": [], "morning_message": ""}
