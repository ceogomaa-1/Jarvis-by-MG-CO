"""
Build Anthropic tool definitions from the user's active connector connections.
Only includes tools for connectors the user has actually connected (status=active).
Returns [] if nothing is connected — never pass an empty list to Anthropic (omit the param instead).
"""
from backend.lib.business.connectors.registry import list_user_connections
from backend.lib.business.leads.config import leads_enabled
from backend.lib.business.leads.tools import LEADS_TOOLS
from backend.lib.business.real_estate.profile import is_real_estate_user
from backend.lib.business.real_estate.tools import REAL_ESTATE_TOOLS
from backend.lib.business.sales_advisor.config import enabled as sales_advisor_enabled
from backend.lib.business.sales_advisor.tools import SALES_TOOLS
from backend.lib.business.twenty.client import TwentyClient

# ─────────────────────────────────────────────────────────────────────────────
# Static tool registry: tool_name → {description, input_schema}
# Tool names use connector_type__action_name (double underscore).
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Always-on tools: available to every user regardless of connected connectors.
# ─────────────────────────────────────────────────────────────────────────────
_ALWAYS_ON_TOOLS: dict[str, dict] = {
    "dashboard__control": {
        "description": (
            "Create, edit, restyle, move, delete, or restore blocks on the user's Rue Home "
            "dashboard, and change its overall theme (colors/fonts). Use this WHENEVER the user asks "
            "to customize, redesign, add to, or change their Home / dashboard. Examples: 'create a "
            "block called My Expenses I can add items to' -> create_block block_type='list'; 'make a "
            "bar chart of my monthly revenue' -> create_block block_type='chart' chart_kind='bar' with "
            "items; 'add a notes block' -> create_block block_type='note'; 'pull today's industry news' "
            "-> create_block block_type='news' news_topic=...; 'add coffee $4 to my expenses' -> "
            "add_item; 'rent is due June 5th' / 'change rent to $1300' / 'rename coffee to lunch' -> "
            "update_item (match the existing item by id or by its current label); 'change the accent "
            "color to emerald' / 'use a serif font' -> set_theme; 'delete "
            "the expenses block' -> delete_block; 'undo' -> restore; 'move my expenses to the top' -> "
            "move_block. Operate on REAL data the user gives you or that you pull live — never invent "
            "numbers. block_id comes from a previous create_block or the dashboard context. After "
            "calling, confirm what changed in one short sentence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [
                    "create_block", "update_block", "add_item", "remove_item", "update_item",
                    "restyle_block", "move_block", "delete_block", "restore", "set_theme"]},
                "block_type": {"type": "string", "enum": ["list", "note", "metric", "chart", "news"],
                               "description": "For create_block."},
                "block_id": {"type": "string", "description": "Target custom block id (update/add_item/remove_item/update_item/restyle/move/delete)."},
                "title": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"},
                          "description": "List/chart items, e.g. [{\"label\":\"Rent\",\"amount\":1200,\"due_date\":\"2026-07-05\"}] for a list, or chart points [{\"label\":\"Jan\",\"value\":30}]."},
                "item": {"type": "object", "description": "A single item. add_item: {\"label\":\"Coffee\",\"amount\":4,\"due_date\":\"2026-07-05\"} (due_date optional, list blocks only). remove_item: {\"id\":...} or {\"label\":...}. update_item: identify with {\"id\":...} (preferred) or {\"label\":\"<current label>\"}, then include only what's changing — \"new_label\" to rename, \"amount\" for a new amount, \"due_date\" for a new/changed due date (empty string clears it)."},
                "text": {"type": "string", "description": "Body text for a note block."},
                "metric": {"type": "object", "description": "For a metric block: {value, unit, label, delta}. Carries 'unit' for a list block (e.g. '$')."},
                "chart_kind": {"type": "string", "enum": ["bar", "line", "pie"]},
                "news_topic": {"type": "string", "description": "Topic to pull live headlines for a news block."},
                "theme": {"type": "object", "description": "Dashboard theme, any subset of {accent (hex or color name), font ('sans'|'serif'|'mono'), density ('cozy'|'compact'), background (hex)}."},
                "style": {"type": "object", "description": "Per-block style override, e.g. {accent}."},
                "position": {"type": "string", "enum": ["top", "bottom"]},
            },
            "required": ["action"],
        },
    },
    "website__create": {
        "description": (
            "Build a brand-new standalone website/landing page, or surgically edit the one you "
            "most recently built. Use this WHENEVER the user asks you to build, design, make, or "
            "change a website/page/site/landing page in plain conversation — never tell them to "
            "go ask separately or that you can't do it here. action='build' for a new page; "
            "action='edit' for a change to the page you just built (e.g. 'change the headline'). "
            "'brief' should restate exactly what to build or change, in your own words, with any "
            "details the user gave you. This only produces a previewable page — it is NEVER "
            "deployed automatically. If the user wants it live, tell them to say 'deploy it' "
            "(handled separately, outside this tool, and always asks for nothing more than that "
            "explicit confirmation)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["build", "edit"]},
                "brief": {"type": "string", "description": "What to build or change, in plain language, with the user's details folded in."},
            },
            "required": ["action", "brief"],
        },
    },
    "walkthrough__generate": {
        "description": (
            "Generate an illustrated, step-by-step walkthrough/tutorial for a how-to question. "
            "Use this when the user asks 'how do I...', 'show me how to...', or otherwise wants a "
            "guided tutorial with visuals — instead of just explaining the steps in plain text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What the walkthrough should teach, in plain language."},
            },
            "required": ["topic"],
        },
    },
    "pdf__create": {
        "description": (
            "Generate a downloadable PDF document from structured content — lead lists, call "
            "sheets, reports, summaries, proposals, checklists. Use this WHENEVER the user asks "
            "for a PDF or a downloadable/printable document — NEVER say you can't create PDFs, "
            "and don't detour to Notion or other tools unless the user asks for that. Gather the "
            "data FIRST (with other tools, in earlier rounds), then call this once with the "
            "COMPLETE content as ordered blocks: {type:'heading', text}, {type:'paragraph', text} "
            "(lines starting with '- ' become bullets), {type:'table', headers:[...], "
            "rows:[[...],...]}. Returns a download_url — always present it to the user as a "
            "markdown link. Runs immediately, no confirmation needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title (shown at the top of the PDF)"},
                "subtitle": {"type": "string", "description": "Optional subtitle shown under the title"},
                "blocks": {
                    "type": "array",
                    "description": (
                        "Ordered content blocks. heading: {\"type\":\"heading\",\"text\":...}; "
                        "paragraph: {\"type\":\"paragraph\",\"text\":...} ('- ' lines render as bullets); "
                        "table: {\"type\":\"table\",\"headers\":[\"Name\",\"Phone\"],\"rows\":[[\"Mario's Garage\",\"(416) 531-0875\"]]}"
                    ),
                    "items": {"type": "object"},
                },
                "filename": {"type": "string", "description": "Optional filename (without path); defaults to the title"},
                "note": {"type": "string", "description": "Optional small-print footer note"},
            },
            "required": ["title", "blocks"],
        },
    },
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
        "description": "[Notion] Create ONE page/row in a Notion database. `properties` may be a simple flat map of column name → plain value (recommended) or Notion's raw property format. For more than one row, use notion__create_pages instead — NEVER a chain of create_page calls (only the first write action of a turn executes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Parent database ID"},
                "properties": {"type": "object", "description": "Flat column→value map (e.g. {\"Name\": \"Mario's Garage\", \"Phone\": \"(416) 531-0875\"}) or raw Notion property objects"},
                "children": {
                    "type": "array",
                    "description": "Page content blocks (optional)",
                    "items": {"type": "object"},
                },
            },
            "required": ["database_id", "properties"],
        },
    },
    "notion__create_pages": {
        "description": "[Notion] Bulk-insert MANY rows into an EXISTING database in ONE confirmed action. Always use this (never repeated create_page calls) when adding 2+ rows — the chat turn ends at the first write action, so a planned series of single inserts will never run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Target database ID"},
                "rows": {
                    "type": "array",
                    "description": "All rows to insert. Each row is a FLAT object mapping column name → plain value, e.g. {\"Name\": \"Mario's Garage\", \"Score\": 80, \"Google Maps Link\": \"https://...\"}",
                    "items": {"type": "object"},
                },
            },
            "required": ["database_id", "rows"],
        },
    },
    "notion__list_pages": {
        "description": "[Notion] List top-level pages shared with the integration — use to find parent page IDs before creating a database.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "notion__create_database": {
        "description": "[Notion] Create a new database under a parent page AND insert its rows — all in ONE confirmed action. ALWAYS call list_pages first to find the parent. CRITICAL: if the user wants a list/table with data in it, you MUST pass every row via `rows` in THIS call. The chat turn ends at the first write action, so follow-up row-insert calls will never execute and the database would be left empty.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_page_id": {"type": "string", "description": "ID of the parent page (from list_pages)"},
                "title": {"type": "string", "description": "Name of the new database"},
                "rows": {
                    "type": "array",
                    "description": "The data rows to insert right after creation. Each row is a FLAT object mapping column name → plain value (e.g. {\"Name\": \"Mario's Garage\", \"Phone\": \"(416) 531-0875\", \"Score\": 80}). Column names must match `columns` (plus the default \"Name\" title column). Pass ALL rows here — do not plan separate inserts.",
                    "items": {"type": "object"},
                },
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
            "[Gmail] Send an email via Gmail, optionally with attachments. To attach a file (one Rue "
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
            "native schedule-send, so Rue stores this and a background dispatcher (checked roughly "
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
                "message": {"type": "string", "description": "Commit message", "default": "Update project files"},
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
# Rue-owned CRM (self-hosted Twenty). Env-gated: only offered when
# TWENTY_API_URL + TWENTY_API_KEY are set. Read-only over the imported data.
# Dispatched specially in tool_executor (connector_type == "twenty").
# ─────────────────────────────────────────────────────────────────────────────
TWENTY_TOOLS: dict[str, dict] = {
    "twenty__list_people": {
        "description": "[Owned CRM] List People (contacts) in Rue's own CRM (the imported GoHighLevel data lives here). Returns name + email. Use for 'who's in my CRM' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max people to return (default 25)"}},
            "required": [],
        },
    },
    "twenty__search_people": {
        "description": "[Owned CRM] Search People in Rue's own CRM by name or email substring. Returns matching name + email + id.",
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
        "description": "[Owned CRM] List Opportunities (deals) in Rue's own CRM, optionally filtered to a pipeline stage by its GHL stage name. Returns deal names.",
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
        "description": "[Owned CRM] Count how many Opportunities are in a given pipeline stage in Rue's own CRM. Answers 'how many opps in <stage> in my CRM'. Pass the stage name as it was in GoHighLevel.",
        "input_schema": {
            "type": "object",
            "properties": {"stage": {"type": "string", "description": "Pipeline stage name to count"}},
            "required": ["stage"],
        },
    },
    "twenty__person_notes_tasks": {
        "description": "[Owned CRM] Look up one person in Rue's own CRM by name/email and return their notes and tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Name or email of the person"}},
            "required": ["query"],
        },
    },
    "twenty__list_companies": {
        "description": "[Owned CRM] List Companies in Rue's own CRM. Returns name + id.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max companies (default 25)"}},
            "required": [],
        },
    },
    "twenty__search_companies": {
        "description": "[Owned CRM] Search Companies by name substring. Returns matching name + id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Company name text to match"},
                "limit": {"type": "integer", "description": "Max results (default 25)"},
            },
            "required": ["query"],
        },
    },
    "twenty__read_fields": {
        "description": (
            "[Owned CRM] Read field VALUES back for one record (verify a write, or inspect "
            "custom fields). object_type = company|person|opportunity; identify by `query` or "
            "{type}_id. `fields` lists which fields (names/labels) to read; default = all custom "
            "fields. Select values come back as labels; link fields as the URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "object_type": {"type": "string"},
                "query": {"type": "string"},
                "company_id": {"type": "string"}, "person_id": {"type": "string"}, "opportunity_id": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
    },
}

# WRITE tools (Phase 3) — full CRUD over the owned CRM. Same gating as reads (only
# when the user's workspace is provisioned). Writes go to Twenty ONLY, never GHL.
# Destructive tools (TWENTY_DESTRUCTIVE_TOOLS) are intercepted by chat.py WRITE_ACTIONS
# for hold-to-confirm before executing.
_P = {"person_id": {"type": "string"}, "company_id": {"type": "string"}, "opportunity_id": {"type": "string"},
      "person_query": {"type": "string"}, "company_query": {"type": "string"}, "opportunity_query": {"type": "string"}}

# Generic custom-field setter, accepted by every create/update/bulk tool. Resolves field
# names/labels + types from the LIVE schema, so any field the user adds is instantly writable.
_FIELDS_PARAM = {
    "type": "object",
    "description": (
        "Set ANY field(s) by field name OR label → value — including custom fields (text, "
        "number, date, link, select, multi-select). For select/multi-select pass the human "
        "option LABEL (e.g. 'To Be Called') and it's mapped to the stored option key "
        "automatically. For a link field pass the URL string. Pass null to clear a field. "
        "Example: {\"Status\": \"To Be Called\", \"Google Maps Link\": \"https://maps.app.goo.gl/x\"}."
    ),
}

TWENTY_WRITE_TOOLS: dict[str, dict] = {
    # ── People ──
    "twenty__create_person": {
        "description": "[Owned CRM WRITE] Create a contact (Person). Idempotent on email. Optionally link to a company via company_query/company_id. Set custom fields via `fields`.",
        "input_schema": {"type": "object", "properties": {
            "first_name": {"type": "string"}, "last_name": {"type": "string"}, "email": {"type": "string"},
            "phone": {"type": "string"}, "city": {"type": "string"}, "job_title": {"type": "string"},
            "company_query": {"type": "string"}, "company_id": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": []},
    },
    "twenty__update_person": {
        "description": "[Owned CRM WRITE] Update a contact. Identify by person_id or `query` (name/email). Set built-in or custom fields (use `fields` for custom/select/link). Only passed fields change.",
        "input_schema": {"type": "object", "properties": {
            "person_id": {"type": "string"}, "query": {"type": "string"},
            "first_name": {"type": "string"}, "last_name": {"type": "string"}, "email": {"type": "string"},
            "phone": {"type": "string"}, "city": {"type": "string"}, "job_title": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": []},
    },
    "twenty__delete_person": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete a contact. Identify by person_id or `query`. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"person_id": {"type": "string"}, "query": {"type": "string"}}, "required": []},
    },
    # ── Companies ──
    "twenty__create_company": {
        "description": "[Owned CRM WRITE] Create a Company. Idempotent on name. Optional domain, city. Set custom fields via `fields`.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"}, "domain": {"type": "string"}, "city": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": ["name"]},
    },
    "twenty__update_company": {
        "description": "[Owned CRM WRITE] Update a Company. Identify by company_id or `query`. Set name/domain or ANY custom field via `fields` (e.g. {\"Status\":\"To Be Called\",\"Google Maps Link\":\"https://…\"}). Select options are given by label.",
        "input_schema": {"type": "object", "properties": {
            "company_id": {"type": "string"}, "query": {"type": "string"}, "name": {"type": "string"}, "domain": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": []},
    },
    "twenty__delete_company": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete a Company. Identify by company_id or `query`. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"company_id": {"type": "string"}, "query": {"type": "string"}}, "required": []},
    },
    # ── Opportunities ──
    "twenty__create_opportunity": {
        "description": "[Owned CRM WRITE] Create an Opportunity. Optional stage (GHL or native name), amount, links via person_query/company_query, and custom fields via `fields`.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"}, "amount": {"type": "number"}, "currency": {"type": "string"}, "stage": {"type": "string"},
            "person_query": {"type": "string"}, "person_id": {"type": "string"},
            "company_query": {"type": "string"}, "company_id": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": ["name"]},
    },
    "twenty__update_opportunity": {
        "description": "[Owned CRM WRITE] Update an Opportunity. Identify by opportunity_id or `query`. Set name/amount or ANY custom field via `fields`.",
        "input_schema": {"type": "object", "properties": {
            "opportunity_id": {"type": "string"}, "query": {"type": "string"}, "name": {"type": "string"},
            "amount": {"type": "number"}, "currency": {"type": "string"}, "fields": _FIELDS_PARAM}, "required": []},
    },
    "twenty__move_opportunity_stage": {
        "description": "[Owned CRM WRITE] Move an Opportunity to a different pipeline stage (by name). Identify by opportunity_id or `query`.",
        "input_schema": {"type": "object", "properties": {
            "opportunity_id": {"type": "string"}, "query": {"type": "string"}, "stage": {"type": "string"}}, "required": ["stage"]},
    },
    "twenty__delete_opportunity": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete an Opportunity. Identify by opportunity_id or `query`. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"opportunity_id": {"type": "string"}, "query": {"type": "string"}}, "required": []},
    },
    # ── Tasks ──
    "twenty__create_task": {
        "description": "[Owned CRM WRITE] Create a task. Optionally assign to a person/company/opportunity (via *_query/*_id) and set due_at (ISO 8601).",
        "input_schema": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "due_at": {"type": "string"}, **_P}, "required": ["title"]},
    },
    "twenty__update_task": {
        "description": "[Owned CRM WRITE] Update a task (title/body/due_at/status). Requires task_id.",
        "input_schema": {"type": "object", "properties": {
            "task_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"},
            "due_at": {"type": "string"}, "status": {"type": "string", "description": "TODO | IN_PROGRESS | DONE"}}, "required": ["task_id"]},
    },
    "twenty__complete_task": {
        "description": "[Owned CRM WRITE] Mark a task complete. Requires task_id.",
        "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
    },
    "twenty__delete_task": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete a task. Requires task_id. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
    },
    # ── Notes ──
    "twenty__add_note": {
        "description": "[Owned CRM WRITE] Create a note and attach it to a person/company/opportunity (via *_query/*_id).",
        "input_schema": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, **_P}, "required": ["body"]},
    },
    "twenty__update_note": {
        "description": "[Owned CRM WRITE] Update a note's title/body. Requires note_id.",
        "input_schema": {"type": "object", "properties": {
            "note_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["note_id"]},
    },
    "twenty__delete_note": {
        "description": "[Owned CRM WRITE — DESTRUCTIVE] Delete a note. Requires note_id. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"note_id": {"type": "string"}}, "required": ["note_id"]},
    },
    # ── Tags ──
    "twenty__add_tag": {
        "description": "[Owned CRM WRITE] Add a tag to a record (idempotent). object_type = person|company|opportunity; identify by *_id or `query`.",
        "input_schema": {"type": "object", "properties": {
            "object_type": {"type": "string"}, "person_id": {"type": "string"}, "company_id": {"type": "string"},
            "opportunity_id": {"type": "string"}, "query": {"type": "string"}, "tag": {"type": "string"}}, "required": ["tag"]},
    },
    "twenty__remove_tag": {
        "description": "[Owned CRM WRITE] Remove a tag from a record (idempotent). object_type = person|company|opportunity; identify by *_id or `query`.",
        "input_schema": {"type": "object", "properties": {
            "object_type": {"type": "string"}, "person_id": {"type": "string"}, "company_id": {"type": "string"},
            "opportunity_id": {"type": "string"}, "query": {"type": "string"}, "tag": {"type": "string"}}, "required": ["tag"]},
    },
    # ── Relationships ──
    "twenty__link_records": {
        "description": "[Owned CRM WRITE] Link two records: person↔company, opportunity↔company, or opportunity↔person. Give from_type/to_type plus from_query/to_query (or *_id).",
        "input_schema": {"type": "object", "properties": {
            "from_type": {"type": "string"}, "to_type": {"type": "string"},
            "from_query": {"type": "string"}, "to_query": {"type": "string"},
            "from_id": {"type": "string"}, "to_id": {"type": "string"}}, "required": ["from_type", "to_type"]},
    },
    # ── Bulk + generic-field writes (confirm-gated) ──
    "twenty__bulk_update": {
        "description": (
            "[Owned CRM WRITE — BULK] Set the SAME field(s) across MANY records in one shot "
            "(reliable bulk path — use this instead of many single updates). object_type = "
            "company|person|opportunity. Select with names[] (matched against records), ids[], "
            "and/or all=true. `fields` sets any built-in or custom field (select by label). "
            "Requires hold-to-confirm. Example: object_type=company, names=[...19 names...], "
            "fields={\"Status\":\"To Be Called\"}."
        ),
        "input_schema": {"type": "object", "properties": {
            "object_type": {"type": "string"}, "names": {"type": "array", "items": {"type": "string"}},
            "ids": {"type": "array", "items": {"type": "string"}}, "all": {"type": "boolean"},
            "fields": _FIELDS_PARAM}, "required": ["fields"]},
    },
    "twenty__rehome_field": {
        "description": (
            "[Owned CRM WRITE — BULK] Move a field's values into another field across records "
            "(one-shot data fix). e.g. move Google Maps URLs wrongly stored in `domainName` into "
            "the 'Google Maps Link' field: object_type=company, from_field='domainName', "
            "to_field='Google Maps Link', contains='maps' (optional URL filter). Clears the "
            "source unless clear_source=false. Optional names[] to limit scope. Hold-to-confirm."
        ),
        "input_schema": {"type": "object", "properties": {
            "object_type": {"type": "string"}, "from_field": {"type": "string"}, "to_field": {"type": "string"},
            "contains": {"type": "string"}, "clear_source": {"type": "boolean"},
            "names": {"type": "array", "items": {"type": "string"}}}, "required": ["to_field"]},
    },
    # ── Advanced escape hatch (confirm-gated) ──
    "twenty__run_graphql_mutation": {
        "description": "[Owned CRM WRITE — ADVANCED] Run a raw Twenty GraphQL mutation for rare ops the structured tools don't cover. Prefer the structured tools. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {
            "mutation": {"type": "string", "description": "A GraphQL mutation string"},
            "variables": {"type": "object", "description": "Variables for the mutation"}}, "required": ["mutation"]},
    },
}

# Deletes + the raw-GraphQL escape hatch require hold-to-confirm (chat.py WRITE_ACTIONS).
TWENTY_DESTRUCTIVE_TOOLS = frozenset({
    "twenty__delete_person", "twenty__delete_company", "twenty__delete_opportunity",
    "twenty__delete_task", "twenty__delete_note", "twenty__run_graphql_mutation",
})

# Bulk writes (touch many records at once) — not destructive, but require hold-to-confirm
# so a mistaken mass-edit can't land silently. Added to chat.py WRITE_ACTIONS.
TWENTY_BULK_TOOLS = frozenset({"twenty__bulk_update", "twenty__rehome_field"})

# METADATA tools (structure-level) — let Rue reshape the CRM: custom fields,
# custom objects ("types"), and views/lists. Gated like other CRM tools; resolved
# per-user. Structural deletes are confirm-gated via chat.py.
TWENTY_METADATA_TOOLS: dict[str, dict] = {
    "twenty__list_objects": {
        "description": "[Owned CRM STRUCTURE] List the CRM's objects/types and their fields. Use this to see the current structure before changing it. Pass custom_only=true for just custom types.",
        "input_schema": {"type": "object", "properties": {"custom_only": {"type": "boolean"}}, "required": []},
    },
    "twenty__list_views": {
        "description": "[Owned CRM STRUCTURE] List the saved views/lists, optionally for one object.",
        "input_schema": {"type": "object", "properties": {"object": {"type": "string"}}, "required": []},
    },
    "twenty__create_field": {
        "description": "[Owned CRM STRUCTURE] Add a custom field to an object. field_type: text, number, currency, date, boolean, select, multi-select, phone, email, link. For select/multi-select pass options (array of strings).",
        "input_schema": {"type": "object", "properties": {
            "object": {"type": "string", "description": "Object name, e.g. People, Companies, Opportunities"},
            "name": {"type": "string", "description": "Field label, e.g. Budget"},
            "field_type": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "Choices for select/multi-select"}},
            "required": ["object", "name", "field_type"]},
    },
    "twenty__update_field": {
        "description": "[Owned CRM STRUCTURE] Update a custom field: rename (new_label), change select options, or activate/deactivate (is_active).",
        "input_schema": {"type": "object", "properties": {
            "object": {"type": "string"}, "field": {"type": "string"},
            "new_label": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
            "is_active": {"type": "boolean"}}, "required": ["object", "field"]},
    },
    "twenty__delete_field": {
        "description": "[Owned CRM STRUCTURE — DESTRUCTIVE] Delete a custom field from an object. Requires hold-to-confirm. Standard fields can't be deleted.",
        "input_schema": {"type": "object", "properties": {"object": {"type": "string"}, "field": {"type": "string"}}, "required": ["object", "field"]},
    },
    "twenty__create_object": {
        "description": "[Owned CRM STRUCTURE] Create a new object/type (e.g. Properties) with optional initial fields. fields = array of {name, type, options?}. type values as in create_field.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Type name, e.g. Properties"},
            "name_singular": {"type": "string"}, "name_plural": {"type": "string"}, "icon": {"type": "string"},
            "fields": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "type": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}}}}}},
            "required": ["name"]},
    },
    "twenty__delete_object": {
        "description": "[Owned CRM STRUCTURE — DESTRUCTIVE] Delete a custom object/type and all its records. Requires hold-to-confirm. Standard objects can't be deleted.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    "twenty__create_view": {
        "description": "[Owned CRM STRUCTURE] Create a custom list/view on an object. view_type: table or kanban. Optional sort_by (field) + sort_direction (asc/desc), group_by (kanban grouping field), and columns (array of field names).",
        "input_schema": {"type": "object", "properties": {
            "object": {"type": "string"}, "name": {"type": "string"},
            "view_type": {"type": "string", "description": "table | kanban"},
            "sort_by": {"type": "string"}, "sort_direction": {"type": "string"},
            "group_by": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}}},
            "required": ["object"]},
    },
    "twenty__update_view": {
        "description": "[Owned CRM STRUCTURE] Rename a view/list. Identify by view_id or name; pass new_name.",
        "input_schema": {"type": "object", "properties": {
            "view_id": {"type": "string"}, "name": {"type": "string"}, "new_name": {"type": "string"}}, "required": []},
    },
    "twenty__delete_view": {
        "description": "[Owned CRM STRUCTURE — DESTRUCTIVE] Delete a view/list. Identify by view_id or name. Requires hold-to-confirm.",
        "input_schema": {"type": "object", "properties": {"view_id": {"type": "string"}, "name": {"type": "string"}}, "required": []},
    },
}

# Metadata writes (everything except the two list_* reads) trigger a cockpit refresh.
TWENTY_METADATA_WRITE = frozenset(k for k in TWENTY_METADATA_TOOLS if not k.endswith(("list_objects", "list_views")))
# Structural deletes require hold-to-confirm.
TWENTY_METADATA_DESTRUCTIVE = frozenset({"twenty__delete_field", "twenty__delete_object", "twenty__delete_view"})
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

    # Rue CRM (self-hosted Twenty). Offered when the user has their OWN
    # provisioned workspace (Phase 2) OR the server has a shared instance via
    # TWENTY_API_URL + TWENTY_API_KEY (Phase 1 fallback).
    if await TwentyClient.configured_for_user(user_id):
        tools += [
            {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
            for name, defn in {**TWENTY_TOOLS, **TWENTY_WRITE_TOOLS, **TWENTY_METADATA_TOOLS}.items()
        ]

    # mgcoleads — MG&CO's B2B lead engine. Additive + env-gated (LEADS_MAPS_API_KEY) AND
    # tier-gated: Rue Leads is Emperor-only (real Google Places cash cost). Grandfathered
    # users map to Emperor, so existing users are unaffected. Non-Emperor users never even see
    # the tools, so the model can't call them.
    if leads_enabled():
        leads_ok = True
        if user_id:
            try:
                from backend.lib.billing import entitlements as _ent
                leads_ok = bool(_ent.for_user(user_id).get("leads"))
            except Exception:
                leads_ok = True  # fail open: don't strip tools on a transient billing error
        if leads_ok:
            tools += [
                {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
                for name, defn in LEADS_TOOLS.items()
            ]

    # Sales Advisor — deep-research one business → closer pitch report. Additive + env-gated
    # (needs only the Anthropic key) AND tier-gated exactly like Leads (it burns real Opus +
    # Places spend). Grandfathered users map to Emperor, so existing users are unaffected.
    if sales_advisor_enabled():
        sales_ok = True
        if user_id:
            try:
                from backend.lib.billing import entitlements as _ent
                sales_ok = bool(_ent.for_user(user_id).get("leads"))
            except Exception:
                sales_ok = True  # fail open: don't strip tools on a transient billing error
        if sales_ok:
            tools += [
                {"name": name, "description": defn["description"], "input_schema": defn["input_schema"]}
                for name, defn in SALES_TOOLS.items()
            ]

    return tools
