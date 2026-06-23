"""mgcoleads — the ONE tunable config: env gating, the scoring rubric, and category maps.

Edit WEIGHTS / thresholds here to retune the engine; nothing else needs to change.
The rubric encodes MG&CO's pain-killer thesis: a call-dependent local business with real
revenue signals but a weak digital presence = a hot lead (it needs the exact products MG&CO
sells — a Premium Website + an AI Receptionist).
"""
import os

# ── Env gating ───────────────────────────────────────────────────────────────────
# Single env var Mohamed must supply (the maps-data API key). Everything is gated on it
# so the feature is fully additive and dark until the key is present.
LEADS_MAPS_API_KEY = os.getenv("LEADS_MAPS_API_KEY", "").strip()
LEADS_PROVIDER = os.getenv("LEADS_PROVIDER", "google_places").strip() or "google_places"


def leads_enabled() -> bool:
    """True iff the leads engine should be exposed. Kill-switch: LEADS_ENABLED=false."""
    if os.getenv("LEADS_ENABLED", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(os.getenv("LEADS_MAPS_API_KEY", "").strip())


# ── Cost control ─────────────────────────────────────────────────────────────────
MAX_RESULTS = int(os.getenv("LEADS_MAX_RESULTS", "40") or "40")   # hard cap per search
PAGE_SIZE = 20                                                     # Google Places max page
CACHE_TTL_HOURS = int(os.getenv("LEADS_CACHE_TTL_HOURS", "24") or "24")  # reuse recent runs

# ── Scoring rubric (tunable) ─────────────────────────────────────────────────────
# Each signal contributes points; the raw sum is clamped to 0-100. Tuned so the canonical
# hot lead (no website + call-dependent + real reviews + an operational gap) lands in A.
WEIGHTS: dict[str, int] = {
    "no_website": 35,          # no site at all → core Premium Website pitch (biggest)
    "weak_website": 20,        # only a social/aggregator page → site rebuild pitch
    "call_dependent": 20,      # category that lives or dies on the phone → AI Receptionist
    "real_revenue": 20,        # healthy review volume → a real business with money to spend
    "decent_rating": 5,        # 3.5-4.8 stars → reputable; not a dead listing
    "missing_hours": 10,       # no hours on the listing → operational gap (booking/AI)
    "no_phone": -10,           # unreachable by phone → harder to cold-pitch (penalty)
}

TIER_A_MIN = 80
TIER_B_MIN = 50

# review_count → "real revenue" signal. Below MIN it's likely too new/small to buy.
REVIEWS_MIN = 15           # below this: no real_revenue points
REVIEWS_STRONG = 75        # at/above this: full real_revenue points (scaled in between)

# rating window that counts as "decent" (a real, reputable operator)
RATING_DECENT_MIN = 3.4
RATING_DECENT_MAX = 4.85   # near-perfect tiny-sample ratings are noise, not signal

# ── Category intelligence ────────────────────────────────────────────────────────
# Google Places `types` / primaryType substrings → True if the category is call-dependent
# (a missed call = a lost customer). Drives the call_dependent signal + the pitch line.
CALL_DEPENDENT_TYPES: tuple[str, ...] = (
    "dentist", "dental", "doctor", "clinic", "medical", "physiotherap", "chiropractor",
    "optometr", "veterinary", "vet", "spa", "salon", "hair", "beauty", "nail", "barber",
    "lawyer", "attorney", "law", "plumber", "electrician", "roofing", "hvac", "contractor",
    "locksmith", "garage", "car_repair", "auto", "restaurant", "cafe", "real_estate",
    "insurance", "moving", "cleaning", "landscap", "pest_control", "accounting",
)

# Domains that mean "no real website" — a social/aggregator page is a weak digital presence.
WEAK_WEBSITE_HOSTS: tuple[str, ...] = (
    "facebook.com", "instagram.com", "linktr.ee", "linktree", "wa.me", "yelp.com",
    "google.com", "business.site", "wixsite.com", "godaddysites.com", "square.site",
    "tiktok.com", "twitter.com", "x.com", "youtube.com", "g.page",
)

# B2C categories MG&CO does NOT sell to — filtered out (B2B only).
EXCLUDE_TYPES: tuple[str, ...] = (
    "school", "university", "government", "city_hall", "courthouse", "police",
    "church", "mosque", "synagogue", "hospital", "library", "park", "bank", "atm",
)
