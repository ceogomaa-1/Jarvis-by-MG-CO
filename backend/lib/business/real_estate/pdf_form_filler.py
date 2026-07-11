"""TOOL 5 — PDF Form Auto-Fill. Reads AcroForm fields from an uploaded PDF and
fills them using the user's profile + values stated in the conversation. Flat
(non-fillable) PDFs get an honest "here's what I'd fill" breakdown instead."""
import io

from pypdf import PdfReader, PdfWriter

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.document_store import load_document, save_document
from backend.lib.business.model_router import HAIKU
from backend.lib.business.real_estate.llm import call_claude, parse_json_response
from backend.lib.business.real_estate.profile import get_business_profile

_FILL_SYSTEM = (
    "You map PDF form field names to values for a real estate agent, using their "
    "profile and details from the conversation. Only fill fields you're confident about."
)
_FLAT_SYSTEM = (
    "You analyze a flat (non-fillable) PDF and tell a real estate agent what values "
    "Rue would put where, based on their profile and the conversation."
)


async def fill_pdf_form(user_id: str, doc_id: str, known_values: dict | None = None) -> ConnectorResult:
    if not doc_id:
        return ConnectorResult(ok=False, error="doc_id is required — attach the PDF first.")

    loaded = load_document(doc_id)
    if not loaded:
        return ConnectorResult(ok=False, error="Couldn't find that PDF — please re-attach it.")

    content, filename, _content_type = loaded
    profile = await get_business_profile(user_id)
    profile_summary = {
        "company_name": profile.get("company_name"),
        "role": profile.get("role"),
        "email": profile.get("email"),
        "memories": profile.get("memories", [])[:15],
    }

    try:
        reader = PdfReader(io.BytesIO(content))
        fields = reader.get_fields()
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Couldn't read that PDF: {e}")

    if not fields:
        return await _flat_pdf_breakdown(reader, filename, profile_summary, known_values)

    field_names = list(fields.keys())
    prompt = f"""Map these PDF form field names to values.

FIELD NAMES: {field_names}
PROFILE: {profile_summary}
KNOWN VALUES FROM CONVERSATION: {known_values or {}}

Return JSON only:
{{"field_values": {{"<exact field name>": "<value>"}}}}

Only include fields you have a confident value for — omit fields you cannot fill."""

    field_values: dict = {}
    try:
        raw = await call_claude(system=_FILL_SYSTEM, prompt=prompt, model=HAIKU, max_tokens=1500)
        parsed = parse_json_response(raw) or {}
        field_values = parsed.get("field_values", {})
    except Exception as e:
        print(f"PDF_FORM_FILLER: field mapping error: {e}")

    if not field_values:
        return ConnectorResult(
            ok=True,
            data={
                "flat_pdf": False,
                "filename": filename,
                "filled_fields": {},
                "field_names": field_names,
                "message": "I found fillable fields but didn't have enough information to confidently fill any of them — tell me the values and I'll fill it in.",
            },
        )

    str_values = {k: str(v) for k, v in field_values.items()}

    writer = PdfWriter()
    writer.append(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, str_values)

    buf = io.BytesIO()
    writer.write(buf)

    doc = save_document(buf.getvalue(), f"filled-{filename}", "application/pdf")

    return ConnectorResult(
        ok=True,
        data={
            "flat_pdf": False,
            "download_url": doc["download_url"],
            "filename": doc["filename"],
            "filled_fields": str_values,
        },
    )


async def _flat_pdf_breakdown(reader: PdfReader, filename: str, profile_summary: dict, known_values: dict | None) -> ConnectorResult:
    text = "\n".join((page.extract_text() or "") for page in reader.pages)

    prompt = f"""This PDF has no fillable form fields (it's a flat/scanned document).

PROFILE: {profile_summary}
KNOWN VALUES FROM CONVERSATION: {known_values or {}}

PDF TEXT (truncated):
{text[:4000]}

Return JSON only:
{{"would_fill": [{{"field": "...", "value": "..."}}], "summary": "1-2 sentences telling the user this PDF can't be auto-filled and what Rue would put where"}}"""

    parsed: dict = {}
    try:
        raw = await call_claude(system=_FLAT_SYSTEM, prompt=prompt, model=HAIKU, max_tokens=800)
        parsed = parse_json_response(raw) or {}
    except Exception as e:
        print(f"PDF_FORM_FILLER: flat extraction error: {e}")

    return ConnectorResult(
        ok=True,
        data={
            "flat_pdf": True,
            "filename": filename,
            "would_fill": parsed.get("would_fill", []),
            "message": parsed.get("summary") or "This PDF has no fillable fields, so I can't auto-fill it directly — here's what I'd put where if you confirm.",
        },
    )
