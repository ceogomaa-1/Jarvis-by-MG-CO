"""
Build Anthropic tool definitions from the user's active connector connections.
Only includes tools for connectors the user has actually connected (status=active).
Returns [] if nothing is connected — never pass an empty list to Anthropic (omit the param instead).
"""
from backend.lib.business.connectors.registry import list_user_connections
from backend.lib.business.real_estate.profile import is_real_estate_user
from backend.lib.business.real_estate.tools import REAL_ESTATE_TOOLS
from backend.lib.business.twenty.client import TwentyClient

# ─────────────────────────────────────────────────────────────────────────────
# Static tool registry: tool_name → {description, input_schema}
# Tool names use connector_type__action_name (double underscore).
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Always-on tools: available to every user regardless of connected connectors.
# ─────────────────────────────────────────────────────────────────────────────
_ALWAYS_ON_TOOLS: dict[str, dict] = {
    "web__search": {
        "description": (
            "Search the web for current or real-time information — news, sports scores/schedules, "
            "prices, weather, facts, and people/business lookups. Returns numbered results; cite them "
            "inline as [1], [2]. Use this whenever the user asks about anything you don't already know "
            "or that is time-sensitive — never refuse a general question by claiming you can't search. "
            "Follow up with web__fetch_url on the most relevant result when you need the full details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query. Keep it short and specific, 2-6 words."},
            },
            "required": ["query"],
        },
    },
    "web__fetch_url": {
        "description": (
            "Fetch and read the full text content of a specific URL (a link from web__search results or "
            "one the user mentioned). Use for a fast read of a single page. For JavaScript-heavy sites "
            "(Wix, Squarespace, etc.) or to auto-discover a homepage's sub-pages and linked PDFs, use "
            "web__scrape_website instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL to fetch (must start with http:// or https://)"},
            },
            "required": ["url"],
        },
    },
    "web__scrape_website": {
        "description": (
            "Fetch and read the full content of a URL. Renders JavaScript-heavy pages "
            "(Wix, Squarespace, etc.) with a headless browser, falls back to a fast static "
            "fetch, and extracts text from linked PDFs (e.g. menu or brochure PDFs). Use this "
            "whenever the user gives you a website to read, research, or build something from "
            "(e.g. building an ElevenLabs voice agent for a business). Set max_pages to 5 when "
            "building a full client profile from a homepage — it auto-discovers and reads key "
            "sub-pages (menu, about, contact, location, hours) and any linked PDFs from the same site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL to fetch (must start with http:// or https://)"},
                "max_pages": {
                    "type": "integer",
                    "description": "How many pages to read in total, including the given URL (1-5). Use 5 when building a client profile from a homepage so menu/about/contact/hours pages and linked PDFs are auto-discovered. Default 1.",
                    "default": 1,
                },
            },
            "required": ["url"],
        },
    },
}

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
    "stripe__create_subscription_tier": {
        "description": (
            "[Stripe] WRITE: Create a real subscription pricing tier on Stripe — a Product plus a "
            "recurring Price in one step (e.g. 'Pro at $249/mo'). Use this for setting up pricing "
            "tiers / plans. amount_cents is in cents ($249 = 24900). First show the user the exact "
            "tiers, amounts, and billing interval and let the system require hold-to-confirm; then "
            "report the REAL prod_…/price_… IDs the tool returns. Never invent IDs or claim it was "
            "created without a successful result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tier / product name, e.g. 'Pro' or 'Operator'"},
                "amount_cents": {"type": "integer", "description": "Price in cents ($249/mo = 24900)"},
                "interval": {"type": "string", "enum": ["day", "week", "month", "year"], "description": "Billing interval (default month)"},
                "currency": {"type": "string", "description": "3-letter currency code (default usd)"},
                "description": {"type": "string", "description": "Optional product description"},
            },
            "required": ["name", "amount_cents"],
        },
    },
    "stripe__create_product": {
        "description": (
            "[Stripe] WRITE: Create a single Stripe Product (no price). Prefer create_subscription_tier "
            "when you also need a recurring price. Confirm with the user first; report the real prod_… id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name"},
                "description": {"type": "string", "description": "Optional product description"},
            },
            "required": ["name"],
        },
    },
    "stripe__create_price": {
        "description": (
            "[Stripe] WRITE: Create a Price for an existing Stripe product. unit_amount is in cents. "
            "Pass interval for a recurring/subscription price; omit it for a one-time price. Confirm "
            "first; report the real price_… id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Existing Stripe product id (prod_…)"},
                "unit_amount": {"type": "integer", "description": "Amount in cents ($10 = 1000)"},
                "currency": {"type": "string", "description": "3-letter currency code (default usd)"},
                "interval": {"type": "string", "enum": ["day", "week", "month", "year"], "description": "Recurring interval; omit for one-time price"},
                "nickname": {"type": "string", "description": "Optional price nickname"},
            },
            "required": ["product_id", "unit_amount"],
        },
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
        "description": "[Google Calendar] Create a new event on the primary calendar. If start/end omit timeZone, it defaults to America/Toronto.",
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
                            "description": "Start time as {dateTime: ISO8601, timeZone: 'America/Toronto'}. timeZone defaults to America/Toronto if omitted.",
                        },
                        "end": {
                            "type": "object",
                            "description": "End time as {dateTime: ISO8601, timeZone: 'America/Toronto'}. timeZone defaults to America/Toronto if omitted.",
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
        "description": "[Google Calendar] Update an existing calendar event (title, time, description, location). Confirm with user before calling. If start/end omit timeZone, it defaults to America/Toronto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID from list_calendar_events"},
                "summary": {"type": "string", "description": "New event title (optional)"},
                "description": {"type": "string", "description": "New description (optional)"},
                "start": {"type": "object", "description": "New start: {dateTime: ISO8601, timeZone: string} (optional). timeZone defaults to America/Toronto if omitted."},
                "end": {"type": "object", "description": "New end: {dateTime: ISO8601, timeZone: string} (optional). timeZone defaults to America/Toronto if omitted."},
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
    "google__freebusy": {
        "description": "[Google Calendar] Check free/busy blocks across one or more calendars in a time range. Use before proposing a meeting/showing time to avoid double-booking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "Start of range, ISO 8601 (e.g. 2026-06-15T00:00:00-04:00)"},
                "time_max": {"type": "string", "description": "End of range, ISO 8601"},
                "calendar_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Calendar IDs to check (default: ['primary'])",
                },
            },
            "required": ["time_min", "time_max"],
        },
    },
    "google__find_free_slot": {
        "description": "[Google Calendar] Find the next free slot of a given duration within working hours (default 9am-5pm Mon-Fri, America/Toronto), checking the primary calendar's free/busy. Use this to propose a showing/meeting time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_min": {"type": "integer", "description": "Desired meeting/showing length in minutes"},
                "time_min": {"type": "string", "description": "Earliest time to consider, ISO 8601 (optional, default now)"},
                "time_max": {"type": "string", "description": "Latest time to consider, ISO 8601 (optional, default 7 days after time_min)"},
                "work_start_hour": {"type": "integer", "description": "Working day start hour, 24h (default 9)"},
                "work_end_hour": {"type": "integer", "description": "Working day end hour, 24h (default 17)"},
                "timezone": {"type": "string", "description": "Timezone name (default America/Toronto)"},
            },
            "required": ["duration_min"],
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
    "google__prioritize_emails": {
        "description": (
            "[Gmail] Fetch recent emails (sender, subject, date, snippet, read/unread status) so YOU can "
            "triage and prioritize them for the user — e.g. 'these 3 need a reply today, these are FYI, "
            "this looks like spam.' Defaults to unread mail. This tool only fetches the metadata; the "
            "prioritization and reasoning is yours to do in your response, not the tool's."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Max emails to fetch (default 20)"},
                "query": {"type": "string", "description": "Gmail search query (default 'is:unread')"},
            },
            "required": [],
        },
    },
    "google__get_message": {
        "description": "[Gmail] Get the full content (body, headers, labels, read/unread) of a single email by message ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID (from list_emails or prioritize_emails)"},
            },
            "required": ["message_id"],
        },
    },
    "google__modify_labels": {
        "description": "[Gmail] Add or remove Gmail labels on a message — e.g. archive by removing 'INBOX', star with 'STARRED', mark read/unread via 'UNREAD'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
                "add_labels": {"type": "array", "items": {"type": "string"}, "description": "Label IDs to add (optional)"},
                "remove_labels": {"type": "array", "items": {"type": "string"}, "description": "Label IDs to remove (optional)"},
            },
            "required": ["message_id"],
        },
    },
    "google__mark_read": {
        "description": "[Gmail] Mark a message as read or unread.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
                "read": {"type": "boolean", "description": "True to mark read, false to mark unread (default true)"},
            },
            "required": ["message_id"],
        },
    },
    "google__send_email": {
        "description": (
            "[Gmail] Send an email via Gmail, optionally with attachments. To attach a file (one Jarvis "
            "generated or the user uploaded), pass its doc_id from the conversation context. NOTE: Gmail's "
            "consumer API has no read-receipt support — never promise the user a read receipt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "cc": {"type": "string", "description": "CC email address(es), comma-separated (optional)"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
                "attachments": {
                    "type": "array",
                    "description": "Files to attach, each referencing a doc_id from the conversation (optional)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string", "description": "Document ID from conversation context"},
                            "filename": {"type": "string", "description": "Override filename (optional)"},
                        },
                        "required": ["doc_id"],
                    },
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    "google__create_draft": {
        "description": "[Gmail] Create a draft email in Gmail (not sent) for the user to review/edit before sending. Supports attachments via doc_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "cc": {"type": "string", "description": "CC email address(es), comma-separated (optional)"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
                "attachments": {
                    "type": "array",
                    "description": "Files to attach, each referencing a doc_id from the conversation (optional)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string", "description": "Document ID from conversation context"},
                            "filename": {"type": "string", "description": "Override filename (optional)"},
                        },
                        "required": ["doc_id"],
                    },
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    "google__list_drafts": {
        "description": "[Gmail] List existing Gmail drafts (to, subject, date, snippet).",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Max drafts to return (default 10)"},
            },
            "required": [],
        },
    },
    "google__get_draft": {
        "description": "[Gmail] Get the full content (to, cc, subject, body) of a Gmail draft by draft ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "Draft ID from list_drafts"},
            },
            "required": ["draft_id"],
        },
    },
    "google__schedule_email": {
        "description": (
            "[Gmail] Schedule an email to be sent automatically at a future time. Gmail's API has no "
            "native schedule-send, so Jarvis stores this and a background dispatcher (checked roughly "
            "every minute) sends it through the user's connected Gmail account once send_at passes — "
            "marked 'sent' only on a real success from Gmail, 'failed' with the real error otherwise. "
            "Supports attachments via doc_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "cc": {"type": "string", "description": "CC email address(es), comma-separated (optional)"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
                "send_at": {
                    "type": "string",
                    "description": "When to send, ISO 8601 with timezone offset (e.g. 2026-06-15T09:00:00-04:00 for America/Toronto)",
                },
                "attachments": {
                    "type": "array",
                    "description": "Files to attach, each referencing a doc_id from the conversation (optional)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string", "description": "Document ID from conversation context"},
                            "filename": {"type": "string", "description": "Override filename (optional)"},
                        },
                        "required": ["doc_id"],
                    },
                },
            },
            "required": ["to", "subject", "body", "send_at"],
        },
    },
    "google__list_scheduled_emails": {
        "description": "[Gmail] List the user's scheduled emails and their status (pending, sent, failed, cancelled).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "sent", "failed", "cancelled"],
                    "description": "Filter by status (optional — default returns all)",
                },
            },
            "required": [],
        },
    },
    "google__cancel_scheduled_email": {
        "description": "[Gmail] Cancel a pending scheduled email before it sends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Scheduled email ID from list_scheduled_emails"},
            },
            "required": ["id"],
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

    # ── Buffer ───────────────────────────────────────────────────────────────
    "buffer__list_organizations": {
        "description": "[Buffer] List Buffer organizations available to the connected API key. Use this to find organization IDs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "buffer__list_channels": {
        "description": "[Buffer] List connected social channels/profiles for an organization. Use this before scheduling so you know the channel IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "organization_id": {"type": "string", "description": "Optional Buffer organization ID. Defaults to saved organization_id."},
            },
            "required": [],
        },
    },
    "buffer__get_channel": {
        "description": "[Buffer] Get details for a single Buffer social channel/profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Buffer channel/profile ID."},
            },
            "required": ["channel_id"],
        },
    },
    "buffer__get_scheduled_posts": {
        "description": "[Buffer] List scheduled/queued posts for selected channel IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "organization_id": {"type": "string", "description": "Optional Buffer organization ID. Defaults to saved organization_id."},
                "channel_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional Buffer channel IDs to filter by."},
                "limit": {"type": "integer", "description": "Max posts, default 20."},
            },
            "required": [],
        },
    },
    "buffer__get_sent_posts": {
        "description": "[Buffer] List recently sent/published posts for selected channel IDs. Use for lightweight content review; do not fabricate unavailable analytics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "organization_id": {"type": "string", "description": "Optional Buffer organization ID. Defaults to saved organization_id."},
                "channel_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional Buffer channel IDs to filter by."},
                "limit": {"type": "integer", "description": "Max posts, default 20."},
            },
            "required": [],
        },
    },
    "buffer__create_post": {
        "description": "[Buffer] WRITE: Create a Buffer post. Use mode addToQueue for queue publishing or customScheduled with publish_at for a fixed time. Show exact text, channel IDs, media, and time first; the system will require hold-to-confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Post caption/text."},
                "channel_ids": {"type": "array", "items": {"type": "string"}, "description": "Buffer channel IDs to publish to."},
                "mode": {"type": "string", "description": "Buffer posting mode: addToQueue or customScheduled."},
                "publish_at": {"type": "string", "description": "ISO datetime for customScheduled mode, e.g. 2026-06-08T09:00:00Z."},
                "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Public media URLs, optional."},
                "networks": {"type": "array", "items": {"type": "string"}, "description": "Optional human labels for validation/confirmation, e.g. instagram, linkedin, x."},
            },
            "required": ["text", "channel_ids"],
        },
    },
    "buffer__schedule_post": {
        "description": "[Buffer] WRITE: Schedule a post at an exact publish time. Show exact text, channel IDs, media, and publish time first; the system will require hold-to-confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Post caption/text."},
                "channel_ids": {"type": "array", "items": {"type": "string"}, "description": "Buffer channel IDs to publish to."},
                "publish_at": {"type": "string", "description": "ISO datetime, e.g. 2026-06-08T09:00:00Z."},
                "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Public media URLs, optional."},
                "networks": {"type": "array", "items": {"type": "string"}, "description": "Optional human labels for validation/confirmation, e.g. instagram, linkedin, x."},
            },
            "required": ["text", "channel_ids", "publish_at"],
        },
    },
    "buffer__add_to_queue": {
        "description": "[Buffer] WRITE: Add a post to the next available slot in the Buffer queue. Show exact text, channel IDs, and media first; the system will require hold-to-confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Post caption/text."},
                "channel_ids": {"type": "array", "items": {"type": "string"}, "description": "Buffer channel IDs to publish to."},
                "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Public media URLs, optional."},
                "networks": {"type": "array", "items": {"type": "string"}, "description": "Optional human labels for validation/confirmation, e.g. instagram, linkedin, x."},
            },
            "required": ["text", "channel_ids"],
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

# ─────────────────────────────────────────────────────────────────────────────
# Jarvis-owned CRM (self-hosted Twenty). Env-gated: only offered when
# TWENTY_API_URL + TWENTY_API_KEY are set. Read-only over the imported data.
# Dispatched specially in tool_executor (connector_type == "twenty").
# ─────────────────────────────────────────────────────────────────────────────
TWENTY_TOOLS: dict[str, dict] = {
    "twenty__list_people": {
        "description": "[Owned CRM] List People (contacts) in Jarvis's own CRM (the imported GoHighLevel data lives here). Returns name + email. Use for 'who's in my CRM' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max people to return (default 25)"}},
            "required": [],
        },
    },
    "twenty__search_people": {
        "description": "[Owned CRM] Search People in Jarvis's own CRM by name or email substring. Returns matching name + email + id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name or email text to match"},
                "limit": {"type": "integer", "description": "Max results (default 25)"},
            },
            "required": ["query"],
        },
    },
    "twenty__list_opportunities": {
        "description": "[Owned CRM] List Opportunities (deals) in Jarvis's own CRM, optionally filtered to a pipeline stage by its GHL stage name. Returns deal names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Optional pipeline stage name (as it was in GoHighLevel) to filter by"},
                "limit": {"type": "integer", "description": "Max opportunities to return (default 50)"},
            },
            "required": [],
        },
    },
    "twenty__count_opportunities_in_stage": {
        "description": "[Owned CRM] Count how many Opportunities are in a given pipeline stage in Jarvis's own CRM. Answers 'how many opps in <stage> in my CRM'. Pass the stage name as it was in GoHighLevel.",
        "input_schema": {
            "type": "object",
            "properties": {"stage": {"type": "string", "description": "Pipeline stage name to count"}},
            "required": ["stage"],
        },
    },
    "twenty__person_notes_tasks": {
        "description": "[Owned CRM] Look up one person in Jarvis's own CRM by name/email and return their notes and tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Name or email of the person"}},
            "required": ["query"],
        },
    },
}

# WRITE tools (Phase 3) — Jarvis can modify the owned CRM. Same gating as reads
# (only when the user's workspace is provisioned). Writes go to Twenty ONLY, never
# GHL. delete_* are intercepted by chat.py WRITE_ACTIONS for hold-to-confirm.
TWENTY_WRITE_TOOLS: dict[str, dict] = {
    "twenty__create_person": {
        "description": "[Owned CRM WRITE] Create a contact (Person) in Jarvis's own CRM. Idempotent on email — if a contact with that email exists it is returned, not duplicated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "city": {"type": "string"},
                "job_title": {"type": "string"},
            },
            "required": [],
        },
    },
    "twenty__update_person": {
        "description": "[Owned CRM WRITE] Update a contact. Identify by person_id, or by `query` (name/email). Only the fields you pass are changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "person_id": {"type": "string"},
                "query": {"type": "string", "description": "Name/email to find the contact if no person_id"},
                "first_name": {"type": "string"}, "last_name": {"type": "string"},
                "email": {"type": "string"}, "phone": {"type": "string"},
                "city": {"type": "string"}, "job_title": {"type": "string"},
            },
            "required": [],
        },
    },
    "twenty__create_opportunity": {
        "description": "[Owned CRM WRITE] Create an Opportunity (deal). Optionally set a pipeline stage (by its GHL stage name), an amount, and link a contact via person_query/person_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "amount": {"type": "number", "description": "Deal value in the major currency unit (e.g. 5000 for $5,000)"},
                "currency": {"type": "string", "description": "ISO code, default USD"},
                "stage": {"type": "string", "description": "Pipeline stage name (as in GoHighLevel)"},
                "person_query": {"type": "string"}, "person_id": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    "twenty__update_opportunity": {
        "description": "[Owned CRM WRITE] Update an Opportunity's name or amount. Identify by opportunity_id or `query` (name).",
        "input_schema": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string"}, "query": {"type": "string"},
                "name": {"type": "string"}, "amount": {"type": "number"}, "currency": {"type": "string"},
            },
            "required": [],
        },
    },
    "twenty__move_opportunity_stage": {
        "description": "[Owned CRM WRITE] Move an Opportunity to a different pipeline stage. Identify the deal by opportunity_id or `query` (name); pass the target stage name (as in GoHighLevel).",
        "input_schema": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string"}, "query": {"type": "string"},
                "stage": {"type": "string"},
            },
            "required": ["stage"],
        },
    },
    "twenty__add_note": {
        "description": "[Owned CRM WRITE] Add a note to a contact. Identify the contact by person_id or `query` (name/email); pass the note `body`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "person_id": {"type": "string"}, "query": {"type": "string"},
                "title": {"type": "string"}, "body": {"type": "string"},
            },
            "required": ["body"],
        },
    },
    "twenty__add_task": {
        "description": "[Owned CRM WRITE] Create a task. Optionally attach it to a contact via person_query/person_id and set a due date (ISO 8601).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "body": {"type": "string"},
                "due_at": {"type": "string", "description": "ISO 8601 datetime"},
                "person_query": {"type": "string"}, "person_id": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    "twenty__complete_task": {
        "description": "[Owned CRM WRITE] Mark a task complete. Requires the task_id.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    "twenty__add_tag": {
        "description": "[Owned CRM WRITE] Add a tag to a contact (idempotent). Identify by person_id or `query`; pass `tag`.",
        "input_schema": {
            "type": "object",
            "properties": {"person_id": {"type": "string"}, "query": {"type": "string"}, "tag": {"type": "string"}},
            "required": ["tag"],
        },
    },
    "twenty__remove_tag": {
        "description": "[Owned CRM WRITE] Remove a tag from a contact (idempotent). Identify by person_id or `query`; pass `tag`.",
        "input_schema": {
            "type": "object",
            "properties": {"person_id": {"type": "string"}, "query": {"type": "string"}, "tag": {"type": "string"}},
            "required": ["tag"],
        },
    },
    "twenty__delete_person": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete a contact. Identify by person_id or `query`. Requires user confirmation (the system gates this with hold-to-confirm).",
        "input_schema": {
            "type": "object",
            "properties": {"person_id": {"type": "string"}, "query": {"type": "string"}},
            "required": [],
        },
    },
    "twenty__delete_opportunity": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete an Opportunity. Identify by opportunity_id or `query`. Requires user confirmation (hold-to-confirm).",
        "input_schema": {
            "type": "object",
            "properties": {"opportunity_id": {"type": "string"}, "query": {"type": "string"}},
            "required": [],
        },
    },
}

# Maps each tool name to its connector_type
_TOOL_TO_CONNECTOR: dict[str, str] = {k: k.split("__")[0] for k in _TOOLS}


async def build_tools_for_user(user_id: str) -> list[dict]:
    """
    Return Anthropic tool definitions: always-on tools (no connector required) plus
    tools for the user's active connector connections.
    """
    tools = [
        {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
        for name, defn in _ALWAYS_ON_TOOLS.items()
    ]

    if not user_id:
        return tools

    rows = await list_user_connections(user_id)
    active_types = {r["connector_type"] for r in rows if r.get("status") == "active"}

    tools += [
        {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
        for name, defn in _TOOLS.items()
        if _TOOL_TO_CONNECTOR[name] in active_types
    ]

    # Real Estate Operator Suite — available to RE-industry users regardless of
    # which connectors they've activated (each tool checks its own deps).
    if await is_real_estate_user(user_id):
        tools += [
            {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
            for name, defn in REAL_ESTATE_TOOLS.items()
        ]

    # Jarvis CRM (self-hosted Twenty). Offered when the user has their OWN
    # provisioned workspace (Phase 2) OR the server has a shared instance via
    # TWENTY_API_URL + TWENTY_API_KEY (Phase 1 fallback).
    if await TwentyClient.configured_for_user(user_id):
        tools += [
            {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
            for name, defn in {**TWENTY_TOOLS, **TWENTY_WRITE_TOOLS}.items()
        ]

    return tools
