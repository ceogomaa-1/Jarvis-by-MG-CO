"""
pdf__create — always-on chat tool that renders structured content (headings,
paragraphs, tables) into a downloadable PDF.

Thin wrapper: rendering lives in pdf_export.generate_report_pdf (same engine as
the real-estate offer/report PDFs), storage + download URL come from
document_store (same pattern as CSV export, PPTX decks, and OREA form fills —
served back via GET /api/business/documents/{doc_id}).

Confirm-free by design: it only produces a file for the user to download; it
never touches an external account.
"""
import re

from backend.lib.business.brand_config import get_brand_config
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.document_store import save_document
from backend.lib.business.pdf_export import HAS_REPORTLAB, generate_report_pdf

_RENDERABLE_TYPES = ("heading", "paragraph", "table")


def _safe_filename(requested: str, title: str) -> str:
    base = (requested or title or "document").strip()
    base = re.sub(r"\.pdf$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", base).strip().replace(" ", "-")[:80] or "document"
    return f"{base}.pdf"


async def run_pdf_create(tool_input: dict, user_id: str) -> ConnectorResult:
    if not HAS_REPORTLAB:
        return ConnectorResult(ok=False, error="PDF engine unavailable on this server (reportlab not installed).")

    title = (tool_input.get("title") or "").strip()
    if not title:
        return ConnectorResult(ok=False, error="`title` is required")

    blocks = tool_input.get("blocks")
    if not blocks or not isinstance(blocks, list):
        return ConnectorResult(ok=False, error="`blocks` must be a non-empty list of heading/paragraph/table blocks")

    renderable = [
        b for b in blocks
        if isinstance(b, dict) and b.get("type") in _RENDERABLE_TYPES
        and (b.get("text") or b.get("headers") or b.get("rows"))
    ]
    if not renderable:
        return ConnectorResult(ok=False, error=(
            "No renderable blocks — each block needs type 'heading'/'paragraph' (with text) "
            "or 'table' (with headers + rows)"
        ))

    # Brand with the client's own business name (never MG&CO); best-effort.
    brand_name = ""
    try:
        brand = await get_brand_config(user_id)
        brand_name = (brand.get("display_name") or "").strip()
    except Exception:
        pass

    try:
        pdf_bytes = generate_report_pdf(
            title=title,
            blocks=renderable,
            subtitle=(tool_input.get("subtitle") or "").strip(),
            brand_name=brand_name,
            note=(tool_input.get("note") or "").strip(),
        )
    except Exception as e:
        return ConnectorResult(ok=False, error=f"PDF rendering failed: {e}")

    filename = _safe_filename(tool_input.get("filename") or "", title)
    doc = save_document(pdf_bytes, filename, "application/pdf")

    return ConnectorResult(ok=True, data={
        "status": "created",
        "doc_id": doc["doc_id"],
        "filename": filename,
        "download_url": doc["download_url"],
        "blocks_rendered": len(renderable),
        "hint": "Give the user the download_url as a markdown link, e.g. [Download the PDF](url).",
    })
