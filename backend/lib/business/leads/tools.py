"""mgcoleads — Anthropic tool definitions + dispatcher (prefix `leads__`).

Gated on config.leads_enabled() in tool_builder, dispatched specially in tool_executor
(like the real-estate + twenty suites). B2B only — local businesses MG&CO sells to.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.leads import engine

LEADS_TOOLS: dict[str, dict] = {
    "leads__find_leads": {
        "description": (
            "[MG&CO Leads] Find and SCORE local B2B businesses to cold-pitch MG&CO's services. "
            "Give an industry + location (e.g. 'dental clinics in Mississauga', 'salons in downtown "
            "Toronto'). Returns a ranked A/B/C list — each lead's score (0-100), tier, contact info "
            "(phone, website-or-none, address), rating + review count, and a one-line 'why + what to "
            "pitch' that maps the gap to an MG&CO product (Premium Website, AI Receptionist). Hot lead "
            "= call-dependent business with real reviews but a weak/absent website. Results are cached "
            "and persisted so you can filter or push them to the CRM afterward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Industry + location, e.g. 'law firms in Oakville'."},
                "max_results": {"type": "integer", "description": "Cap on businesses to fetch (default 40, for cost control)."},
            },
            "required": ["query"],
        },
    },
    "leads__list_leads": {
        "description": (
            "[MG&CO Leads] List already-found leads from the database, ranked by score. Use for "
            "conversational follow-ups like 'show only A-tier', 'which ones haven't I added to the CRM', "
            "or to re-show the pipeline without spending another API call. Filter by tier and/or "
            "pushed-to-CRM status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tier": {"type": "string", "enum": ["A", "B", "C"], "description": "Only this tier (optional)."},
                "pushed": {"type": "boolean", "description": "true = only leads already in the CRM; false = only not-yet-pushed (optional)."},
                "limit": {"type": "integer", "description": "Max leads to return (default 50)."},
            },
            "required": [],
        },
    },
    "leads__push_to_crm": {
        "description": (
            "[MG&CO Leads] Push selected scored leads into the Rue CRM as Companies, with the "
            "gap/pitch attached as a note — closes the loop (scrape → score → pitch → track). Select by "
            "tier (e.g. all A-tier) and/or explicit business names. Idempotent (skips leads already "
            "pushed; companies de-dupe on name). Use when the user says 'add these to my CRM' / 'add the "
            "A-tier leads to my pipeline'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tier": {"type": "string", "enum": ["A", "B", "C"], "description": "Push every lead of this tier (optional)."},
                "names": {"type": "array", "items": {"type": "string"}, "description": "Specific business names to push (optional)."},
                "limit": {"type": "integer", "description": "Max leads to push in one go (default 25)."},
            },
            "required": [],
        },
    },
}


async def execute_leads_tool(action_name: str, inp: dict, user_id: str) -> ConnectorResult:
    # Defense-in-depth: Rue Leads is Emperor-only. tool_builder already withholds these
    # tools from non-Emperor users, but gate the cash-cost actions here too in case a tool
    # call slips through (stale toolset, replay, etc.). Fail open on a billing lookup error.
    if action_name in ("find_leads", "push_to_crm") and user_id:
        try:
            from backend.lib.billing import entitlements
            allowed, _reason = entitlements.leads_allowed(user_id)
            if not allowed:
                return ConnectorResult(
                    ok=False,
                    error="Rue Leads is an Emperor-tier feature. Upgrade to Emperor to use it.",
                )
        except Exception:
            pass

    if action_name == "find_leads":
        return await engine.run_search(user_id, inp.get("query", ""), inp.get("max_results"))
    if action_name == "list_leads":
        return await engine.list_leads(user_id, tier=inp.get("tier"),
                                       limit=int(inp.get("limit", 50)), pushed=inp.get("pushed"))
    if action_name == "push_to_crm":
        return await engine.push_to_crm(user_id, tier=inp.get("tier"),
                                        names=inp.get("names"), limit=int(inp.get("limit", 25)))
    return ConnectorResult(ok=False, error=f"Unknown leads action: {action_name}")
