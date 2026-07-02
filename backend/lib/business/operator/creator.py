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
import re

import httpx

from backend.lib.anthropic_batch import AnthropicBatchError, AnthropicBatchTimeout, run_message_batch
from backend.lib.business.model_router import SONNET as MODEL

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TIMEOUT = 90.0


_CREATOR_SYSTEM = """\
You are a CREATOR sub-agent of Jarvis's Operator Agent, running overnight.

Your job: produce a SHIP-READY artifact for the move you've been assigned. \
The artifact lands in the owner's approval queue — when the owner taps \
APPROVE, Jarvis's Executor agent runs it FOR REAL through the wired \
connectors (sends the emails, schedules the posts, updates the CRM). Write \
the artifact so a machine can execute it without guessing.

Operating posture: Hormozi × Tate × Gary V — owner energy.

Rules:
- The artifact is markdown
- Lead with a 1-sentence "what this is" line
- Then the artifact itself — copy, plan, analysis, whatever the move requires
- EXECUTION-READY MEANS EXACT: real recipient names/emails from the live \
scan where provided (never invent addresses — if unknown, write \
[lookup: <person/company> in CRM] so the Executor resolves it), exact \
subject lines, exact post text per platform, exact CRM field changes
- Use vocabulary from the industry — never generic
- Include any numbers, sources, or specific assumptions inline
- End with a "What ships next" line — what happens when the owner approves
- NEVER end with "let me know if you have any questions"

Length guidance:
- Email/SMS drafts: 50-200 words
- Campaign bundles: 400-800 words
- Reports/analyses: 600-1200 words
- Landing page copy: full page, headlines + body
- Strategy docs: 500-800 words

Output ONLY the artifact markdown. No code fences. No preamble.
"""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def creator_batch_enabled(request_count: int) -> bool:
    """Whether Operator Creator should use Anthropic Message Batches for this fanout."""
    min_requests = max(1, _env_int("JARVIS_OPERATOR_CREATOR_BATCH_MIN", 2))
    return (
        bool(ANTHROPIC_API_KEY)
        and request_count >= min_requests
        and _env_bool("JARVIS_OPERATOR_CREATOR_BATCH", True)
    )


def creator_advisor_enabled() -> bool:
    """Advisor is opt-in: it can improve hard agentic work, but is not a blanket cost saver."""
    return _env_bool("JARVIS_OPERATOR_CREATOR_ADVISOR", False)


def _creator_prompt(
    move: dict,
    research_for_move: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
    scan_digest: str = "",
) -> str:
    prompt = (
        f"BUSINESS: {business_name}\n"
        f"INDUSTRY: {industry}\n"
        f"NORTH STAR: {north_star_label}\n\n"
        f"YOUR ASSIGNED MOVE:\n"
        f"  Title: {move.get('title','')}\n"
        f"  Rationale: {move.get('rationale','')}\n"
        f"  Expected impact: {move.get('expected_impact','')}\n"
        f"  Kind: {move.get('proposal_kind','artifact')}"
        f" (tools: {', '.join(move.get('execution_tools') or []) or 'none'})\n"
        f"  Preparation type: {move.get('preparation_type','')}\n"
        f"  Brief: {move.get('sub_agent_brief','')}\n\n"
    )
    if scan_digest:
        prompt += (
            f"LIVE BUSINESS SCAN (real data — pull names, emails, deals, and "
            f"numbers from here):\n{scan_digest[:3500]}\n\n"
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
    if creator_advisor_enabled():
        prompt += "\n\n(Advisor: please keep guidance under 80 words. Focus only on the highest-risk strategic miss.)"
    return prompt


def _message_params(prompt: str) -> dict:
    params: dict = {
        "model": MODEL,
        "max_tokens": 2500,
        "system": [
            {
                "type": "text",
                "text": _CREATOR_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": prompt}],
    }
    if creator_advisor_enabled():
        params["tools"] = [
            {
                "type": "advisor_20260301",
                "name": "advisor",
                "model": os.getenv("JARVIS_OPERATOR_CREATOR_ADVISOR_MODEL", "claude-opus-4-8"),
                "max_uses": max(1, _env_int("JARVIS_OPERATOR_CREATOR_ADVISOR_MAX_USES", 1)),
                "max_tokens": max(1024, _env_int("JARVIS_OPERATOR_CREATOR_ADVISOR_MAX_TOKENS", 2048)),
            }
        ]
    return params


def _advisor_beta_headers() -> list[str]:
    return ["advisor-tool-2026-03-01"] if creator_advisor_enabled() else []


def _message_headers() -> dict:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    betas = _advisor_beta_headers()
    if betas:
        headers["anthropic-beta"] = ",".join(betas)
    return headers


def _extract_message_text(message: dict) -> str:
    return "\n".join(
        block.get("text", "")
        for block in message.get("content", [])
        if block.get("type") == "text"
    ).strip()


def _custom_id(move: dict, index: int) -> str:
    raw = str(move.get("id") or f"move_{index + 1}")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).strip("_") or f"move_{index + 1}"
    return f"creator_{index + 1}_{safe}"[:64]


def _success_payload(move: dict, text: str, *, billing_mode: str, batch_id: str | None = None) -> dict:
    payload = {
        "move_id": move.get("id"),
        "ok": True,
        "artifact": text,
        "preparation_type": move.get("preparation_type", ""),
        "title": move.get("title", ""),
        "billing_mode": billing_mode,
    }
    if batch_id:
        payload["batch_id"] = batch_id
    return payload


async def _create_one(
    move: dict,
    research_for_move: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
    scan_digest: str = "",
) -> dict:
    """Run one sub-agent for one move."""
    prompt = _creator_prompt(
        move,
        research_for_move,
        industry,
        business_name,
        north_star_label,
        connector_summary,
        scan_digest=scan_digest,
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=_message_headers(),
                json=_message_params(prompt),
                timeout=TIMEOUT,
            )

        if resp.status_code != 200:
            return {
                "move_id": move.get("id"),
                "ok": False,
                "error": f"Creator API {resp.status_code}",
                "artifact": "",
            }

        text = _extract_message_text(resp.json())
        return _success_payload(move, text, billing_mode="sync")
    except Exception as e:
        return {
            "move_id": move.get("id"),
            "ok": False,
            "error": str(e),
            "artifact": "",
        }


async def _create_many_batch(
    moves: list[dict],
    research_map: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
    scan_digest: str = "",
) -> list[dict]:
    requests: list[dict] = []
    move_by_custom_id: dict[str, dict] = {}

    for idx, move in enumerate(moves):
        cid = _custom_id(move, idx)
        move_by_custom_id[cid] = move
        prompt = _creator_prompt(
            move=move,
            research_for_move=research_map.get(move["id"], {}),
            industry=industry,
            business_name=business_name,
            north_star_label=north_star_label,
            connector_summary=connector_summary,
            scan_digest=scan_digest,
        )
        requests.append({"custom_id": cid, "params": _message_params(prompt)})

    max_wait = max(60, _env_int("JARVIS_OPERATOR_CREATOR_BATCH_MAX_WAIT_SECONDS", 3600))
    batch, raw_results = await run_message_batch(
        requests,
        beta_headers=_advisor_beta_headers(),
        max_wait_seconds=max_wait,
        initial_poll_seconds=max(1, _env_int("JARVIS_OPERATOR_CREATOR_BATCH_POLL_SECONDS", 10)),
    )

    batch_id = batch.get("id")
    results_by_id = {r.get("custom_id"): r for r in raw_results}
    outputs: list[dict] = []
    for cid, move in move_by_custom_id.items():
        item = results_by_id.get(cid)
        if not item:
            outputs.append({
                "move_id": move.get("id"),
                "ok": False,
                "error": f"Creator batch {batch_id} returned no result for {cid}",
                "artifact": "",
                "billing_mode": "batch",
                "batch_id": batch_id,
            })
            continue

        result = item.get("result") or {}
        result_type = result.get("type")
        if result_type == "succeeded":
            text = _extract_message_text(result.get("message") or {})
            outputs.append(_success_payload(move, text, billing_mode="batch", batch_id=batch_id))
        else:
            error = result.get("error") or {}
            outputs.append({
                "move_id": move.get("id"),
                "ok": False,
                "error": f"Creator batch {result_type or 'unknown'}: {error}",
                "artifact": "",
                "billing_mode": "batch",
                "batch_id": batch_id,
            })
    return outputs


async def run_creator(
    strategist_plan: dict,
    researcher_output: dict,
    industry: str,
    business_name: str,
    north_star_label: str,
    connector_summary: str,
    max_parallel: int = 6,
    scan_digest: str = "",
) -> list[dict]:
    """
    Spawn one sub-agent per move (capped at max_parallel).
    Returns a list of creator outputs.
    """
    moves = (strategist_plan.get("moves") or [])[:max_parallel]
    if not moves:
        return []

    research_map = (researcher_output.get("research") or {})

    if creator_batch_enabled(len(moves)):
        try:
            print(f"OPERATOR CREATOR: using Anthropic Message Batch for {len(moves)} artifacts")
            return await _create_many_batch(
                moves=moves,
                research_map=research_map,
                industry=industry,
                business_name=business_name,
                north_star_label=north_star_label,
                connector_summary=connector_summary,
                scan_digest=scan_digest,
            )
        except AnthropicBatchTimeout as e:
            print(f"OPERATOR CREATOR: batch timed out without sync fallback: {e}")
            return [
                {
                    "move_id": m.get("id"),
                    "ok": False,
                    "error": str(e),
                    "artifact": "",
                    "billing_mode": "batch_timeout",
                }
                for m in moves
            ]
        except AnthropicBatchError as e:
            print(f"OPERATOR CREATOR: batch unavailable, falling back to sync fanout: {e}")

    tasks = [
        _create_one(
            move=m,
            research_for_move=research_map.get(m["id"], {}),
            industry=industry,
            business_name=business_name,
            north_star_label=north_star_label,
            connector_summary=connector_summary,
            scan_digest=scan_digest,
        )
        for m in moves
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)
