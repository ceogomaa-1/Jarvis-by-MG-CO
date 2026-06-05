"""
Build Anthropic tool definitions from the user's active connector connections.
Only includes tools for connectors the user has actually connected (status=active).
Returns [] if nothing is connected — never pass an empty list to Anthropic (omit the param instead).
"""
from backend.lib.business.connectors.registry import list_user_connections

# ─────────────────────────────────────────────────────────────────────────────
# Static tool registry: tool_name → {description, input_schema}
# Tool names use connector_type__action_name (double underscore).
# ─────────────────────────────────────────────────────────────────────────────
_TOOLS: dict[str, dict] = {

    # ── Stripe ────────────────────────────────────────────────────────────────
    "stripe__list_recent_charges": {
        "description": "[Stripe] List recent charges / transactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max charges to return (1-100, default 10)"},
            },
            "required": [],
        },
    },
    "stripe__revenue_summary": {
        "description": "[Stripe] Get gross revenue summary for the last 30 days — total, count, and currency.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },

    # ── Twilio ────────────────────────────────────────────────────────────────
    "twilio__send_sms": {
        "description": "[Twilio] Send an SMS message to a phone number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number in E.164 format (e.g. +14155551234)"},
                "body": {"type": "string", "description": "SMS message body"},
            },
            "required": ["to", "body"],
        },
    },

    # ── SMTP ──────────────────────────────────────────────────────────────────
    "smtp__send_email": {
        "description": "[Email/SMTP] Send an email via the connected SMTP server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (plain text)"},
            },
            "required": ["to", "subject", "body"],
        },
    },

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    "elevenlabs__list_voices": {
        "description": "[ElevenLabs] List all available voices in the account.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "elevenlabs__text_to_speech": {
        "description": "[ElevenLabs] Convert text to speech. Returns base64-encoded MP3 audio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert to speech"},
                "voice_id": {"type": "string", "description": "Voice ID from list_voices (optional, defaults to Rachel)"},
            },
            "required": ["text"],
        },
    },
    "elevenlabs__list_agents": {
        "description": "[ElevenLabs] List all Conversational AI agents in the account.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "elevenlabs__get_agent": {
        "description": "[ElevenLabs] Get full details of a specific Conversational AI agent (config, voice, system prompt).",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The agent ID to retrieve"},
            },
            "required": ["agent_id"],
        },
    },
    "elevenlabs__create_agent": {
        "description": "[ElevenLabs] Create a new Conversational AI agent. Draft config first, confirm with user before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for the new agent"},
                "system_prompt": {"type": "string", "description": "System prompt / instructions for the agent"},
                "first_message": {"type": "string", "description": "Greeting message the agent says first"},
                "voice_id": {"type": "string", "description": "ElevenLabs voice ID (get from list_voices)"},
                "language": {"type": "string", "description": "Language code (default: en)"},
            },
            "required": ["name", "system_prompt"],
        },
    },
    "elevenlabs__update_agent": {
        "description": "[ElevenLabs] Update an existing Conversational AI agent. Show changes to user and confirm before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The agent ID to update"},
                "name": {"type": "string", "description": "New name (optional)"},
                "system_prompt": {"type": "string", "description": "New system prompt (optional)"},
                "first_message": {"type": "string", "description": "New first message (optional)"},
                "voice_id": {"type": "string", "description": "New voice ID (optional)"},
            },
            "required": ["agent_id"],
        },
    },
    "elevenlabs__delete_agent": {
        "description": "[ElevenLabs] Delete a Conversational AI agent. ALWAYS confirm with user first — irreversible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The agent ID to delete"},
            },
            "required": ["agent_id"],
        },
    },

    # ── Notion ────────────────────────────────────────────────────────────────
    "notion__search": {
        "description": "[Notion] Search pages and databases in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "filter_type": {
                    "type": "string",
                    "enum": ["page", "database"],
                    "description": "Filter to only pages or only databases (optional)",
                },
            },
            "required": ["query"],
        },
    },
    "notion__read_page": {
        "description": "[Notion] Read the full content and properties of a Notion page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Notion page ID"},
            },
            "required": ["page_id"],
        },
    },
    "notion__query_database": {
        "description": "[Notion] Query a Notion database with optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Notion database ID"},
                "filter": {"type": "object", "description": "Notion filter object (optional)"},
            },
            "required": ["database_id"],
        },
    },
    "notion__create_page": {
        "description": "[Notion] Create a new page in a Notion database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Parent database ID"},
                "properties": {"type": "object", "description": "Page properties matching the database schema"},
                "children": {
                    "type": "array",
                    "description": "Page content blocks (optional)",
                    "items": {"type": "object"},
                },
            },
            "required": ["database_id", "properties"],
        },
    },
    "notion__list_pages": {
        "description": "[Notion] List top-level pages shared with the integration — use to find parent page IDs before creating a database.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "notion__create_database": {
        "description": "[Notion] Create a new database under a parent page. ALWAYS call list_pages first and confirm parent + schema with user before creating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_page_id": {"type": "string", "description": "ID of the parent page (from list_pages)"},
                "title": {"type": "string", "description": "Name of the new database"},
                "columns": {
                    "type": "array",
                    "description": "Custom columns beyond the default 'Name' title column",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "description": "rich_text, number, select, date, checkbox, url, email, phone_number",
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Options for select-type columns",
                            },
                            "format": {
                                "type": "string",
                                "description": "Number format (number, dollar, percent) for number columns",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["parent_page_id", "title"],
        },
    },

    # ── Google Calendar + Gmail ───────────────────────────────────────────────
    "google__list_calendar_events": {
        "description": "[Google Calendar] List upcoming calendar events from the primary calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Max events to return (default 10)"},
            },
            "required": [],
        },
    },
    "google__create_calendar_event": {
        "description": "[Google Calendar] Create a new event on the primary calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_body": {
                    "type": "object",
                    "description": "Google Calendar event object",
                    "properties": {
                        "summary": {"type": "string", "description": "Event title"},
                        "start": {
                            "type": "object",
                            "description": "Start time as {dateTime: ISO8601, timeZone: 'America/Toronto'}",
                        },
                        "end": {
                            "type": "object",
                            "description": "End time as {dateTime: ISO8601, timeZone: 'America/Toronto'}",
                        },
                        "description": {"type": "string", "description": "Event description (optional)"},
                        "location": {"type": "string", "description": "Location (optional)"},
                    },
                    "required": ["summary", "start", "end"],
                },
            },
            "required": ["event_body"],
        },
    },
    "google__update_calendar_event": {
        "description": "[Google Calendar] Update an existing calendar event (title, time, description, location). Confirm with user before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID from list_calendar_events"},
                "summary": {"type": "string", "description": "New event title (optional)"},
                "description": {"type": "string", "description": "New description (optional)"},
                "start": {"type": "object", "description": "New start: {dateTime: ISO8601, timeZone: string} (optional)"},
                "end": {"type": "object", "description": "New end: {dateTime: ISO8601, timeZone: string} (optional)"},
                "location": {"type": "string", "description": "New location (optional)"},
            },
            "required": ["event_id"],
        },
    },
    "google__delete_calendar_event": {
        "description": "[Google Calendar] Delete a calendar event permanently. ALWAYS confirm with user first — irreversible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID from list_calendar_events"},
            },
            "required": ["event_id"],
        },
    },
    "google__list_emails": {
        "description": "[Gmail] List recent emails. Optionally filter with a Gmail search query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Max emails to return (default 10)"},
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g. 'is:unread', 'from:boss@company.com', 'subject:invoice')",
                },
            },
            "required": [],
        },
    },
    "google__send_email": {
        "description": "[Gmail] Send an email via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
            },
            "required": ["to", "subject", "body"],
        },
    },

    # ── GoHighLevel ───────────────────────────────────────────────────────────
    "gohighlevel__list_contacts": {
        "description": "[GoHighLevel] List CRM contacts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max contacts (default 20)"},
            },
            "required": [],
        },
    },
    "gohighlevel__search_contacts": {
        "description": "[GoHighLevel] Search CRM contacts by name, email, or phone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
            },
            "required": ["query"],
        },
    },
    "gohighlevel__create_contact": {
        "description": "[GoHighLevel] Create a new CRM contact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "firstName": {"type": "string"},
                "lastName": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "companyName": {"type": "string"},
            },
            "required": ["firstName"],
        },
    },
    "gohighlevel__list_pipelines": {
        "description": "[GoHighLevel] List all sales pipelines.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "gohighlevel__list_opportunities": {
        "description": "[GoHighLevel] List opportunities in a sales pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "string", "description": "Pipeline ID from list_pipelines"},
            },
            "required": ["pipeline_id"],
        },
    },
    "gohighlevel__list_appointments": {
        "description": "[GoHighLevel] List upcoming appointments.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
}

# Maps each tool name to its connector_type
_TOOL_TO_CONNECTOR: dict[str, str] = {k: k.split("__")[0] for k in _TOOLS}


async def build_tools_for_user(user_id: str) -> list[dict]:
    """
    Return Anthropic tool definitions for the user's active connector connections.
    Returns [] if no connectors are active — callers must NOT pass [] to the API.
    """
    if not user_id:
        return []

    rows = await list_user_connections(user_id)
    active_types = {r["connector_type"] for r in rows if r.get("status") == "active"}

    if not active_types:
        return []

    return [
        {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
        for name, defn in _TOOLS.items()
        if _TOOL_TO_CONNECTOR[name] in active_types
    ]
