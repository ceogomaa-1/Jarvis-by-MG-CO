"""
Operator Cycle 4 — PACKAGER.

Reviews everything the prior cycles produced and writes the morning approval
queue. Each artifact gets classified as internal or external, priority-scored,
and tagged with the relevant connector if any.

This is the LAST cycle, run on Opus 4.7 because the packaging quality is what
the user sees in the morning — it earns the spend.
"""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-7"
TIMEOUT = 60.0


_PACKAGER_SYSTEM = """\
You are the PACKAGER cycle of Jarvis's Operator Agent. The prior cycles ran \
overnight and produced artifacts. Your job: package each artifact as a card \
in the owner's morning approval queue.

For each creator artifact, decide:
- action_type: one of "email_draft", "sms_draft", "landing_page", \
"campaign_bundle", "report", "analysis", "research_brief", "strategy_doc"
- internal_or_external:
    - "external" = action would touch the outside world if shipped \
(send email, send SMS, publish page, post ad)
    - "internal" = preparation only (analysis, strategy doc, research brief, internal report)
- priority: 1-100, LOWER = more urgent
- connector_type: if external, which connector fires it ("smtp", "twilio", or "" if none wired)
- title: short, action-oriented ("Ship the Mother's Day SMS to 200 inactive customers")
- description: 1 sentence — what this card does

Return ONLY JSON:
{
  "morning_message": "One paragraph the owner reads first — what got done overnight, what's queued, what's most urgent",
  "cards": [
    {
      "move_id": "m1",
      "action_type": "...",
      "internal_or_external": "external",
      "title": "...",
      "description": "...",
      "priority": 25,
      "connector_type": "smtp",
      "artifact_markdown": "(pass through the creator's artifact verbatim)"
    }
  ]
}

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
) -> dict:
    """Package the creator outputs into morning approval cards."""
    if not creator_outputs:
        return {"morning_message": "Operator ran but produced no artifacts.", "cards": []}

    summary_for_llm = []
    for c in creator_outputs:
        if not c.get("ok"):
            continue
        summary_for_llm.append({
            "move_id": c.get("move_id"),
            "title": c.get("title"),
            "preparation_type": c.get("preparation_type"),
            "artifact_excerpt": (c.get("artifact") or "")[:500],
            "artifact_length": len(c.get("artifact") or ""),
        })

    prompt = (
        f"BUSINESS: {business_name}\n"
        f"NORTH STAR: {north_star_label}\n"
        f"WEEKLY THESIS: {strategist_plan.get('weekly_thesis','')}\n\n"
        f"CREATOR ARTIFACTS (excerpts):\n{json.dumps(summary_for_llm, indent=2)}\n\n"
        f"Package each artifact as a morning approval card. Return JSON now."
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

        parsed.setdefault("morning_message", "")
        parsed.setdefault("cards", [])
        return parsed

    except json.JSONDecodeError as e:
        return {"error": f"Packager JSON: {e}", "cards": [], "morning_message": ""}
    except Exception as e:
        return {"error": f"Packager exception: {e}", "cards": [], "morning_message": ""}
