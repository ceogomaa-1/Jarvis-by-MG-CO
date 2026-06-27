"""TOOL 2 — Offer & Amendment Drafter. Generates a structured purchase offer
or amendment via LLM and renders it to a branded PDF."""
from backend.lib.business.brand_config import get_brand_config
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.document_store import save_document
from backend.lib.business.model_router import SONNET
from backend.lib.business.pdf_export import generate_branded_document_pdf
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.lib.business.real_estate.profile import get_business_profile

LIABILITY_NOTE = "Draft for review — confirm with your brokerage/legal counsel before presenting."

DOC_TYPE_LABELS = {
    "offer": "Purchase Offer",
    "amendment": "Amendment to Agreement of Purchase and Sale",
}

_DRAFT_SYSTEM = "You are a real estate transaction coordinator drafting clean, professional documents for a licensed agent."


async def draft_offer_document(
    user_id: str,
    doc_type: str,
    property_address: str,
    buyer_name: str = "",
    seller_name: str = "",
    price: str = "",
    deposit: str = "",
    closing_date: str = "",
    conditions: list[str] | None = None,
    custom_clauses: str = "",
) -> ConnectorResult:
    if not property_address:
        return ConnectorResult(ok=False, error="property_address is required.")

    doc_type = (doc_type or "offer").strip().lower()
    if doc_type not in DOC_TYPE_LABELS:
        doc_type = "offer"

    profile = await get_business_profile(user_id)
    brokerage = profile.get("company_name") or "the brokerage"

    # Client deliverable: brand it with the agent's OWN business name (brand config
    # display_name, falling back to their company name) — NEVER MG&CO.
    brand = await get_brand_config(user_id)
    brand_name = (brand.get("display_name") or profile.get("company_name") or "").strip()

    conditions = conditions or []
    conditions_str = "\n".join(f"- {c}" for c in conditions) if conditions else "- None specified"

    prompt = f"""Draft a {DOC_TYPE_LABELS[doc_type]} for a residential real estate transaction.

Return JSON only, with this exact shape:
{{"title": "...", "subtitle": "...", "sections": [{{"heading": "...", "body": "..."}}]}}

Use these section headings, in this order: Parties, Property, Terms, Conditions, Signatures.
In each "body": use "\\n" to separate lines, and prefix list items with "- " so they render as bullets.
Write in plain, professional real estate contract language — concrete, not generic boilerplate filler.
The "Signatures" section body must list signature lines for Buyer, Seller, Date, and Witness as "- " bullet lines.

DETAILS:
- Document type: {DOC_TYPE_LABELS[doc_type]}
- Property address: {property_address}
- Buyer: {buyer_name or "[buyer name not provided]"}
- Seller: {seller_name or "[seller name not provided]"}
- Purchase price: {price or "[not specified]"}
- Deposit: {deposit or "[not specified]"}
- Closing date: {closing_date or "[not specified]"}
- Conditions:
{conditions_str}
- Custom clauses: {custom_clauses or "None"}
- Brokerage: {brokerage}"""

    try:
        raw = await call_claude(system=_DRAFT_SYSTEM, prompt=prompt, model=SONNET, max_tokens=2000)
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Document drafting failed: {e}")

    parsed = parse_json_response(raw)
    if not parsed or not parsed.get("sections"):
        return ConnectorResult(ok=False, error="Couldn't generate the document — try again with a bit more detail (price, dates, parties).")

    title = parsed.get("title") or f"{DOC_TYPE_LABELS[doc_type]} — {property_address}"
    subtitle = parsed.get("subtitle") or property_address

    try:
        pdf_bytes = generate_branded_document_pdf(title, subtitle, parsed["sections"], footer_note=LIABILITY_NOTE, brand_name=brand_name)
    except ImportError:
        return ConnectorResult(ok=False, error="PDF generation isn't available on the server — reportlab is missing.")

    safe_addr = "".join(c if c.isalnum() or c in " -_" else "" for c in property_address)[:40].strip() or "document"
    filename = f"{doc_type}-{safe_addr}.pdf"
    doc = save_document(pdf_bytes, filename, "application/pdf")

    return ConnectorResult(
        ok=True,
        data={
            "download_url": doc["download_url"],
            "filename": doc["filename"],
            "title": title,
            "type": doc_type,
            "note": LIABILITY_NOTE,
        },
    )
