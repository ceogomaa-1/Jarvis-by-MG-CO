"""
Operator Cycle 3 — CREATOR.

For each strategist move, spawn a Sonnet 4.6 sub-agent that produces a
ship-ready artifact. Sub-agents run in parallel via asyncio.gather.

The artifacts are then handed to the Packager (Cycle 4) which writes them
into business_pending_actions as morning approval cards.
"""
import asyncio
import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
TIMEOUT = 90.0


_CREATOR_SYSTEM = """\
You are a CREATOR sub-agent of Jarvis's Operator Agent, running overnight.

Your job: produce a SHIP-READY artifact for the move you've been assigned. \
The artifact lands in the owner's morning approval queue — they should be \
able to read it and click Ship without rewriting it.

Operating posture: Hormozi × Tate × Gary V — owner energy.

Rules:
- The artifact is markdown
- Lead with a 1-sentence "what this is" line
- Then the artifact itself — copy, plan, analysis, whatever the move requires
- Use vocabulary from the industry — never generic
- Include any numbers, sources, or specific assumptions inline
- End with a "What ships next" line — what the owner clicks to deploy this
- NEVER end with "let me know if you have any questions"

Length guidance:
- Email/SMS drafts: 50-200 words
- Campaign bundles: 400-800 words
- Reports/analyses: 600-1200 words
- Landing page copy: full page, headlines + body
- Strategy docs: 500-800 words

Output ONLY the artifact markdown. No code fences. No preamble.
"""


async def _create_one(
    move: dict,
    research_for_move: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
) -> dict:
    """Run one sub-agent for one move."""
    prompt = (
        f"BUSINESS: {business_name}\n"
        f"INDUSTRY: {industry}\n"
        f"NORTH STAR: {north_star_label}\n\n"
        f"YOUR ASSIGNED MOVE:\n"
        f"  Title: {move.get('title','')}\n"
        f"  Rationale: {move.get('rationale','')}\n"
        f"  Preparation type: {move.get('preparation_type','')}\n"
        f"  Brief: {move.get('sub_agent_brief','')}\n\n"
    )
    if research_for_move:
        prompt += (
            f"CURRENT RESEARCH (use sparingly, cite if relevant):\n"
            f"{json.dumps(research_for_move, indent=2)}\n\n"
        )
    prompt += (
        f"CONNECTOR STATUS: {connector_summary}\n"
        f"(If the owner has a connector wired, mention how the artifact ships through it. "
        f"If not, deliver the artifact as a draft for manual use.)\n\n"
        f"Produce the artifact now."
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
                    "max_tokens": 2500,
                    "system": _CREATOR_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=TIMEOUT,
            )

        if resp.status_code != 200:
            return {
                "move_id": move.get("id"),
                "ok": False,
                "error": f"Creator API {resp.status_code}",
                "artifact": "",
            }

        text = resp.json().get("content", [{}])[0].get("text", "")
        return {
            "move_id": move.get("id"),
            "ok": True,
            "artifact": text,
            "preparation_type": move.get("preparation_type", ""),
            "title": move.get("title", ""),
        }
    except Exception as e:
        return {
            "move_id": move.get("id"),
            "ok": False,
            "error": str(e),
            "artifact": "",
        }


async def run_creator(
    strategist_plan: dict,
    researcher_output: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
    max_parallel: int = 6,
) -> list[dict]:
    """
    Spawn one sub-agent per move (capped at max_parallel).
    Returns a list of creator outputs.
    """
    moves = (strategist_plan.get("moves") or [])[:max_parallel]
    if not moves:
        return []

    research_map = (researcher_output.get("research") or {})

    tasks = [
        _create_one(
            move=m,
            research_for_move=research_map.get(m["id"], {}),
            industry=industry,
            business_name=business_name,
            north_star_label=north_star_label,
            connector_summary=connector_summary,
        )
        for m in moves
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)
