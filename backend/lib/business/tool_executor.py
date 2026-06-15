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
from backend.lib.business.document_store import resolve_attachments
from backend.lib.business.real_estate.tools import execute_real_estate_tool
from backend.lib.business.scheduled_emails import (
    cancel_scheduled_email,
    list_scheduled_emails,
    schedule_email,
)
from backend.lib.business.web_scrape import execute_web_tool


async def execute_tool(tool_name: str, tool_input: dict, user_id: str) -> str:
    """
    Execute one tool call. Returns a JSON string (success data or error object).
    """
    parts = tool_name.split("__", 1)
    if len(parts) != 2:
        return json.dumps({"error": f"Invalid tool name format: {tool_name}"})

    connector_type, action_name = parts

    # Real Estate tools aren't simple connector wrappers — each implementation
    # checks its own connector dependencies (GHL, Google) internally.
    if connector_type == "realestate":
        try:
            result: ConnectorResult = await execute_real_estate_tool(action_name, tool_input, user_id)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})

        if result.ok:
            return json.dumps(result.data or {}, default=str)
        return json.dumps({"error": result.error or "Action failed with no error message"})

    # Web tools are always-on — no connector/credentials needed.
    if connector_type == "web":
        try:
            result: ConnectorResult = await execute_web_tool(action_name, tool_input)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})

        if result.ok:
            return json.dumps(result.data or {}, default=str)
        return json.dumps({"error": result.error or "Action failed with no error message"})

    connector = await get_connector_for_user(user_id, connector_type)
    if not connector:
        return json.dumps({
            "error": (
                f"Not connected to {connector_type}. "
                "Connect it via Settings → Connections and try again."
            )
        })

    try:
        result: ConnectorResult = await _dispatch(connector, connector_type, action_name, tool_input, user_id)
    except Exception as e:
        return json.dumps({"error": f"Tool execution error: {e}"})

    if result.ok:
        return json.dumps(result.data or {}, default=str)
    return json.dumps({"error": result.error or "Action failed with no error message"})


async def _dispatch(connector, connector_type: str, action_name: str, inp: dict, user_id: str = "") -> ConnectorResult:
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
        if action_name == "list_pages":
            return await connector.list_pages()
        if action_name == "create_database":
            return await connector.create_database(
                parent_page_id=inp["parent_page_id"],
                title=inp["title"],
                columns=inp.get("columns"),
            )

    # ── Google (Calendar + Gmail) ─────────────────────────────────────────────
    if connector_type == "google":
        if action_name == "list_calendar_events":
            return await connector.list_calendar_events(max_results=int(inp.get("max_results", 10)))
        if action_name == "create_calendar_event":
            return await connector.create_calendar_event(event_body=inp["event_body"])
        if action_name == "update_calendar_event":
            return await connector.update_calendar_event(
                event_id=inp["event_id"],
                summary=inp.get("summary"),
                description=inp.get("description"),
                start=inp.get("start"),
                end=inp.get("end"),
                location=inp.get("location"),
            )
        if action_name == "delete_calendar_event":
            return await connector.delete_calendar_event(event_id=inp["event_id"])
        if action_name == "freebusy":
            return await connector.freebusy(
                time_min=inp["time_min"],
                time_max=inp["time_max"],
                calendar_ids=inp.get("calendar_ids"),
            )
        if action_name == "find_free_slot":
            return await connector.find_free_slot(
                duration_min=int(inp["duration_min"]),
                time_min=inp.get("time_min"),
                time_max=inp.get("time_max"),
                work_start_hour=int(inp.get("work_start_hour", 9)),
                work_end_hour=int(inp.get("work_end_hour", 17)),
                timezone_name=inp.get("timezone", "America/Toronto"),
            )
        if action_name == "list_emails":
            return await connector.list_emails(
                max_results=int(inp.get("max_results", 10)),
                query=inp.get("query", ""),
            )
        if action_name == "prioritize_emails":
            return await connector.list_emails(
                max_results=int(inp.get("max_results", 20)),
                query=inp.get("query", "is:unread"),
            )
        if action_name == "get_message":
            return await connector.get_message(message_id=inp["message_id"])
        if action_name == "modify_labels":
            return await connector.modify_labels(
                message_id=inp["message_id"],
                add_labels=inp.get("add_labels"),
                remove_labels=inp.get("remove_labels"),
            )
        if action_name == "mark_read":
            return await connector.mark_read(
                message_id=inp["message_id"],
                read=bool(inp.get("read", True)),
            )
        if action_name == "send_email":
            attachments, attach_error = resolve_attachments(inp.get("attachments"))
            if attach_error:
                return ConnectorResult(ok=False, error=attach_error)
            return await connector.send_email(
                to=inp["to"],
                subject=inp["subject"],
                body=inp.get("body", ""),
                cc=inp.get("cc", ""),
                attachments=attachments or None,
            )
        if action_name == "create_draft":
            attachments, attach_error = resolve_attachments(inp.get("attachments"))
            if attach_error:
                return ConnectorResult(ok=False, error=attach_error)
            return await connector.create_draft(
                to=inp["to"],
                subject=inp["subject"],
                body=inp.get("body", ""),
                cc=inp.get("cc", ""),
                attachments=attachments or None,
            )
        if action_name == "list_drafts":
            return await connector.list_drafts(max_results=int(inp.get("max_results", 10)))
        if action_name == "get_draft":
            return await connector.get_draft(draft_id=inp["draft_id"])
        if action_name == "schedule_email":
            return await schedule_email(
                user_id,
                to_email=inp["to"],
                subject=inp["subject"],
                body=inp.get("body", ""),
                send_at=inp["send_at"],
                cc=inp.get("cc", ""),
                attachments=inp.get("attachments"),
            )
        if action_name == "list_scheduled_emails":
            return await list_scheduled_emails(user_id, status=inp.get("status"))
        if action_name == "cancel_scheduled_email":
            return await cancel_scheduled_email(user_id, scheduled_id=inp["id"])

    # ── GoHighLevel ───────────────────────────────────────────────────────────
    if connector_type == "gohighlevel":
        if action_name == "list_contacts":
            return await connector.list_contacts_v2(limit=int(inp.get("limit", 20)))
        if action_name == "search_contacts":
            return await connector.search_contacts_v2(query=inp["query"])
        if action_name == "create_contact":
            return await connector.create_contact(contact_data=inp)
        if action_name == "list_pipelines":
            return await connector.list_pipelines()
        if action_name == "list_opportunities":
            return await connector.list_opportunities(pipeline_id=inp["pipeline_id"])
        if action_name == "list_appointments":
            return await connector.list_appointments()

    # ── GitHub ────────────────────────────────────────────────────────────────
    if connector_type == "github":
        if action_name == "list_repos":
            return await connector.list_repos(limit=int(inp.get("limit", 10)))
        if action_name == "create_repo":
            return await connector.create_repo(
                name=inp["name"],
                description=inp.get("description", ""),
                private=bool(inp.get("private", False)),
            )
        if action_name == "push_files":
            return await connector.push_files(
                repo=inp["repo"],
                files=inp["files"],
                message=inp.get("message", "Jarvis OS1: automated commit"),
                branch=inp.get("branch", "main"),
            )

    # ── Vercel ────────────────────────────────────────────────────────────────
    if connector_type == "vercel":
        if action_name == "list_projects":
            return await connector.list_projects(limit=int(inp.get("limit", 10)))
        if action_name == "create_project":
            return await connector.create_project(
                name=inp["name"],
                github_repo=inp.get("github_repo", ""),
                framework=inp.get("framework", "nextjs"),
            )
        if action_name == "trigger_deploy":
            return await connector.trigger_deploy(
                project_name=inp["project_name"],
                github_repo=inp.get("github_repo", ""),
                branch=inp.get("branch", "main"),
            )
        if action_name == "get_deployment":
            return await connector.get_deployment(deployment_id=inp["deployment_id"])

    # ── Buffer ───────────────────────────────────────────────────────────────
    if connector_type == "buffer":
        if action_name == "list_organizations":
            return await connector.list_organizations()
        if action_name == "list_channels":
            return await connector.list_channels(organization_id=inp.get("organization_id"))
        if action_name == "get_channel":
            return await connector.get_channel(channel_id=inp["channel_id"])
        if action_name == "get_scheduled_posts":
            return await connector.get_scheduled_posts(
                channel_ids=inp.get("channel_ids"),
                limit=int(inp.get("limit", 20)),
                organization_id=inp.get("organization_id"),
            )
        if action_name == "get_sent_posts":
            return await connector.get_sent_posts(
                channel_ids=inp.get("channel_ids"),
                limit=int(inp.get("limit", 20)),
                organization_id=inp.get("organization_id"),
            )
        if action_name == "create_post":
            return await connector.create_post(
                text=inp.get("text", ""),
                channel_ids=inp.get("channel_ids", []),
                mode=inp.get("mode", "addToQueue"),
                publish_at=inp.get("publish_at"),
                media_urls=inp.get("media_urls", []),
                networks=inp.get("networks", []),
            )
        if action_name == "schedule_post":
            return await connector.schedule_post(
                text=inp.get("text", ""),
                channel_ids=inp.get("channel_ids", []),
                publish_at=inp.get("publish_at", ""),
                media_urls=inp.get("media_urls", []),
                networks=inp.get("networks", []),
            )
        if action_name == "add_to_queue":
            return await connector.add_to_queue(
                text=inp.get("text", ""),
                channel_ids=inp.get("channel_ids", []),
                media_urls=inp.get("media_urls", []),
                networks=inp.get("networks", []),
            )

    # ── Supabase (user projects) ──────────────────────────────────────────────
    if connector_type == "supabase_project":
        if action_name == "list_projects":
            return await connector.list_projects()
        if action_name == "get_project_keys":
            return await connector.get_project_keys(project_id=inp["project_id"])
        if action_name == "run_sql":
            return await connector.run_sql(project_id=inp["project_id"], sql=inp["sql"])

    return ConnectorResult(ok=False, error=f"Unknown action: {connector_type}__{action_name}")
