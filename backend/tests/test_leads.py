"""mgcoleads — scoring rubric, provider normalization, query parsing, and the
ingest→score→persist dedupe path. Network + Supabase are mocked."""
import pytest

from backend.lib.business.leads import config, engine, scoring
from backend.lib.business.leads.providers import GooglePlacesProvider


# ── scoring ──────────────────────────────────────────────────────────────────────
def _lead(**kw):
    base = {"place_id": "p", "name": "X", "category": "Dentist", "address": "1 St, Mississauga, ON",
            "phone": "+1 905 555 1212", "website": None, "rating": 4.6, "review_count": 200,
            "price_level": None, "business_status": "OPERATIONAL", "has_hours": False,
            "types": ["dentist", "doctor"], "raw": {}}
    base.update(kw)
    return base


def test_hot_lead_scores_tier_a():
    s = scoring.score_lead(_lead())                      # no site + call-dep + big reviews + gap
    assert s["tier"] == "A" and s["score"] >= 80
    assert "no_website" in s["signals"] and "call_dependent" in s["signals"]
    assert "Premium Website" in s["pitch"] and "AI Receptionist" in s["pitch"]


def test_weak_lead_scores_tier_c():
    s = scoring.score_lead(_lead(website="https://example.com", types=["store"], category="Store",
                                 review_count=4, rating=4.9, has_hours=True))
    assert s["tier"] == "C" and s["score"] < 50


def test_social_only_site_is_weak_website():
    assert scoring.is_weak_website("https://facebook.com/acmesalon")
    assert scoring.is_weak_website("http://www.instagram.com/foo")
    assert not scoring.is_weak_website("https://acmesalon.com")
    s = scoring.score_lead(_lead(website="https://facebook.com/acme", review_count=40,
                                 rating=4.2, has_hours=True, types=["hair_salon"], category="Salon"))
    assert "weak_website" in s["signals"] and s["tier"] == "B"


def test_real_revenue_scales_with_reviews():
    assert scoring._real_revenue_points(5, 20) == 0          # below floor
    assert scoring._real_revenue_points(75, 20) == 20        # at/above ceiling → full
    assert 0 < scoring._real_revenue_points(45, 20) < 20     # in between → partial


def test_no_phone_penalty_lowers_score():
    with_phone = scoring.score_lead(_lead())
    without = scoring.score_lead(_lead(phone=None))
    assert without["score"] < with_phone["score"]
    assert "no_phone" in without["signals"]


def test_b2c_categories_excluded():
    assert scoring.is_b2c_excluded(_lead(types=["school", "point_of_interest"], category="School"))
    assert not scoring.is_b2c_excluded(_lead())


# ── provider normalization ───────────────────────────────────────────────────────
def test_google_places_normalize():
    p = {
        "id": "ChIJabc", "displayName": {"text": "Bright Smile Dental"},
        "formattedAddress": "12 King St, Oakville, ON", "nationalPhoneNumber": "(905) 555-0100",
        "websiteUri": "https://brightsmile.ca", "rating": 4.7, "userRatingCount": 132,
        "businessStatus": "OPERATIONAL", "priceLevel": "PRICE_LEVEL_MODERATE",
        "regularOpeningHours": {"weekdayDescriptions": ["Mon: 9-5"]},
        "primaryTypeDisplayName": {"text": "Dentist"}, "types": ["dentist", "health"],
    }
    n = GooglePlacesProvider._normalize(p)
    assert n["place_id"] == "ChIJabc" and n["name"] == "Bright Smile Dental"
    assert n["phone"] == "(905) 555-0100" and n["website"] == "https://brightsmile.ca"
    assert n["review_count"] == 132 and n["price_level"] == 2 and n["has_hours"] is True
    assert n["category"] == "Dentist"


def test_google_places_normalize_missing_optionals():
    n = GooglePlacesProvider._normalize({"id": "x", "displayName": {"text": "No Web Co"}})
    assert n["website"] is None and n["review_count"] == 0 and n["has_hours"] is False
    assert n["price_level"] is None


# ── query parsing + helpers ──────────────────────────────────────────────────────
def test_parse_query_splits_industry_and_location():
    assert engine._parse_query("dental clinics in Mississauga") == ("dental clinics", "Mississauga")
    assert engine._parse_query("salons near downtown Toronto") == ("salons", "downtown Toronto")
    assert engine._parse_query("law firms") == ("law firms", "")


def test_host_and_city_helpers():
    assert engine._host("https://www.acme.ca/contact") == "acme.ca"
    assert engine._host(None) is None
    assert engine._city_from_address("12 King St, Oakville, ON L6J") == "Oakville"


# ── ingest → score → persist (dedupe) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_search_inserts_new_and_updates_existing(monkeypatch):
    monkeypatch.setattr(config, "leads_enabled", lambda: True)

    class FakeProvider:
        name = "google_places"

        async def search(self, query, cap):
            return [_lead(place_id="new1", website=None),
                    _lead(place_id="old1", name="Existing", website="https://x.com")], 1

    monkeypatch.setattr(engine, "get_provider", lambda: FakeProvider())

    inserted, updated = [], []
    async def _recent(*a, **k): return None
    async def _create_run(*a, **k): return "run-1"
    async def _existing(uid, pids): return {"old1": "lead-old"}     # old1 already stored
    async def _insert(rows): inserted.extend(rows); return len(rows)
    async def _update(lid, fields): updated.append(lid); return True

    monkeypatch.setattr(engine.store, "find_recent_run", _recent)
    monkeypatch.setattr(engine.store, "create_run", _create_run)
    monkeypatch.setattr(engine.store, "existing_by_place", _existing)
    monkeypatch.setattr(engine.store, "insert_leads", _insert)
    monkeypatch.setattr(engine.store, "update_lead", _update)

    res = await engine.run_search("user_x", "dentists in Oakville")
    assert res.ok
    assert res.data["new"] == 1 and res.data["updated"] == 1
    assert [r["place_id"] for r in inserted] == ["new1"]          # only the new place inserted
    assert updated == ["lead-old"]                               # existing re-scored in place
    assert res.data["leads"][0]["rank"] == 1                     # ranked output


@pytest.mark.asyncio
async def test_run_search_uses_cache(monkeypatch):
    monkeypatch.setattr(config, "leads_enabled", lambda: True)
    called = {"provider": False}

    def _prov():
        called["provider"] = True
        raise AssertionError("provider must not be called on cache hit")

    monkeypatch.setattr(engine, "get_provider", _prov)
    async def _recent(*a, **k): return {"id": "run-cached"}
    async def _for_run(uid, rid, limit=50): return [_lead(score=90, tier="A")]
    monkeypatch.setattr(engine.store, "find_recent_run", _recent)
    monkeypatch.setattr(engine.store, "list_leads_for_run", _for_run)

    res = await engine.run_search("user_x", "dentists in Oakville")
    assert res.ok and res.data["cached"] is True and called["provider"] is False


@pytest.mark.asyncio
async def test_run_search_disabled_returns_error(monkeypatch):
    monkeypatch.setattr(config, "leads_enabled", lambda: False)
    res = await engine.run_search("user_x", "dentists in Oakville")
    assert not res.ok and "off" in res.error.lower()
