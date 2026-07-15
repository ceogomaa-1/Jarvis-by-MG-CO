"""Sales Advisor — Maps-URL parsing, Places normalization, the deterministic digital
audit, research rendering, pitch JSON extraction, tool surface, and engine guards.
Network + Supabase are mocked/off (test env leaves Supabase unset on purpose)."""
import json

import pytest

from backend.lib.business.sales_advisor import engine, pitch, research
from backend.lib.business.sales_advisor.tools import SALES_TOOLS, execute_sales_tool


# ── Maps URL parsing ─────────────────────────────────────────────────────────────
def test_parse_maps_url_place_path():
    p = research.parse_maps_url(
        "https://www.google.com/maps/place/Bright+Smile+Dental/@43.5891,-79.6441,17z/data=!3m1")
    assert p["name"] == "Bright Smile Dental"
    assert p["lat"] == pytest.approx(43.5891) and p["lng"] == pytest.approx(-79.6441)


def test_parse_maps_url_query_place_id():
    p = research.parse_maps_url(
        "https://www.google.com/maps/search/?api=1&query=dentist&query_place_id=ChIJabc123_-XYZ")
    assert p["place_id"] == "ChIJabc123_-XYZ"


def test_parse_maps_url_q_param_name_vs_coords():
    assert research.parse_maps_url("https://maps.google.com/?q=Joes+Pizza+Toronto")["name"] == "Joes Pizza Toronto"
    # pure-coordinate q= must NOT be mistaken for a business name
    assert research.parse_maps_url("https://maps.google.com/?q=43.6,-79.4")["name"] is None


def test_parse_maps_url_percent_encoding():
    p = research.parse_maps_url("https://www.google.com/maps/place/Caf%C3%A9+Del+Sol/@43.1,-79.1,15z")
    assert p["name"] == "Café Del Sol"


@pytest.mark.asyncio
async def test_resolve_target_name_only_no_network():
    t = await research.resolve_target(None, "  Joes Pizza  ")
    assert t["name"] == "Joes Pizza" and t["place_id"] is None and t["maps_url"] is None


# ── Places details normalization ─────────────────────────────────────────────────
def test_normalize_details_and_reviews():
    raw = {
        "id": "ChIJx", "displayName": {"text": "Bright Smile Dental"},
        "formattedAddress": "12 King St, Oakville, ON", "nationalPhoneNumber": "(905) 555-0100",
        "websiteUri": "https://brightsmile.ca", "rating": 4.7, "userRatingCount": 132,
        "businessStatus": "OPERATIONAL",
        "regularOpeningHours": {"weekdayDescriptions": ["Mon: 9-5"]},
        "primaryTypeDisplayName": {"text": "Dentist"}, "types": ["dentist"],
        "location": {"latitude": 43.4, "longitude": -79.7},
        "editorialSummary": {"text": "A dental clinic."},
        "reviews": [{"rating": 5, "text": {"text": "Great!"},
                     "relativePublishTimeDescription": "a month ago",
                     "authorAttribution": {"displayName": "Sam"}}],
    }
    prof = research._normalize_details(raw)
    assert prof["name"] == "Bright Smile Dental" and prof["category"] == "Dentist"
    assert prof["review_count"] == 132 and prof["hours"] == ["Mon: 9-5"]
    revs = research._normalize_reviews(raw)
    assert revs[0]["rating"] == 5 and revs[0]["author"] == "Sam" and revs[0]["text"] == "Great!"


# ── deterministic digital audit ──────────────────────────────────────────────────
def _audit_map(items):
    return {i["check"]: i["status"] for i in items}


def test_audit_no_website_is_a_miss():
    a = _audit_map(research.audit_digital_presence({"website": None, "hours": [], "phone": None}, None))
    assert a["website"] == "miss" and a["listing_hours"] == "miss" and a["listing_phone"] == "miss"


def test_audit_social_only_site_is_weak():
    a = _audit_map(research.audit_digital_presence(
        {"website": "https://facebook.com/acmesalon", "hours": ["Mon"], "phone": "x"}, None))
    assert a["website"] == "miss"


def test_audit_site_signals_hit_and_miss():
    site = {"text": "Book now with Calendly. © 2021 Acme.", "links": ["https://instagram.com/acme"]}
    items = research.audit_digital_presence(
        {"website": "https://acme.ca", "hours": ["Mon"], "phone": "x"}, site)
    a = _audit_map(items)
    assert a["website"] == "hit" and a["online_booking"] == "hit"
    assert a["chat_widget"] == "miss" and a["social_links"] == "hit"
    assert a.get("stale_copyright") == "miss"  # 2021 footer = abandoned-looking site


def test_audit_unreachable_listed_site():
    a = _audit_map(research.audit_digital_presence(
        {"website": "https://acme.ca", "hours": ["Mon"], "phone": "x"},
        {"text": "", "links": [], "error": "HTTP 403"}))
    assert a["site_reachable"] == "miss"


# ── research rendering ───────────────────────────────────────────────────────────
def test_research_text_renders_and_caps():
    bundle = {
        "target": {"name": "Acme", "maps_url": None},
        "profile": {"name": "Acme", "category": "Salon", "address": "1 St, Toronto, ON",
                    "phone": None, "website": None, "rating": 4.2, "review_count": 88,
                    "price_level": None, "business_status": "OPERATIONAL", "hours": [],
                    "summary": None},
        "reviews": [{"rating": 5, "text": "Love it", "when": "a week ago", "author": "Jo"}],
        "audit": [{"check": "website", "status": "miss", "detail": "No website"}],
        "website": None, "web_intel": [{"query": "acme reviews", "results": "1. ..."}],
        "notes": "Owner is called Maria.",
    }
    text = research.research_text(bundle)
    assert "GOOGLE MAPS PROFILE" in text and "NONE — no website" in text
    assert "RECENT GOOGLE REVIEWS" in text and "DIGITAL PRESENCE AUDIT" in text
    assert "OWNER-PROVIDED INTEL" in text and "Maria" in text


def test_research_text_truncates(monkeypatch):
    from backend.lib.business.sales_advisor import config
    monkeypatch.setattr(config, "MAX_RESEARCH_CHARS", 200)
    bundle = {"target": {"name": "A"}, "profile": None, "reviews": [], "audit": [],
              "website": {"url": "https://a.com", "text": "x" * 5000, "error": None},
              "web_intel": [], "notes": None}
    text = research.research_text(bundle)
    assert len(text) <= 230 and text.endswith("[research truncated]")


# ── pitch JSON extraction ────────────────────────────────────────────────────────
def test_extract_json_plain_fenced_and_noisy():
    payload = {"offer": {"name": "The Never-Miss-A-Call System"}}
    raw = json.dumps(payload)
    assert pitch.extract_json(raw) == payload
    assert pitch.extract_json(f"```json\n{raw}\n```") == payload
    assert pitch.extract_json(f"Here you go:\n{raw}\nEnjoy.") == payload
    with pytest.raises(Exception):
        pitch.extract_json("no json here")


def test_system_prompt_grounds_mgco_and_honesty():
    sp = pitch.build_system_prompt("Brand display name: MG&CO")
    assert "AI Voice Receptionist" in sp and "pain" in sp.lower()
    assert "NEVER invent clients" in sp and "NEVER invent pricing" in sp
    assert "MG&CO" in sp and "Brand display name" in sp


# ── tool surface + dispatcher ────────────────────────────────────────────────────
def test_sales_tools_follow_prefix_convention():
    assert set(SALES_TOOLS) == {"sales__analyze_business", "sales__get_report", "sales__list_reports"}
    for name, defn in SALES_TOOLS.items():
        connector, action = name.split("__", 1)
        assert connector == "sales" and action
        assert defn["description"] and defn["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_execute_sales_tool_unknown_action():
    res = await execute_sales_tool("nope", {}, "user_x")
    assert not res.ok and "Unknown sales action" in res.error


# ── engine guards ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_start_analysis_requires_a_target():
    res = await engine.start_analysis("user_x")
    assert not res.ok
    # either input validation or (if Anthropic key placeholder missing) the env gate —
    # both are hard stops before any network/storage call
    assert "Maps link" in res.error or "off" in res.error or "storage" in res.error


@pytest.mark.asyncio
async def test_start_analysis_without_storage_fails_cleanly(monkeypatch):
    from backend.lib.business.sales_advisor import config, store
    monkeypatch.setattr(config, "enabled", lambda: True)
    monkeypatch.setattr(store, "enabled", lambda: False)
    res = await engine.start_analysis("user_x", business_name="Acme Salon")
    assert not res.ok and "storage" in res.error.lower()


def test_public_row_shapes():
    row = {"id": "r1", "business_name": "Acme", "maps_url": None, "status": "complete",
           "progress": "Done", "error": None, "model": "claude-opus-4-8",
           "created_at": "t", "updated_at": "t", "notes": "hi",
           "research": {"profile": {"name": "Acme"}, "audit": [], "website": {"text": "big"}},
           "report": {"offer": {}}}
    slim = engine._public_row(row)
    assert "report" not in slim and "research" not in slim and slim["status"] == "complete"
    full = engine._public_row(row, full=True)
    assert full["report"] == {"offer": {}} and full["profile"] == {"name": "Acme"}
    assert "website" not in full  # the raw scrape payload never leaves the store
