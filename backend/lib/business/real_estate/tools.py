"""Real Estate Operator Suite — tool definitions + dispatcher.

Gated to users whose industry resolves to real_estate.md (see
backend.lib.business.real_estate.profile.is_real_estate_user). Tool names use
the `realestate__` prefix and are dispatched specially in tool_executor (not
via the connector registry, since these aren't all simple connector wrappers).
"""
from backend.lib.business.brand_config import get_brand_config
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.pptx_generator import generate_presentation
from backend.lib.business.real_estate import contact_enrichment, ghl_leads, offer_drafter, orea_form_filler, pdf_form_filler, seller_research, showing_booker
from backend.lib.business.real_estate.form_templates.orea_100 import FIELDS as OREA_FIELDS

_OREA_FIELDS_DESC = "; ".join(f"{k} ({spec['label']})" for k, spec in OREA_FIELDS.items())

REAL_ESTATE_TOOLS: dict[str, dict] = {
    "realestate__ghl_scan_stale_leads": {
        "description": "[Real Estate / GoHighLevel] Scan CRM contacts for stale leads (no activity in N days), classify which need follow-up, and draft 1-2 sentence follow-up messages. Returns a ranked, actionable queue. If the user has more than one GoHighLevel account connected, defaults to scanning ALL of them (response includes an 'accounts' breakdown) — pass account_label to scope to one account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_stale": {"type": "integer", "description": "Flag contacts with no activity in this many days (default 14)"},
                "limit": {"type": "integer", "description": "Max stale leads to return per account (default 25)"},
                "account_label": {"type": "string", "description": "Which connected GoHighLevel account to scan (see Connected Tools for labels), or 'all' (default) to scan every connected account"},
            },
            "required": [],
        },
    },
    "realestate__ghl_contacts_no_future_task": {
        "description": "[Real Estate / GoHighLevel] Find every CRM contact that has NO open/future task (no incomplete task due now or later) and export them as a clean, downloadable CSV (name, phone, email, last activity). Use when the user asks for contacts with no upcoming/scheduled task or no follow-up planned. Pass account_label to pick which connected GoHighLevel account (defaults to 'default').",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_label": {"type": "string", "description": "Which connected GoHighLevel account to scan (see Connected Tools for labels). Defaults to 'default'."},
                "max_contacts": {"type": "integer", "description": "Max contacts to scan (default 300)."},
            },
            "required": [],
        },
    },
    "realestate__ghl_add_note": {
        "description": "[Real Estate / GoHighLevel] Add a note to a CRM contact — log actions Jarvis took (follow-ups sent, showings booked) back into GoHighLevel. If the user has more than one GoHighLevel account connected, pass account_label to specify which one (defaults to 'default' / their first account) — use the account_label the contact came from in a stale-lead scan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "GoHighLevel contact ID"},
                "note": {"type": "string", "description": "Note text to add"},
                "account_label": {"type": "string", "description": "Which connected GoHighLevel account this contact belongs to (see Connected Tools for labels). Defaults to 'default'."},
            },
            "required": ["contact_id", "note"],
        },
    },
    "realestate__draft_offer_document": {
        "description": "[Real Estate] Draft a purchase offer or amendment as a branded PDF (parties, property, terms, conditions, signatures). Always includes a 'review with brokerage/legal counsel' disclaimer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["offer", "amendment"], "description": "Document type"},
                "property_address": {"type": "string", "description": "Property address"},
                "buyer_name": {"type": "string", "description": "Buyer full name(s)"},
                "seller_name": {"type": "string", "description": "Seller full name(s)"},
                "price": {"type": "string", "description": "Purchase price, e.g. '$650,000'"},
                "deposit": {"type": "string", "description": "Deposit amount"},
                "closing_date": {"type": "string", "description": "Closing date"},
                "conditions": {"type": "array", "items": {"type": "string"}, "description": "Conditions (financing, inspection, etc.)"},
                "custom_clauses": {"type": "string", "description": "Any additional custom clauses"},
            },
            "required": ["type", "property_address"],
        },
    },
    "realestate__book_showing": {
        "description": "[Real Estate] Book a property showing on Google Calendar. If GoHighLevel is connected and a matching contact exists, also logs a note to the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "property_address": {"type": "string", "description": "Property address"},
                "client_name": {"type": "string", "description": "Client/buyer name"},
                "datetime": {"type": "string", "description": "Showing date/time, ISO 8601, e.g. 2026-06-15T14:00:00"},
                "duration_min": {"type": "integer", "description": "Duration in minutes (default 45)"},
                "notes": {"type": "string", "description": "Optional notes for the calendar event"},
                "contact_id": {"type": "string", "description": "Optional GoHighLevel contact ID, to log the note directly"},
            },
            "required": ["property_address", "client_name", "datetime"],
        },
    },
    "realestate__research_seller_contacts": {
        "description": "[Real Estate] Research public contact info for a property owner / FSBO seller via web search and page extraction. Public sources only — always cites sources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Property address or owner name to research"},
                "region": {"type": "string", "description": "City/region to narrow the search (optional)"},
            },
            "required": ["query"],
        },
    },
    "realestate__fill_pdf_form": {
        "description": "[Real Estate] Fill an uploaded PDF form using the user's profile and details from the conversation. If the PDF has no fillable fields, returns an honest breakdown of what would be filled where.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID of the attached PDF, given to you in the conversation context"},
                "known_values": {"type": "object", "description": "Field values stated by the user in the conversation (optional)"},
            },
            "required": ["doc_id"],
        },
    },
    "realestate__enrich_contacts": {
        "description": "[Real Estate] Best-effort public-record contact enrichment for a list of leads (e.g. parsed from an uploaded CSV) — searches the web plus people-search/brokerage/social sources (Canada411, 411.ca, WhitePages, realtor.ca, LinkedIn, Facebook) for phone numbers and emails. Every result includes a source URL and a confidence level (high/medium/low). Returns 'not found' honestly when nothing reliable turns up — NEVER fabricates a phone number, email, or name. Processes up to 5 people per call (call again for more rows).",
        "input_schema": {
            "type": "object",
            "properties": {
                "people": {
                    "type": "array",
                    "description": "Leads to research (max 5 per call). Parse rows from the uploaded CSV / conversation into this shape.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Full name of the person to research"},
                            "address": {"type": "string", "description": "Known address, if any"},
                            "city": {"type": "string", "description": "City, if known"},
                            "company": {"type": "string", "description": "Known company/brokerage, if any"},
                        },
                        "required": ["name"],
                    },
                },
                "region": {"type": "string", "description": "City/region to narrow the search, e.g. 'Toronto, ON' (optional)"},
            },
            "required": ["people"],
        },
    },
    "realestate__fill_orea_form": {
        "description": "[Real Estate] Fill an OREA Form 100 (Agreement of Purchase and Sale) PDF using a coordinate overlay — covers the core deal terms on visual pages 1-2 (parties, property, price, deposit, irrevocability, completion date, chattels/fixtures/rental items/HST). Pages 3-6 (legal boilerplate, signatures, Confirmation of Cooperation) are NOT filled. Returns a DRAFT PDF plus lists of filled vs. still-missing fields. Always for human review — not legal advice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID of the attached OREA Form 100 PDF, given to you in the conversation context"},
                "address": {"type": "string", "description": "Property address — used to look up listing data (price, legal description, frontage, depth, municipality) for fields not already in known_values (optional)"},
                "known_values": {
                    "type": "object",
                    "description": (
                        "Field values you are confident about from the conversation, an uploaded CSV, or the user's profile — "
                        "NEVER invent or estimate a value, especially for price, dates, and legal description. Only include "
                        f"keys you have a real value for. Valid keys: {_OREA_FIELDS_DESC}"
                    ),
                },
            },
            "required": ["doc_id"],
        },
    },
    "realestate__generate_presentation": {
        "description": "[Real Estate] Generate a PowerPoint deck — listing presentation, CMA, buyer guide, or custom — branded with the agent's OWN business name (never MG&CO).",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["listing", "cma", "buyer_guide", "custom"], "description": "Deck type"},
                "title": {"type": "string", "description": "Deck title"},
                "content": {"type": "object", "description": "Property data / content outline for the LLM to write into the deck"},
            },
            "required": ["type"],
        },
    },
}


async def execute_real_estate_tool(action_name: str, tool_input: dict, user_id: str, progress_cb=None) -> ConnectorResult:
    if action_name == "ghl_scan_stale_leads":
        return await ghl_leads.scan_stale_leads(
            user_id,
            days_stale=tool_input.get("days_stale", 14),
            limit=tool_input.get("limit", 25),
            account_label=tool_input.get("account_label", "all"),
        )

    if action_name == "ghl_contacts_no_future_task":
        return await ghl_leads.export_contacts_without_future_tasks(
            user_id,
            account_label=tool_input.get("account_label", "default"),
            max_contacts=tool_input.get("max_contacts", 300),
        )

    if action_name == "ghl_add_note":
        return await ghl_leads.add_note(
            user_id,
            tool_input.get("contact_id", ""),
            tool_input.get("note", ""),
            account_label=tool_input.get("account_label", "default"),
        )

    if action_name == "draft_offer_document":
        return await offer_drafter.draft_offer_document(
            user_id,
            doc_type=tool_input.get("type", "offer"),
            property_address=tool_input.get("property_address", ""),
            buyer_name=tool_input.get("buyer_name", ""),
            seller_name=tool_input.get("seller_name", ""),
            price=tool_input.get("price", ""),
            deposit=tool_input.get("deposit", ""),
            closing_date=tool_input.get("closing_date", ""),
            conditions=tool_input.get("conditions") or [],
            custom_clauses=tool_input.get("custom_clauses", ""),
        )

    if action_name == "book_showing":
        return await showing_booker.book_showing(
            user_id,
            property_address=tool_input.get("property_address", ""),
            client_name=tool_input.get("client_name", ""),
            showing_datetime=tool_input.get("datetime", ""),
            duration_min=tool_input.get("duration_min", 45),
            notes=tool_input.get("notes", ""),
            contact_id=tool_input.get("contact_id"),
        )

    if action_name == "research_seller_contacts":
        return await seller_research.research_seller_contacts(
            query=tool_input.get("query", ""),
            region=tool_input.get("region", ""),
            progress_cb=progress_cb,
        )

    if action_name == "fill_pdf_form":
        return await pdf_form_filler.fill_pdf_form(
            user_id,
            doc_id=tool_input.get("doc_id", ""),
            known_values=tool_input.get("known_values") or {},
        )

    if action_name == "enrich_contacts":
        return await contact_enrichment.enrich_contacts(
            people=tool_input.get("people") or [],
            region=tool_input.get("region", ""),
            progress_cb=progress_cb,
        )

    if action_name == "fill_orea_form":
        return await orea_form_filler.fill_orea_form(
            user_id,
            doc_id=tool_input.get("doc_id", ""),
            address=tool_input.get("address", ""),
            known_values=tool_input.get("known_values") or {},
        )

    if action_name == "generate_presentation":
        # Brand the deck with the agent's own business name (brand config display_name),
        # never MG&CO.
        _brand = await get_brand_config(user_id)
        _brand_name = (_brand.get("display_name") or "").strip()
        return await generate_presentation(
            deck_type=tool_input.get("type", "custom"),
            title=tool_input.get("title", ""),
            content=tool_input.get("content"),
            brand_name=_brand_name,
        )

    return ConnectorResult(ok=False, error=f"Unknown Real Estate tool: {action_name}")
