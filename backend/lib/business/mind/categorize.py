"""
Classify a memory into one of The Mind's 7 cluster categories (+ general).
This is a *separate* taxonomy from business_user_memories.category, which
tracks provenance (general / knowledge_base / morning_queue_action).
"""
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU = "claude-haiku-4-5-20251001"

MIND_CATEGORIES = ["revenue", "leads", "operations", "people", "brand", "tools", "risk", "general"]

_CATEGORIZE_PROMPT = """\
Classify the following business memory into exactly ONE of these categories:
- revenue: money, pricing, sales, financial targets, profit, costs
- leads: customers, clients, prospects, leads, deals, follow-ups
- operations: day-to-day processes, workflows, suppliers, logistics, scheduling
- people: team, hiring, staff, the owner's identity/preferences/goals
- brand: marketing, branding, content, positioning, voice
- tools: software, connectors, integrations, tech stack
- risk: warnings, problems, compliance, things that could go wrong
- general: anything that doesn't clearly fit the above

MEMORY: "{memory}"

Respond with ONLY the single category word, nothing else."""


async def categorize_memory(text: str) -> str:
    if not ANTHROPIC_API_KEY or not text or not text.strip():
        return "general"
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
                    "model": HAIKU,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": _CATEGORIZE_PROMPT.format(memory=text[:500])}],
                },
                timeout=20.0,
            )
        if resp.status_code != 200:
            print(f"MIND_CATEGORIZE: API error {resp.status_code}: {resp.text[:200]}")
            return "general"
        raw = resp.json().get("content", [{}])[0].get("text", "").strip().lower()
        raw = raw.strip(" .,!\"'")
        return raw if raw in MIND_CATEGORIES else "general"
    except Exception as e:
        print(f"MIND_CATEGORIZE: error: {e}")
        return "general"
