"""TOOL — Fill OREA Form 100 (Agreement of Purchase and Sale).

Fills a flat (non-AcroForm) OREA Form 100 PDF using a coordinate-based
overlay (form_overlay.fill_overlay + form_templates.orea_100.FIELDS).

There is deliberately NO LLM field-mapping step here — this is a legal
document, and a wrong guess on a deal term is a real-world liability. Field
values come ONLY from:
  1. known_values passed by the caller (Claude, populated from the
     conversation / an uploaded CSV / the user's profile)
  2. listing_data looked up via lookup_listing_data(address), for the
     subset of fields not already present in known_values
  3. today's date, computed deterministically for agreement_day/month/year

Fields not covered by any of the above are returned in `missing_fields` so
the caller can ask the user for them. Output is always labeled DRAFT —
review before use; not legal advice. Pages 3-6 (legal boilerplate,
signature/witness/date blocks, Confirmation of Cooperation) are not covered.
"""
import io
from datetime import datetime

import pytz
from pypdf import PdfReader

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.document_store import load_document, save_document
from backend.lib.business.real_estate.form_overlay import fill_overlay
from backend.lib.business.real_estate.form_templates.orea_100 import FIELDS, PAGE_HEIGHT, PAGE_WIDTH
from backend.lib.business.real_estate.listing_lookup import lookup_listing_data

_LISTING_FIELD_MAP = {
    "list_price": "purchase_price_numeral",
    "legal_description": "legal_description",
    "frontage": "frontage",
    "depth": "depth",
    "municipality": "municipality",
}


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _today_fields() -> dict:
    now = datetime.now(pytz.timezone("America/Toronto"))
    return {
        "agreement_day": _ordinal(now.day),
        "agreement_month": now.strftime("%B"),
        "agreement_year": now.strftime("%y"),
    }


async def fill_orea_form(user_id: str, doc_id: str, address: str = "", known_values: dict | None = None) -> ConnectorResult:
    if not doc_id:
        return ConnectorResult(ok=False, error="doc_id is required — attach the PDF first.")

    known_values = {k: v for k, v in (known_values or {}).items() if v}

    loaded = load_document(doc_id)
    if not loaded:
        return ConnectorResult(ok=False, error="Couldn't find that PDF — please re-attach it.")

    content, filename, _content_type = loaded

    try:
        reader = PdfReader(io.BytesIO(content))
        first_page_text = reader.pages[0].extract_text() or ""
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Couldn't read that PDF: {e}")

    if "Form 100" not in first_page_text or "Agreement of Purchase and Sale" not in first_page_text:
        return ConnectorResult(
            ok=False,
            error=(
                "This doesn't look like an OREA Form 100 — I don't have a coordinate "
                "template for it yet. Try realestate__fill_pdf_form for a general breakdown."
            ),
        )

    values: dict = _today_fields()

    sources: list[str] = []
    listing_note = ""
    if address:
        listing = await lookup_listing_data(address)
        listing_data = listing.get("listing_data") or {}
        sources = listing.get("sources") or []
        listing_note = listing.get("note") or ""
        for src_key, field_key in _LISTING_FIELD_MAP.items():
            if field_key not in known_values and listing_data.get(src_key):
                values[field_key] = listing_data[src_key]

    values.update(known_values)

    filled = {k: v for k, v in values.items() if k in FIELDS and v}
    missing = [{"field": k, "label": spec["label"]} for k, spec in FIELDS.items() if k not in filled]

    try:
        pdf_bytes = fill_overlay(content, PAGE_WIDTH, PAGE_HEIGHT, FIELDS, filled)
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Failed to fill form: {e}")

    new_filename = f"DRAFT-{filename}"
    saved = save_document(pdf_bytes, new_filename, "application/pdf")

    message = (
        f"DRAFT — review carefully before sending or signing. Not legal advice. "
        f"Filled {len(filled)} of {len(FIELDS)} fields; {len(missing)} still need values "
        "(see missing_fields) — ask the user or fill those in by hand. Pages 3-6 (legal "
        "boilerplate, signatures, Confirmation of Cooperation) are not auto-filled."
    )
    if listing_note:
        message += f" {listing_note}"

    return ConnectorResult(
        ok=True,
        data={
            "doc_id": saved["doc_id"],
            "download_url": saved["download_url"],
            "filename": saved["filename"],
            "filled_fields": filled,
            "missing_fields": missing,
            "sources": sources,
            "message": message,
        },
    )
