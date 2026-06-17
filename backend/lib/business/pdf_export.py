import io
import textwrap
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors as _rl_colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# MG&CO is OUR company, not the client's — it must NEVER appear on a user-facing
# deliverable. Generated documents carry the client's own business name when we have
# it (brand_config.display_name); otherwise the brand line is simply omitted. This
# helper is the single source of truth for that rule.
def _footer_label(brand_name: str = "") -> str:
    return f"Prepared by {brand_name.strip()}" if brand_name and brand_name.strip() else ""


def generate_pdf(walkthrough: dict, brand_name: str = "") -> bytes:
    if not HAS_REPORTLAB:
        raise ImportError("reportlab not installed — add it to requirements.txt")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72,
    )

    styles = getSampleStyleSheet()
    accent = HexColor("#c84b31")

    title_style = ParagraphStyle(
        "BizTitle", parent=styles["Title"],
        fontSize=22, textColor=accent, spaceAfter=10, fontName="Helvetica-Bold",
    )
    meta_style = ParagraphStyle(
        "BizMeta", parent=styles["Normal"],
        fontSize=9, textColor=HexColor("#888888"), spaceAfter=18,
    )
    intro_style = ParagraphStyle(
        "BizIntro", parent=styles["Normal"],
        fontSize=11, spaceAfter=16, leading=16,
    )
    step_num_style = ParagraphStyle(
        "BizStepNum", parent=styles["Normal"],
        fontSize=13, textColor=accent, spaceBefore=14, spaceAfter=5,
        fontName="Helvetica-Bold",
    )
    step_body_style = ParagraphStyle(
        "BizStepBody", parent=styles["Normal"],
        fontSize=11, spaceAfter=6, leading=15, leftIndent=16,
    )
    detail_style = ParagraphStyle(
        "BizDetail", parent=styles["Normal"],
        fontSize=10, spaceAfter=6, leading=14, leftIndent=16,
        textColor=HexColor("#666666"),
    )
    footer_style = ParagraphStyle(
        "BizFooter", parent=styles["Normal"],
        fontSize=8, textColor=HexColor("#aaaaaa"), alignment=1,
    )

    story = []

    story.append(Paragraph(walkthrough.get("title", "Walkthrough"), title_style))
    date_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(f"Jarvis for Business · {date_str}", meta_style))

    intro = walkthrough.get("intro", "")
    if intro:
        story.append(Paragraph(intro, intro_style))

    for step in walkthrough.get("steps", []):
        num = step.get("step_number", "?")
        instruction = step.get("instruction", "").replace("<", "&lt;").replace(">", "&gt;")
        detail = step.get("detail", "")

        story.append(Paragraph(f"Step {num}", step_num_style))
        story.append(Paragraph(instruction, step_body_style))
        if detail:
            story.append(Paragraph(f"<i>{detail}</i>", detail_style))

    _footer = _footer_label(brand_name)
    if _footer:
        story.append(Spacer(1, 0.4 * inch))
        story.append(Paragraph(_escape(_footer), footer_style))

    doc.build(story)
    return buffer.getvalue()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_table_pdf(title: str, headers: list[str], rows: list[list], brand_name: str = "", note: str = "") -> bytes:
    """
    Render a clean, aligned tabular report (P2). Uses a reportlab Table with evenly
    distributed column widths and word-wrapped cells so columns line up and long text
    doesn't overflow — instead of free-floating text. Auto-uses landscape for wide
    tables. Branded with the client's own business name (never MG&CO).
    """
    if not HAS_REPORTLAB:
        raise ImportError("reportlab not installed — add it to requirements.txt")

    headers = [str(h) for h in (headers or ["Item"])]
    n_cols = len(headers)
    pagesize = landscape(letter) if n_cols > 4 else letter
    page_w = pagesize[0]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=pagesize,
        rightMargin=36, leftMargin=36, topMargin=54, bottomMargin=48,
    )
    styles = getSampleStyleSheet()
    accent = HexColor("#c84b31")

    title_style = ParagraphStyle("TblTitle", parent=styles["Title"], fontSize=18,
                                 textColor=accent, spaceAfter=4, fontName="Helvetica-Bold")
    meta_style = ParagraphStyle("TblMeta", parent=styles["Normal"], fontSize=9,
                                textColor=HexColor("#888888"), spaceAfter=14)
    cell_style = ParagraphStyle("TblCell", parent=styles["Normal"], fontSize=9, leading=12)
    head_cell_style = ParagraphStyle("TblHeadCell", parent=styles["Normal"], fontSize=9.5,
                                     leading=12, textColor=HexColor("#ffffff"), fontName="Helvetica-Bold")
    note_style = ParagraphStyle("TblNote", parent=styles["Normal"], fontSize=8.5,
                                leading=12, textColor=HexColor("#888888"), spaceBefore=14)

    story = [Paragraph(_escape(title or "Report"), title_style)]
    meta = brand_name.strip() if brand_name and brand_name.strip() else "Report"
    story.append(Paragraph(f"{_escape(meta)} · {datetime.now().strftime('%B %d, %Y')}", meta_style))

    # Word-wrap every cell as a Paragraph so nothing overflows the column.
    table_data = [[Paragraph(_escape(h), head_cell_style) for h in headers]]
    for row in (rows or []):
        cells = list(row) + [""] * (n_cols - len(row))
        table_data.append([
            Paragraph(_escape("" if v is None else str(v)), cell_style) for v in cells[:n_cols]
        ])

    usable_w = page_w - 72
    col_w = usable_w / n_cols
    table = Table(table_data, colWidths=[col_w] * n_cols, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#131313")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl_colors.white, HexColor("#f5f5f5")]),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    if note:
        story.append(Paragraph(_escape(note), note_style))

    doc.build(story)
    return buffer.getvalue()


def _branded_cover(title: str, subtitle: str, brand_name: str = ""):
    """onFirstPage callback: dark cover with title/subtitle. The top brand line shows
    the client's own business name when known, and is omitted otherwise — never MG&CO."""

    def _draw(canvas, doc):
        canvas.saveState()
        width, height = letter
        canvas.setFillColor(HexColor("#131313"))
        canvas.rect(0, 0, width, height, fill=1, stroke=0)

        if brand_name and brand_name.strip():
            canvas.setFillColor(HexColor("#2d7ff9"))
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(0.9 * inch, height - 1.1 * inch, brand_name.strip().upper())

        canvas.setFillColor(HexColor("#ffffff"))
        canvas.setFont("Helvetica-Bold", 26)
        lines = textwrap.wrap(title, 36) or [title]
        y = height / 2 + 0.3 * inch + (0.45 * inch * (len(lines) - 1))
        for line in lines:
            canvas.drawString(0.9 * inch, y, line)
            y -= 0.45 * inch

        if subtitle:
            canvas.setFillColor(HexColor("#9aa0a6"))
            canvas.setFont("Helvetica", 12)
            canvas.drawString(0.9 * inch, y - 0.1 * inch, subtitle)

        canvas.setFillColor(HexColor("#666666"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.9 * inch, 0.7 * inch, datetime.now().strftime("%B %d, %Y"))
        canvas.restoreState()

    return _draw


def _branded_body(brand_name: str = ""):
    """onLaterPages callback factory: clean white body pages with footer. The footer
    shows the client's own business name when known, never MG&CO."""
    footer = _footer_label(brand_name)

    def _draw(canvas, doc):
        canvas.saveState()
        width, _ = letter
        canvas.setFillColor(HexColor("#aaaaaa"))
        canvas.setFont("Helvetica", 8)
        if footer:
            canvas.drawString(0.9 * inch, 0.5 * inch, footer)
        canvas.drawRightString(width - 0.9 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    return _draw


def generate_branded_document_pdf(title: str, subtitle: str, sections: list[dict], footer_note: str = "", brand_name: str = "") -> bytes:
    """
    Render a document with a dark cover page (title + subtitle) followed by clean
    white body pages. `sections` is a list of {"heading": str, "body": str}, where
    `body` lines starting with "- " render as bullets. `brand_name` (the client's own
    business name) is shown on the cover/footer; MG&CO is NEVER shown on client docs.
    """
    if not HAS_REPORTLAB:
        raise ImportError("reportlab not installed — add it to requirements.txt")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72,
    )

    styles = getSampleStyleSheet()
    accent = HexColor("#2d7ff9")

    heading_style = ParagraphStyle(
        "DocHeading", parent=styles["Heading2"],
        fontSize=14, textColor=accent, spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "DocBody", parent=styles["Normal"],
        fontSize=10.5, leading=15, spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "DocBullet", parent=body_style, leftIndent=16, bulletIndent=4,
    )
    note_style = ParagraphStyle(
        "DocNote", parent=styles["Normal"],
        fontSize=8.5, leading=12, textColor=HexColor("#888888"), spaceBefore=18,
    )

    story = [PageBreak()]
    for section in sections:
        heading = section.get("heading", "")
        body = section.get("body", "")
        if heading:
            story.append(Paragraph(_escape(heading), heading_style))
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            escaped = _escape(line)
            if escaped.startswith("- "):
                story.append(Paragraph(escaped[2:], bullet_style, bulletText="•"))
            else:
                story.append(Paragraph(escaped, body_style))

    if footer_note:
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(_escape(footer_note), note_style))

    doc.build(
        story,
        onFirstPage=_branded_cover(title, subtitle, brand_name),
        onLaterPages=_branded_body(brand_name),
    )
    return buffer.getvalue()
