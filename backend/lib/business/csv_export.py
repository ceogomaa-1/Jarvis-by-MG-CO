"""
Clean CSV export (P2).

Produces proper RFC-4180 CSV via the stdlib `csv` module — real header row, correct
quoting/escaping of commas, quotes and newlines, CRLF line endings, one row per record
— then saves it as a downloadable file via the document store. This replaces ad-hoc
pasted/"scattered" text exports.
"""
import csv
import io

from backend.lib.business.document_store import save_document


def build_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    """
    Render `rows` (list of dicts) as an RFC-4180 CSV string.

    `columns` optionally fixes the header order; otherwise the union of keys is used
    in first-seen order. Values are stringified; None becomes an empty cell. Commas,
    quotes and newlines inside a value are quoted/escaped by the csv module.
    """
    rows = rows or []
    if columns is None:
        columns = []
        for row in rows:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
    if not columns:
        columns = ["value"]

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=columns,
        extrasaction="ignore",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
    return buf.getvalue()


def export_csv_document(rows: list[dict], filename: str = "export.csv", columns: list[str] | None = None) -> tuple[dict, int]:
    """
    Build a clean CSV and save it as a downloadable document.

    Returns (saved_document, row_count). The bytes use a UTF-8 BOM so Excel/Sheets
    open non-ASCII text correctly and keep columns aligned.
    """
    csv_text = build_csv(rows, columns)
    if not filename.lower().endswith(".csv"):
        filename = f"{filename}.csv"
    data = csv_text.encode("utf-8-sig")
    doc = save_document(data, filename, "text/csv")
    return doc, len(rows or [])
