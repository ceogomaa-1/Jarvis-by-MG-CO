"""
Export quality tests (P2): RFC-4180 CSV + clean aligned table PDF.
"""
import csv
import io

import pytest

from backend.lib.business.csv_export import build_csv


def test_csv_has_header_and_rows():
    rows = [
        {"name": "Jane Doe", "phone": "416-555-1212", "email": "jane@x.com"},
        {"name": "John Roe", "phone": "647-555-0000", "email": "john@y.com"},
    ]
    out = build_csv(rows)
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[0] == ["name", "phone", "email"]
    assert parsed[1] == ["Jane Doe", "416-555-1212", "jane@x.com"]
    assert len(parsed) == 3  # header + 2 rows


def test_csv_escapes_commas_quotes_newlines():
    rows = [{
        "name": 'Smith, Jr. "Skip"',
        "note": "line1\nline2",
        "addr": "1 Main St, Unit 2",
    }]
    out = build_csv(rows, columns=["name", "note", "addr"])
    # Round-trip: the csv reader must recover the exact original values.
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[1][0] == 'Smith, Jr. "Skip"'
    assert parsed[1][1] == "line1\nline2"
    assert parsed[1][2] == "1 Main St, Unit 2"


def test_csv_uses_crlf_and_handles_none():
    rows = [{"a": "x", "b": None}]
    out = build_csv(rows, columns=["a", "b"])
    assert "\r\n" in out  # RFC-4180 line terminator
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[1] == ["x", ""]  # None -> empty cell


def test_csv_fixed_column_order():
    rows = [{"b": 2, "a": 1, "c": 3}]
    out = build_csv(rows, columns=["a", "b", "c"])
    assert out.splitlines()[0] == "a,b,c"


def test_table_pdf_is_clean_and_unbranded_by_mgco():
    from backend.lib.business.pdf_export import HAS_REPORTLAB, generate_table_pdf
    if not HAS_REPORTLAB:
        pytest.skip("reportlab not installed")
    pypdf = pytest.importorskip("pypdf")
    pdf = generate_table_pdf(
        "Contacts With No Future Task",
        ["Name", "Phone", "Email", "Last Activity"],
        [["Jane Doe", "416-555-1212", "jane@x.com", "2026-01-02"],
         ["John Roe", "647-555-0000", "john@y.com", "2026-02-03"]],
        brand_name="Skyline Realty",
        note="Generated from GoHighLevel.",
    )
    text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    up = text.upper()
    assert "MG&CO" not in up
    assert "SKYLINE REALTY" in up
    assert "JANE DOE" in up and "JOHN ROE" in up
    assert "PHONE" in up and "EMAIL" in up
