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

    # ── GitHub ────────────────────────────────────────────────────────────────
    "github__list_repos": {
        "description": "[GitHub] List the user's GitHub repositories, sorted by last updated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max repos to return (default 10)", "default": 10},
            },
            "required": [],
        },
    },
    "github__create_repo": {
        "description": "[GitHub] Create a new GitHub repository. Always confirm name with user before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Repository name (lowercase, hyphens ok)"},
                "description": {"type": "string", "description": "Short repo description"},
                "private": {"type": "boolean", "description": "Private repo? Default false", "default": False},
            },
            "required": ["name"],
        },
    },
    "github__push_files": {
        "description": "[GitHub] Push multiple files to a GitHub repository in a single atomic commit. Use this to push an entire project (all source files) at once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Full repo name: owner/repo-name"},
                "files": {
                    "type": "array",
                    "description": "Array of files to push",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path in repo (e.g. src/app/page.tsx)"},
                            "content": {"type": "string", "description": "Full file content as string"},
                        },
                        "required": ["path", "content"],
                    },
                },
                "message": {"type": "string", "description": "Commit message", "default": "Jarvis OS1: project files"},
                "branch": {"type": "string", "description": "Branch name", "default": "main"},
            },
            "required": ["repo", "files"],
        },
    },

    # ── Vercel ────────────────────────────────────────────────────────────────
    "vercel__list_projects": {
        "description": "[Vercel] List the user's Vercel projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max projects to return (default 10)", "default": 10},
            },
            "required": [],
        },
    },
    "vercel__create_project": {
        "description": "[Vercel] Create a new Vercel project, optionally linked to a GitHub repo for auto-deploy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Project name (lowercase, hyphens ok)"},
                "github_repo": {"type": "string", "description": "GitHub repo to link: owner/repo-name"},
                "framework": {"type": "string", "description": "Framework: nextjs, vite, etc.", "default": "nextjs"},
            },
            "required": ["name"],
        },
    },
    "vercel__trigger_deploy": {
        "description": "[Vercel] Trigger a production deployment for a Vercel project from a GitHub repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Vercel project name"},
                "github_repo": {"type": "string", "description": "owner/repo"},
                "branch": {"type": "string", "description": "Branch to deploy", "default": "main"},
            },
            "required": ["project_name"],
        },
    },
    "vercel__get_deployment": {
        "description": "[Vercel] Check the status of a Vercel deployment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deployment_id": {"type": "string", "description": "Deployment ID from trigger_deploy"},
            },
            "required": ["deployment_id"],
        },
    },

    # ── Metricool ────────────────────────────────────────────────────────────
    "metricool__list_brands": {
        "description": "[Metricool] List available Metricool brands/profiles and brand IDs for the connected account.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "metricool__get_profile": {
        "description": "[Metricool] Get brand settings/profile context for a Metricool brand, including connected networks where exposed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID. Defaults to saved default brand."},
            },
            "required": [],
        },
    },
    "metricool__get_recent_posts": {
        "description": "[Metricool] Get recent published social posts/reels and available per-post metrics. Use before judging content performance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "network": {"type": "string", "description": "Optional network: instagram, facebook, linkedin, tiktok, youtube, pinterest."},
                "limit": {"type": "integer", "description": "Max posts per network, default 20."},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD, optional."},
                "end": {"type": "string", "description": "End date YYYY-MM-DD, optional."},
                "timezone_name": {"type": "string", "description": "Timezone, default America/Toronto."},
            },
            "required": [],
        },
    },
    "metricool__get_scheduled_posts": {
        "description": "[Metricool] List queued/scheduled posts for a brand over a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD, default today."},
                "end": {"type": "string", "description": "End date YYYY-MM-DD, default 30 days out."},
                "timezone_name": {"type": "string", "description": "Timezone, default America/Toronto."},
                "extended_range": {"type": "boolean", "description": "Whether Metricool should expand the range by one day."},
            },
            "required": [],
        },
    },
    "metricool__get_available_metrics": {
        "description": "[Metricool] Return available analytics metrics by network/subject. Call this when unsure which Metricool metrics can be queried.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "network": {"type": "string", "description": "Optional network: instagram, facebook, linkedin, tiktok, youtube, etc."},
            },
            "required": [],
        },
    },
    "metricool__get_metrics": {
        "description": "[Metricool] Pull real analytics timeline data for a network and metric(s). Never invent social numbers; call this before reporting followers, impressions, reach, engagement, or growth.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "network": {"type": "string", "description": "Network to analyze, e.g. instagram, facebook, linkedin, tiktok, youtube."},
                "metric": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metric names. If omitted, connector uses default account metrics.",
                },
                "subject": {"type": "string", "description": "Optional Metricool subject/metricType such as account, posts, reels, videos."},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD, default 30 days ago."},
                "end": {"type": "string", "description": "End date YYYY-MM-DD, default today."},
                "timezone_name": {"type": "string", "description": "Timezone, default America/Toronto."},
            },
            "required": ["network"],
        },
    },
    "metricool__get_best_time_to_post": {
        "description": "[Metricool] Get best posting times for a network. Higher returned value means stronger posting window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "network": {"type": "string", "description": "Network/provider: instagram, facebook, linkedin, youtube, tiktok, twitter."},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD, default today."},
                "end": {"type": "string", "description": "End date YYYY-MM-DD, default 7 days out."},
                "timezone_name": {"type": "string", "description": "Timezone, default America/Toronto."},
            },
            "required": ["network"],
        },
    },
    "metricool__schedule_post": {
        "description": "[Metricool] WRITE: Schedule a social post across one or more networks. Show exact text, networks, media, and publish time before calling; the system will require hold-to-confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "text": {"type": "string", "description": "Post caption/text."},
                "networks": {"type": "array", "items": {"type": "string"}, "description": "Networks, e.g. instagram, facebook, linkedin, twitter."},
                "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Public media URLs, optional."},
                "publish_at": {"type": "string", "description": "ISO datetime without timezone, e.g. 2026-06-08T09:00:00."},
                "timezone_name": {"type": "string", "description": "Timezone, default America/Toronto."},
                "info": {"type": "object", "description": "Advanced raw Metricool scheduler body. Optional."},
            },
            "required": ["text", "networks", "publish_at"],
        },
    },
    "metricool__update_scheduled_post": {
        "description": "[Metricool] WRITE: Update a scheduled post. Fetch scheduled posts first, show exactly what changes, then call; the system will require hold-to-confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "blog_id": {"type": "string", "description": "Optional Metricool brand/blog ID."},
                "post_id": {"type": "string", "description": "Scheduled post ID from get_scheduled_posts."},
                "changes": {"type": "object", "description": "Fields to change."},
                "info": {"type": "object", "description": "Full Metricool scheduler body when available."},
            },
            "required": ["post_id"],
        },
    },

    # ── Supabase (user projects) ──────────────────────────────────────────────
    "supabase_project__list_projects": {
        "description": "[Supabase] List the user's Supabase projects.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "supabase_project__get_project_keys": {
        "description": "[Supabase] Get API keys for a Supabase project (truncated for security — full keys visible in dashboard).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Supabase project ID (from list_projects)"},
            },
            "required": ["project_id"],
        },
    },
    "supabase_project__run_sql": {
        "description": "[Supabase] Run SQL on a Supabase project — create tables, insert data, alter schema. Confirm with user before running schema changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Supabase project ID (from list_projects)"},
                "sql": {"type": "string", "description": "SQL query to execute"},
            },
            "required": ["project_id", "sql"],
        },
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
