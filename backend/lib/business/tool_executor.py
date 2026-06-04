"""
Route Anthropic tool_use calls to the correct connector method.
Tool name format: "connector_type__action_name" (double underscore separator).

Uses get_connector_for_user() from the registry — it fetches credentials from
business_connections and returns an authenticated connector instance. Returns
a JSON string for Claude to interpret.
"""
import json

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user


async def execute_tool(tool_name: str, tool_input: dict, user_id: str) -> str:
    """
    Execute one tool call. Returns a JSON string (success data or error object).
    """
    parts = tool_name.split("__", 1)
    if len(parts) != 2:
        return json.dumps({"error": f"Invalid tool name format: {tool_name}"})

    connector_type, action_name = parts

    connector = await get_connector_for_user(user_id, connector_type)
    if not connector:
        return json.dumps({
            "error": (
                f"Not connected to {connector_type}. "
                "Connect it via Settings → Connections and try again."
            )
        })

    try:
        result: ConnectorResult = await _dispatch(connector, connector_type, action_name, tool_input)
    except Exception as e:
        return json.dumps({"error": f"Tool execution error: {e}"})

    if result.ok:
        return json.dumps(result.data or {}, default=str)
    return json.dumps({"error": result.error or "Action failed with no error message"})


async def _dispatch(connector, connector_type: str, action_name: str, inp: dict) -> ConnectorResult:
    """Map (connector_type, action_name) → connector method call."""

    # ── Stripe ────────────────────────────────────────────────────────────────
    if connector_type == "stripe":
        if action_name == "list_recent_charges":
            return await connector.list_recent_charges(limit=int(inp.get("limit", 10)))
        if action_name == "revenue_summary":
            return await connector.revenue_summary_last_30_days()

    # ── Twilio ────────────────────────────────────────────────────────────────
    if connector_type == "twilio":
        if action_name == "send_sms":
            return await connector.send_sms(to=inp["to"], body=inp["body"])

    # ── SMTP ──────────────────────────────────────────────────────────────────
    if connector_type == "smtp":
        if action_name == "send_email":
            return await connector.send_email(
                to=inp["to"],
                subject=inp["subject"],
                body_text=inp.get("body", inp.get("body_text", "")),
            )

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    if connector_type == "elevenlabs":
        if action_name == "list_voices":
            return await connector.list_voices()
        if action_name == "text_to_speech":
            return await connector.text_to_speech(
                text=inp["text"],
                voice_id=inp.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
            )
        if action_name == "list_agents":
            return await connector.list_agents()
        if action_name == "get_agent":
            return await connector.get_agent(agent_id=inp["agent_id"])
        if action_name == "create_agent":
            return await connector.create_agent(
                name=inp["name"],
                system_prompt=inp["system_prompt"],
                first_message=inp.get("first_message", "Hello! How can I help you?"),
                voice_id=inp.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
                language=inp.get("language", "en"),
            )
        if action_name == "update_agent":
            kwargs = {k: v for k, v in inp.items() if k != "agent_id"}
            return await connector.update_agent(agent_id=inp["agent_id"], **kwargs)
        if action_name == "delete_agent":
            return await connector.delete_agent(agent_id=inp["agent_id"])

    # ── Notion ────────────────────────────────────────────────────────────────
    if connector_type == "notion":
        if action_name == "search":
            return await connector.search(
                query=inp.get("query", ""),
                filter_type=inp.get("filter_type"),
            )
        if action_name == "read_page":
            return await connector.read_page(page_id=inp["page_id"])
        if action_name == "query_database":
            return await connector.query_database(
                database_id=inp["database_id"],
                filter_obj=inp.get("filter"),
            )
        if action_name == "create_page":
            return await connector.create_page(
                database_id=inp["database_id"],
                properties=inp["properties"],
                children=inp.get("children"),
            )

    # ── Google (Calendar + Gmail) ─────────────────────────────────────────────
    if connector_type == "google":
        if action_name == "list_calendar_events":
            return await connector.list_calendar_events(max_results=int(inp.get("max_results", 10)))
        if action_name == "create_calendar_event":
            return await connector.create_calendar_event(event_body=inp["event_body"])
        if action_name == "list_emails":
            return await connector.list_emails(
                max_results=int(inp.get("max_results", 10)),
                query=inp.get("query", ""),
            )
        if action_name == "send_email":
            return await connector.send_email(
                to=inp["to"],
                subject=inp["subject"],
                body=inp.get("body", ""),
            )

    # ── GoHighLevel ───────────────────────────────────────────────────────────
    if connector_type == "gohighlevel":
        if action_name == "list_contacts":
            return await connector.list_contacts(limit=int(inp.get("limit", 20)))
        if action_name == "search_contacts":
            return await connector.search_contacts(query=inp["query"])
        if action_name == "create_contact":
            return await connector.create_contact(contact_data=inp)
        if action_name == "list_pipelines":
            return await connector.list_pipelines()
        if action_name == "list_opportunities":
            return await connector.list_opportunities(pipeline_id=inp["pipeline_id"])
        if action_name == "list_appointments":
            return await connector.list_appointments()

    return ConnectorResult(ok=False, error=f"Unknown action: {connector_type}__{action_name}")
