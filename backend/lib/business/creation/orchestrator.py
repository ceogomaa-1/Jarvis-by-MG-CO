import asyncio
import json
import os
from typing import AsyncIterator

import httpx

from backend.lib.business.creation.sub_agents import run_sub_agent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ORCHESTRATOR_MODEL = "claude-opus-4-7"
ORCHESTRATOR_TIMEOUT = 60.0

_ORCHESTRATOR_SYSTEM = """\
You are the ORCHESTRATOR of Jarvis Business Creation 1.0. Your job is to decompose a creation request into a small team of specialized sub-agents.

Available sub-agent roles:
- strategist: high-level decisions (target audience, offer, channel mix, timeline)
- copywriter: ready-to-ship email / SMS / ad / landing page copy
- designer: HTML, SVG, or JSX components (landing pages, email templates, signage)
- researcher: factual research brief (competitors, market, customer)
- analyst: numbers, tables, ROI math
- reporter: ALWAYS the final sub-agent — aggregates everything into a unified artifact

Rules:
- Use 2-5 sub-agents BEFORE the reporter. Total 3-6 including reporter.
- Reporter is ALWAYS the last sub-agent.
- Each sub-agent (other than reporter) should run on independent inputs so they can run in parallel.
- Be precise in each sub-agent's `task` — one sentence telling them exactly what to produce.

Return ONLY a valid JSON object in this exact shape:
{
  "title": "Short title of the creation (e.g. 'Mother's Day Campaign')",
  "intro": "One sentence Jarvis tells the user about what is being spun up.",
  "sub_agents": [
    {"role": "strategist", "task": "..."},
    {"role": "copywriter", "task": "..."},
    {"role": "designer", "task": "..."},
    {"role": "reporter", "task": "Aggregate all prior outputs into the final deliverable."}
  ]
}

No markdown code fences. No commentary. JSON only.
"""


async def _plan_creation(user_message: str, context: dict) -> dict:
    """Call Opus 4.7 to decompose the request into a sub-agent plan."""
    user_prompt = f"Creation request: {user_message}"
    if context.get("industry"):
        user_prompt += f"\nIndustry: {context['industry']}"
    if context.get("company_name"):
        user_prompt += f"\nCompany: {context['company_name']}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ORCHESTRATOR_MODEL,
                "max_tokens": 1024,
                "system": _ORCHESTRATOR_SYSTEM,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=ORCHESTRATOR_TIMEOUT,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Orchestrator API {resp.status_code}: {resp.text[:300]}")

    raw = resp.json().get("content", [{}])[0].get("text", "").strip()
    # Strip accidental code fences just in case
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    plan = json.loads(raw)

    # Validate: must have reporter as last sub-agent
    sub_agents = plan.get("sub_agents", [])
    if not sub_agents or sub_agents[-1].get("role") != "reporter":
        sub_agents.append({"role": "reporter", "task": "Aggregate all prior outputs into the final deliverable."})
        plan["sub_agents"] = sub_agents

    # Add stable IDs to each sub-agent so the frontend can track status
    for i, sa in enumerate(sub_agents):
        sa["id"] = f"a{i + 1}"

    return plan


async def orchestrate_creation(
    user_message: str,
    context: dict,
) -> AsyncIterator[dict]:
    """
    Generator that yields streaming events:
      {"type": "plan", "title": ..., "intro": ..., "agents": [{id, role, task}]}
      {"type": "agent_status", "id": "a1", "status": "started"|"complete"|"failed", "output_preview"?: str}
      {"type": "artifact", "format": "markdown", "content": "..."}
      {"type": "complete"}
      {"type": "error", "value": "..."}

    `context` should include: user_id, industry, company_name (optional).
    """
    try:
        # PHASE 1: PLAN
        plan = await _plan_creation(user_message, context)
        agents = plan["sub_agents"]
        yield {
            "type": "plan",
            "title": plan.get("title", "Creation"),
            "intro": plan.get("intro", ""),
            "agents": [{"id": a["id"], "role": a["role"], "task": a["task"]} for a in agents],
        }

        # PHASE 2: PARALLEL SUB-AGENT EXECUTION (everything except reporter)
        parallel_agents = [a for a in agents if a["role"] != "reporter"]
        reporter_agent = next((a for a in agents if a["role"] == "reporter"), None)

        # Emit "started" for all parallel agents immediately
        for a in parallel_agents:
            yield {"type": "agent_status", "id": a["id"], "status": "started"}

        # Run them in parallel
        parallel_tasks = [
            run_sub_agent(role=a["role"], task=a["task"], context=context)
            for a in parallel_agents
        ]
        parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=False)

        # Map results back to agent IDs and emit completion events
        outputs_by_id: dict[str, dict] = {}
        for agent, result in zip(parallel_agents, parallel_results):
            outputs_by_id[agent["id"]] = result
            preview = (result.get("output") or result.get("error") or "")[:200]
            yield {
                "type": "agent_status",
                "id": agent["id"],
                "status": "complete" if result["ok"] else "failed",
                "output_preview": preview,
            }

        # PHASE 3: REPORTER AGGREGATION
        if reporter_agent:
            yield {"type": "agent_status", "id": reporter_agent["id"], "status": "started"}

            reporter_context = {
                **context,
                "prior_outputs": [
                    {
                        "role": a["role"],
                        "task": a["task"],
                        "output": outputs_by_id[a["id"]].get("output", ""),
                    }
                    for a in parallel_agents
                ],
            }
            reporter_result = await run_sub_agent(
                role="reporter",
                task=reporter_agent["task"],
                context=reporter_context,
                max_tokens=4096,
            )
            yield {
                "type": "agent_status",
                "id": reporter_agent["id"],
                "status": "complete" if reporter_result["ok"] else "failed",
                "output_preview": (reporter_result.get("output") or "")[:200],
            }

            if reporter_result["ok"]:
                yield {
                    "type": "artifact",
                    "format": "markdown",
                    "content": reporter_result["output"],
                }
            else:
                yield {
                    "type": "error",
                    "value": f"Reporter failed: {reporter_result.get('error', 'unknown')}",
                }

        yield {"type": "complete"}

    except json.JSONDecodeError as e:
        yield {"type": "error", "value": f"Orchestrator returned invalid JSON: {e}"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "error", "value": f"Orchestration failed: {str(e)[:200]}"}
