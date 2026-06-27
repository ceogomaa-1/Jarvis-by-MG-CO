"""crm_enrich — bulk-enrichment intent detection.

The detector is the gate that routes "enrich phone/email/address for all my companies" to
the background job. These lock in that it fires on the real bulk asks and, crucially, does
NOT hijack normal single-record chat or unrelated requests."""
from backend.lib.business.crm_enrich import detect_bulk_enrichment, _summary_text


# ── fires on real bulk-enrichment asks ────────────────────────────────────────
def test_all_my_companies_phone():
    out = detect_bulk_enrichment("get phone numbers for all my companies")
    assert out and out["fields"] == ["phone"] and out["limit"] is None


def test_every_company_in_crm():
    out = detect_bulk_enrichment("enrich addresses for every company in my crm")
    assert out and out["fields"] == ["address"]


def test_explicit_large_count_sets_limit():
    out = detect_bulk_enrichment("fill in websites for these 42 companies")
    assert out and out["fields"] == ["website"] and out["limit"] == 42


def test_multiple_fields():
    out = detect_bulk_enrichment("get phone and website for all companies in my CRM")
    assert out and set(out["fields"]) == {"phone", "website"}


# ── does NOT hijack normal chat ───────────────────────────────────────────────
def test_single_company_lookup_is_not_bulk():
    assert detect_bulk_enrichment("what is the phone number for Acme Dental") is None


def test_small_count_is_not_bulk():
    # 3 ≤ 8 and no all/every/each → stays in normal chat
    assert detect_bulk_enrichment("get phone numbers for 3 companies") is None


def test_no_field_is_not_bulk():
    assert detect_bulk_enrichment("show me all my companies") is None


def test_lead_search_is_not_bulk():
    assert detect_bulk_enrichment("find dental clinics in Mississauga") is None


def test_empty():
    assert detect_bulk_enrichment("") is None


# ── summary wording ───────────────────────────────────────────────────────────
def test_summary_counts():
    txt = _summary_text({"updated": 38, "no_match": 3, "failed": 1}, 42, "phone")
    assert "38 of 42" in txt and "3 had no match" in txt and "1 couldn't be updated" in txt


def test_summary_clean_run():
    txt = _summary_text({"updated": 42, "no_match": 0, "failed": 0}, 42, "phone")
    assert "42 of 42" in txt and "had no match" not in txt
