"""Overlay text onto a flat (non-AcroForm) PDF using reportlab + pypdf.

Used by orea_form_filler to draft-fill the OREA Form 100 Agreement of
Purchase and Sale. Each entry in `fields` describes where on the page a
value should be drawn — either a single (x, y) position, or a list of
(x, y) `lines` for fields whose text may wrap across multiple printed
blank lines (e.g. chattels included).
"""
import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

FONT = "Helvetica"
MIN_FONT_SIZE = 6


def _fit_size(text: str, max_width: float, size: float) -> float:
    while size > MIN_FONT_SIZE and stringWidth(text, FONT, size) > max_width:
        size -= 0.5
    return size


def _wrap_lines(text: str, max_width: float, size: float, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or stringWidth(candidate, FONT, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                return lines
    if current:
        lines.append(current)
    return lines[:max_lines]


def fill_overlay(content: bytes, page_width: float, page_height: float, fields: dict, values: dict) -> bytes:
    """Render `values` (a subset of `fields` keys -> strings) onto `content`
    and return the merged PDF bytes."""
    reader = PdfReader(io.BytesIO(content))
    draws_by_page: dict[int, list[tuple[float, float, str, float]]] = {}

    for key, value in values.items():
        spec = fields.get(key)
        if not spec or value in (None, ""):
            continue
        text = str(value)
        page_index = spec.get("page", 0)
        size = spec.get("size", 8)
        max_width = spec.get("max_width")

        if "lines" in spec:
            wrapped = _wrap_lines(text, max_width, size, len(spec["lines"]))
            for (x, y), line in zip(spec["lines"], wrapped):
                draws_by_page.setdefault(page_index, []).append((x, y, line, size))
        else:
            draw_size = _fit_size(text, max_width, size) if max_width else size
            draws_by_page.setdefault(page_index, []).append((spec["x"], spec["y"], text, draw_size))

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        draws = draws_by_page.get(i)
        if draws:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(page_width, page_height))
            for x, y, text, size in draws:
                c.setFont(FONT, size)
                c.drawString(x, y, text)
            c.save()
            buf.seek(0)
            page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
