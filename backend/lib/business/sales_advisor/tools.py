"""Sales Advisor — Anthropic tool definitions + dispatcher (prefix `sales__`).

Gated on sales_advisor.config.enabled() in tool_builder (plus the same Emperor tier gate
as the leads suite — this burns real Opus + Places spend), dispatched specially in
tool_executor like leads/twenty/real-estate.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.sales_advisor import engine

SALES_TOOLS: dict[str, dict] = {
    "sales__analyze_business": {
        "description": (
            "[Sales Advisor] Deep-research ONE specific business and build a closer-grade pitch "
            "report for Mohamed to sell MG&CO services to them: gaps found (with evidence), a "
            "Hormozi-style offer, a 10-12 slide pitch deck with exact words to say, a call script, "
            "and objection handling. Give a Google Maps link (any form, incl. maps.app.goo.gl) "
            "and/or the business name + city, plus any extra intel the user has. Runs in the "
            "background (1-3 min) — tell the user it's cooking and they can open the Sales Advisor "
            "panel or ask for the report shortly. Use when the user says 'analyze this business', "
            "'build me a pitch for X', 'I'm calling this salon tomorrow — prep me'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "maps_url": {"type": "string", "description": "Google Maps link to the business (optional if name given)."},
                "business_name": {"type": "string", "description": "Business name, ideally with city (optional if maps_url given)."},
                "notes": {"type": "string", "description": "Any extra intel the user shared: who the owner is, past contact, what they know (optional)."},
            },
            "required": [],
        },
    },
    "sales__get_report": {
        "description": (
            "[Sales Advisor] Fetch a pitch report — the latest one by default, or by report_id. "
            "While status is 'running' it returns the live progress stage. Once 'complete' it "
            "returns the full report (snapshot, kill_shots, offer, pitch_deck, call_script, "
            "objections, closing_moves) so you can walk the user through it, rehearse objections, "
            "or adapt lines. Use for 'is my pitch ready', 'show me the deck', 'how do I answer X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "string", "description": "Specific report id (optional — default latest)."},
            },
            "required": [],
        },
    },
    "sales__list_reports": {
        "description": (
            "[Sales Advisor] List past pitch reports (business, status, when). Use for 'which "
            "businesses have I analyzed', or to find a report_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max reports (default 20)."},
            },
            "required": [],
        },
    },
}


async def execute_sales_tool(action_name: str, inp: dict, user_id: str) -> ConnectorResult:
    # Defense-in-depth tier gate, mirroring leads: tool_builder already withholds these
    # from non-Emperor users; re-check the cash-cost action here. Fail open on lookup errors.
    if action_name == "analyze_business" and user_id:
        try:
            from backend.lib.billing import entitlements
            allowed, _reason = entitlements.leads_allowed(user_id)
            if not allowed:
                return ConnectorResult(
                    ok=False,
                    error="Sales Advisor is an Emperor-tier feature. Upgrade to Emperor to use it.")
        except Exception:
            pass

    if action_name == "analyze_business":
        return await engine.start_analysis(user_id, maps_url=inp.get("maps_url"),
                                           business_name=inp.get("business_name"),
                                           notes=inp.get("notes"))
    if action_name == "get_report":
        return await engine.get_report(user_id, inp.get("report_id") or None)
    if action_name == "list_reports":
        return await engine.list_reports(user_id, limit=int(inp.get("limit", 20)))
    return ConnectorResult(ok=False, error=f"Unknown sales action: {action_name}")
