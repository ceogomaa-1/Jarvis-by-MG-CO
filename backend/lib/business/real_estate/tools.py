"""Real Estate Operator Suite — tool definitions + dispatcher.

Gated to users whose industry resolves to real_estate.md (see
backend.lib.business.real_estate.profile.is_real_estate_user). Tool names use
the `realestate__` prefix and are dispatched specially in tool_executor (not
via the connector registry, since these aren't all simple connector wrappers).
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.pptx_generator import generate_presentation
from backend.lib.business.real_estate import ghl_leads, offer_drafter, pdf_form_filler, seller_research, showing_booker

REAL_ESTATE_TOOLS: dict[str, dict] = {
    "realestate__ghl_scan_stale_leads": {
        "description": "[Real Estate / GoHighLevel] Scan CRM contacts for stale leads (no activity in N days), classify which need follow-up, and draft 1-2 sentence follow-up messages. Returns a ranked, actionable queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_stale": {"type": "integer", "description": "Flag contacts with no activity in this many days (default 14)"},
                "limit": {"type": "integer", "description": "Max stale leads to return (default 25)"},
            },
            "required": [],
        },
    },
    "realestate__ghl_add_note": {
        "description": "[Real Estate / GoHighLevel] Add a note to a CRM contact — log actions Jarvis took (follow-ups sent, showings booked) back into GoHighLevel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "GoHighLevel contact ID"},
                "note": {"type": "string", "description": "Note text to add"},
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
    "realestate__generate_presentation": {
        "description": "[Real Estate] Generate a branded PowerPoint deck — listing presentation, CMA, buyer guide, or custom — using the MG&CO template.",
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


async def execute_real_estate_tool(action_name: str, tool_input: dict, user_id: str) -> ConnectorResult:
    if action_name == "ghl_scan_stale_leads":
        return await ghl_leads.scan_stale_leads(
            user_id,
            days_stale=tool_input.get("days_stale", 14),
            limit=tool_input.get("limit", 25),
        )

    if action_name == "ghl_add_note":
        return await ghl_leads.add_note(user_id, tool_input.get("contact_id", ""), tool_input.get("note", ""))

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
        )

    if action_name == "fill_pdf_form":
        return await pdf_form_filler.fill_pdf_form(
            user_id,
            doc_id=tool_input.get("doc_id", ""),
            known_values=tool_input.get("known_values") or {},
        )

    if action_name == "generate_presentation":
        return await generate_presentation(
            deck_type=tool_input.get("type", "custom"),
            title=tool_input.get("title", ""),
            content=tool_input.get("content"),
        )

    return ConnectorResult(ok=False, error=f"Unknown Real Estate tool: {action_name}")
