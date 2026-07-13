"""
pdf__create — always-on PDF export tool for Business chat.

Locks in: Rue can render structured content (headings/paragraphs/tables) to a
downloadable PDF instead of refusing ("I don't have a PDF generation tool") or
detouring to Notion. Rendering = pdf_export.generate_report_pdf; storage =
document_store (same pattern as CSV/PPTX/real-estate docs).
"""
import io
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.lib.business.pdf_export import HAS_REPORTLAB
from backend.lib.business.pdf_tool import _safe_filename, run_pdf_create
from backend.lib.business.tool_builder import _ALWAYS_ON_TOOLS
from backend.routes.business.chat import WRITE_ACTIONS

LEAD_BLOCKS = [
    {"type": "heading", "text": "Top 10 HOT Call List"},
    {"type": "paragraph", "text": "Durham region trades — call in rank order.\n- Start with the no-website leads\n- Pitch: Premium Website + AI Receptionist"},
    {"type": "table",
     "headers": ["Name", "Address", "Category", "Maps Link", "Phone", "Pitch"],
     "rows": [
         ["Mario's Garage", "12 King St E, Oshawa", "Auto repair", "https://maps.google.com/?q=Mario's+Garage", "(416) 531-0875", "Premium Website + AI Receptionist"],
         ["topplusroofing", "88 Simcoe St N, Oshawa", "Roofing", "https://maps.google.com/?q=topplusroofing", "(647) 213-1121", "Premium Website + AI Receptionist"],
     ]},
]


# ── Rendering ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
def test_report_pdf_renders_mixed_blocks_branded_by_client():
    from backend.lib.business.pdf_export import generate_report_pdf
    pypdf = pytest.importorskip("pypdf")

    pdf = generate_report_pdf(
        title="Durham Region Trades",
        blocks=LEAD_BLOCKS,
        subtitle="HOT leads",
        brand_name="MG Client Co",
        note="Generated from live Google Places data.",
    )
    assert pdf.startswith(b"%PDF")
    text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    up = text.upper()
    assert "DURHAM REGION TRADES" in up
    assert "MARIO'S GARAGE" in up and "TOPPLUSROOFING" in up
    assert "PHONE" in up and "PITCH" in up
    assert "MG CLIENT CO" in up          # client's brand shown
    assert "MG&CO" not in up             # our company never on client docs


@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
def test_report_pdf_wide_table_goes_landscape():
    from reportlab.lib.pagesizes import letter
    from backend.lib.business.pdf_export import generate_report_pdf
    pypdf = pytest.importorskip("pypdf")

    pdf = generate_report_pdf(title="Wide", blocks=[LEAD_BLOCKS[2]])  # 6-column table
    page = pypdf.PdfReader(io.BytesIO(pdf)).pages[0]
    assert float(page.mediabox.width) > float(page.mediabox.height)  # landscape
    assert float(page.mediabox.width) == pytest.approx(letter[1])


# ── Tool behavior ────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
@pytest.mark.asyncio
async def test_run_pdf_create_returns_working_download():
    from backend.lib.business.document_store import load_document

    with patch("backend.lib.business.pdf_tool.get_brand_config",
               new=AsyncMock(return_value={"display_name": "MG Client Co"})):
        result = await run_pdf_create(
            {"title": "Durham Region Trades — Top 10 HOT Call List", "blocks": LEAD_BLOCKS},
            "user_1",
        )

    assert result.ok, result.error
    assert result.data["status"] == "created"
    assert result.data["filename"].endswith(".pdf")
    assert result.data["download_url"].startswith("http")
    assert result.data["blocks_rendered"] == 3

    loaded = load_document(result.data["doc_id"])
    assert loaded is not None
    content, filename, content_type = loaded
    assert content.startswith(b"%PDF")
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_run_pdf_create_validates_input():
    r = await run_pdf_create({"blocks": LEAD_BLOCKS}, "u")
    assert not r.ok and "title" in r.error

    r = await run_pdf_create({"title": "T"}, "u")
    assert not r.ok and "blocks" in r.error

    r = await run_pdf_create({"title": "T", "blocks": [{"type": "mystery"}, {"type": "heading"}]}, "u")
    assert not r.ok and "renderable" in r.error.lower()


@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
@pytest.mark.asyncio
async def test_run_pdf_create_survives_brand_config_failure():
    with patch("backend.lib.business.pdf_tool.get_brand_config",
               new=AsyncMock(side_effect=RuntimeError("supabase down"))):
        result = await run_pdf_create({"title": "T", "blocks": LEAD_BLOCKS}, "user_1")
    assert result.ok, result.error


def test_safe_filename():
    assert _safe_filename("", "Durham Trades: Top 10!") == "Durham-Trades-Top-10.pdf"
    assert _safe_filename("my report.PDF", "x") == "my-report.pdf"
    assert _safe_filename("../../etc/passwd", "x") == "etcpasswd.pdf"
    assert _safe_filename("", "") == "document.pdf"


# ── Wiring ───────────────────────────────────────────────────────────────────

def test_pdf_create_is_always_on_and_confirm_free():
    assert "pdf__create" in _ALWAYS_ON_TOOLS
    schema = _ALWAYS_ON_TOOLS["pdf__create"]["input_schema"]
    assert set(schema["required"]) == {"title", "blocks"}
    assert "pdf__create" not in WRITE_ACTIONS  # runs immediately, no confirm card


@pytest.mark.asyncio
async def test_build_tools_includes_pdf_even_without_user():
    from backend.lib.business.tool_builder import build_tools_for_user
    tools = await build_tools_for_user("")
    assert any(t["name"] == "pdf__create" for t in tools)


@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
@pytest.mark.asyncio
async def test_executor_dispatches_pdf_create():
    from backend.lib.business import tool_executor

    with patch("backend.lib.business.pdf_tool.get_brand_config",
               new=AsyncMock(return_value={"display_name": ""})):
        out = await tool_executor.execute_tool(
            "pdf__create", {"title": "Call Sheet", "blocks": LEAD_BLOCKS}, "user_1"
        )
    data = json.loads(out)
    assert "error" not in data
    assert data["download_url"].startswith("http")
