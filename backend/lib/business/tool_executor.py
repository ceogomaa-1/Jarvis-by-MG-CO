"""
Route Anthropic tool_use calls to the correct connector method.
Tool name format: "connector_type__action_name" (double underscore separator).

Uses get_connector_for_user() from the registry — it fetches credentials from
business_connections and returns an authenticated connector instance. Returns
a JSON string for Claude to interpret.
"""
import asyncio
import json

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.document_store import resolve_attachments
from backend.lib.business.leads.tools import execute_leads_tool
from backend.lib.business.real_estate.tools import execute_real_estate_tool
from backend.lib.business.twenty.tools import execute_twenty_tool
from backend.lib.business.scheduled_emails import (
    cancel_scheduled_email,
    list_scheduled_emails,
    schedule_email,
)
from backend.lib.business.web_scrape import execute_web_tool


async def execute_tool(tool_name: str, tool_input: dict, user_id: str, progress_cb=None) -> str:
    """
    Execute one tool call. Returns a JSON string (success data or error object).

    `progress_cb(message: str)` is an optional async callback for tools that
    stream human-readable progress (e.g. web research). Tools that don't support
    it simply ignore it.
    """
    parts = tool_name.split("__", 1)
    if len(parts) != 2:
        return json.dumps({"error": f"Invalid tool name format: {tool_name}"})

    connector_type, action_name = parts

    # Real Estate tools aren't simple connector wrappers — each implementation
    # checks its own connector dependencies (GHL, Google) internally.
    if connector_type == "realestate":
        try:
            result: ConnectorResult = await execute_real_estate_tool(action_name, tool_input, user_id, progress_cb=progress_cb)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})

        if result.ok:
            return json.dumps(result.data or {}, default=str)
        return json.dumps({"error": result.error or "Action failed with no error message"})

    # Jarvis CRM (Twenty) — read + write. execute_twenty_tool resolves the user's
    # OWN workspace (Phase 2 for_user) before any read/write, so every operation is
    # scoped to that client's tenant. Writes go to Twenty only, never GHL.
    if connector_type == "twenty":
        try:
            result: ConnectorResult = await execute_twenty_tool(action_name, tool_input, user_id)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})

        if result.ok:
            return json.dumps(result.data or {}, default=str)
        return json.dumps({"error": result.error or "Action failed with no error message"})

    # mgcoleads — MG&CO's B2B lead engine (ingest + score + push-to-CRM). Env-gated;
    # dispatched specially (not a connector wrapper). Scoped to user_id internally.
    if connector_type == "leads":
        try:
            result: ConnectorResult = await execute_leads_tool(action_name, tool_input, user_id)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})
        if result.ok:
            return json.dumps(result.data or {}, default=str)
        return json.dumps({"error": result.error or "Action failed with no error message"})

    # Dashboard Studio (Batch 68) — Jarvis builds/edits the user's Home dashboard. Always-on,
    # scoped to user_id internally. Only touches the user's own dashboard, so no confirm gate.
    if connector_type == "dashboard":
        try:
            from backend.lib.business.dashboard_studio import execute_dashboard_tool
            result = await execute_dashboard_tool(action_name, tool_input, user_id)
        except Exception as e:
            return json.dumps({"error": f"Tool execution error: {e}"})
        return json.dumps(result, default=str)

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


async def _enforce_buffer_platform_cap(connector, user_id: str, channel_ids, organization_id=None):
    """Block a Buffer post that would exceed the user's platform cap (Pro = 2, Emperor = ∞).

    Resolves the target channels to their Buffer *services* (the platform), then asks the
    entitlements layer whether this user may post to that platform set. On allow, records the
    platforms used so the cap is first-come-first-served. Returns a ConnectorResult(error) to
    block, or None to allow.

    Fails OPEN: if we can't resolve services (no org id, list_channels error, no user_id) we
    don't block a legitimate post — the cap is a monetization gate, not a security boundary."""
    from backend.lib.billing import entitlements as _ent, store as _bstore

    if not user_id or not channel_ids:
        return None

    # Map channel_id -> service via the org's channel list.
    try:
        channels_res = await connector.list_channels(organization_id=organization_id)
    except Exception:
        return None
    if not channels_res.ok:
        return None
    by_id = {c.get("id"): (c.get("service") or "").lower()
             for c in ((channels_res.data or {}).get("channels") or [])}
    target_services = {by_id.get(cid) for cid in channel_ids if by_id.get(cid)}
    if not target_services:
        return None

    try:
        allowed, reason, to_record = await asyncio.to_thread(
            _ent.buffer_platform_check, user_id, target_services
        )
    except Exception:
        return None  # fail open on entitlements lookup failure

    if not allowed:
        return ConnectorResult(ok=False, error=reason, data={"upgrade": "emperor"})
    if to_record:
        try:
            await asyncio.to_thread(_bstore.add_buffer_platforms, user_id, to_record)
        except Exception:
            pass
    return None


async def _dispatch(connector, connector_type: str, action_name: str, inp: dict, user_id: str = "") -> ConnectorResult:
    """Map (connector_type, action_name) → connector method call."""

    # ── Stripe ────────────────────────────────────────────────────────────────
    if connector_type == "stripe":
        if action_name == "list_recent_charges":
            return await connector.list_recent_charges(limit=int(inp.get("limit", 10)))
        if action_name == "revenue_summary":
            return await connector.revenue_summary_last_30_days()
        if action_name == "create_subscription_tier":
            return await connector.create_subscription_product(
                name=inp["name"],
                amount_cents=int(inp["amount_cents"]),
                description=inp.get("description"),
                interval=inp.get("interval", "month"),
                currency=inp.get("currency", "usd"),
            )
        if action_name == "create_product":
            return await connector.create_product(
                name=inp["name"],
                description=inp.get("description"),
            )
        if action_name == "create_price":
            return await connector.create_price(
                product_id=inp["product_id"],
                unit_amount=int(inp["unit_amount"]),
                currency=inp.get("currency", "usd"),
                interval=inp.get("interval"),
                nickname=inp.get("nickname"),
            )

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
                message=inp.get("message", "Update project files"),
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
        # Pro tier is capped at 2 distinct social platforms (Emperor = unlimited). Enforce on
        # the WRITE actions only — reads are free. Posting to a platform that would push the
        # user past their cap is blocked with an upgrade prompt.
        if action_name in ("create_post", "schedule_post", "add_to_queue"):
            gate = await _enforce_buffer_platform_cap(
                connector, user_id, inp.get("channel_ids", []), inp.get("organization_id")
            )
            if gate is not None:
                return gate
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
