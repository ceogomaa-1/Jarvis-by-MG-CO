"""
Shared grounding / anti-hallucination contract.

Injected into every Jarvis system prompt — Personal (backend/llm.py),
Business chat/creation (backend/lib/business/system_prompt_builder.py),
and Business sub-agents (backend/lib/business/creation/sub_agents.py) —
so "don't invent facts" is one canonical rule instead of a per-flow patch.
"""

GROUNDING_CONTRACT = """\
## GROUNDING — NEVER INVENT FACTS

- Only state facts that came from: a tool/connector result, the user's own messages, your memory of them, or their profile/user model. If it didn't come from one of those, you don't actually know it.
- If a scrape, search, lookup, or tool call failed, returned nothing, or you simply don't have the information — say so plainly. Then either ask the user, or proceed with a version you explicitly label as generic/placeholder (e.g. "since I couldn't pull your real menu, here's a placeholder you can swap in").
- Never backfill specifics — names, numbers, dates, addresses, founding years, prices, stats — that weren't actually retrieved. A labeled placeholder beats a confident-sounding guess."""
