"""Sales Advisor deep-research pipeline: one target business → a research bundle.

Stages (each degrades gracefully — a missing key/section never kills the run):
  1. resolve_target      — parse a Google Maps URL (incl. maps.app.goo.gl short links)
                           or a plain business name into {name, place_id, lat, lng}.
  2. places_profile      — official Google Places v1 lookup (Text Search → Details with
                           REVIEWS + editorial summary). Reuses LEADS_MAPS_API_KEY.
  3. scrape_website      — the shared stealth scraper (Playwright → Scrapling/curl_cffi
                           impersonation → httpx) over homepage + key subpages.
  4. web_intel           — Brave/DDG searches: reputation, socials, news.
  5. audit               — deterministic digital-presence audit (booking/ordering/chat
                           widgets, socials, weak-host website, stale copyright, https).

Output: {target, profile, reviews, website, web_intel, audit, notes} + research_text()
which renders it into the capped, labeled block the pitch LLM consumes.
"""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlparse

import httpx

from backend.lib.business.leads import config as leads_config
from backend.lib.business.leads.config import WEAK_WEBSITE_HOSTS
from backend.lib.business.sales_advisor import config
from backend.lib.business.web_scrape import scrape
from backend.tools.web_search import web_search

_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/"

_SEARCH_FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.primaryTypeDisplayName", "places.userRatingCount",
])
_DETAILS_FIELD_MASK = ",".join([
    "id", "displayName", "formattedAddress", "nationalPhoneNumber", "internationalPhoneNumber",
    "websiteUri", "rating", "userRatingCount", "businessStatus", "priceLevel",
    "regularOpeningHours.weekdayDescriptions", "primaryType", "primaryTypeDisplayName",
    "types", "location", "editorialSummary", "reviews", "googleMapsUri",
])

# Google Maps URL shapes we can pull a business name / place id / coords out of.
_RE_PLACE_PATH = re.compile(r"/maps/place/([^/@]+)")
_RE_QUERY_PLACE_ID = re.compile(r"query_place_id=([A-Za-z0-9_-]+)")
_RE_PLACE_ID_PARAM = re.compile(r"place_id[:=]([A-Za-z0-9_-]+)")
_RE_AT_COORDS = re.compile(r"/@(-?\d+\.\d+),(-?\d+\.\d+)")
_RE_Q_PARAM = re.compile(r"[?&]q=([^&]+)")
_SHORTLINK_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co", "g.page")


# ── 1. target resolution ─────────────────────────────────────────────────────────
async def _expand_shortlink(url: str) -> str:
    """Follow a maps.app.goo.gl-style redirect to the full Google Maps URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0,
                                     headers={"User-Agent": "Mozilla/5.0"}) as c:
            resp = await c.get(url)
        return str(resp.url)
    except Exception:
        return url


def parse_maps_url(url: str) -> dict:
    """Best-effort extraction of {name, place_id, lat, lng} from a full Maps URL."""
    out: dict = {"name": None, "place_id": None, "lat": None, "lng": None}
    if not url:
        return out
    m = _RE_QUERY_PLACE_ID.search(url) or _RE_PLACE_ID_PARAM.search(url)
    if m:
        out["place_id"] = m.group(1)
    m = _RE_PLACE_PATH.search(url)
    if m:
        out["name"] = unquote_plus(m.group(1)).replace("+", " ").strip()
    elif (m := _RE_Q_PARAM.search(url)):
        q = unquote_plus(m.group(1)).strip()
        # q= can be "lat,lng" — only treat it as a name when it isn't pure coords.
        if not re.fullmatch(r"-?\d+\.?\d*,\s*-?\d+\.?\d*", q):
            out["name"] = q
    m = _RE_AT_COORDS.search(url)
    if m:
        out["lat"], out["lng"] = float(m.group(1)), float(m.group(2))
    return out


async def resolve_target(maps_url: str | None, business_name: str | None) -> dict:
    """Combine the URL parse and the typed name into one target dict."""
    target = {"name": (business_name or "").strip() or None,
              "place_id": None, "lat": None, "lng": None, "maps_url": maps_url or None}
    url = (maps_url or "").strip()
    if url:
        host = (urlparse(url).hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in _SHORTLINK_HOSTS):
            url = await _expand_shortlink(url)
            target["maps_url"] = url
        parsed = parse_maps_url(url)
        target["place_id"] = parsed["place_id"]
        target["lat"], target["lng"] = parsed["lat"], parsed["lng"]
        if parsed["name"] and not target["name"]:
            target["name"] = parsed["name"]
    return target


# ── 2. Google Places profile (+ reviews) ─────────────────────────────────────────
def _normalize_details(p: dict) -> dict:
    loc = p.get("location") or {}
    return {
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text") or "",
        "category": (p.get("primaryTypeDisplayName") or {}).get("text") or p.get("primaryType") or "",
        "types": p.get("types") or [],
        "address": p.get("formattedAddress"),
        "lat": loc.get("latitude"), "lng": loc.get("longitude"),
        "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber"),
        "website": p.get("websiteUri") or None,
        "rating": p.get("rating"),
        "review_count": int(p.get("userRatingCount") or 0),
        "price_level": p.get("priceLevel"),
        "business_status": p.get("businessStatus"),
        "hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [],
        "summary": (p.get("editorialSummary") or {}).get("text"),
        "maps_uri": p.get("googleMapsUri"),
    }


def _normalize_reviews(p: dict) -> list[dict]:
    out = []
    for r in (p.get("reviews") or [])[:5]:
        out.append({
            "rating": r.get("rating"),
            "text": ((r.get("text") or {}).get("text") or "")[:600],
            "when": r.get("relativePublishTimeDescription") or r.get("publishTime"),
            "author": ((r.get("authorAttribution") or {}).get("displayName") or "")[:60],
        })
    return out


async def places_profile(target: dict) -> tuple[dict | None, list[dict]]:
    """Official Places v1 lookup: (normalized profile, reviews). (None, []) without a key."""
    api_key = leads_config.LEADS_MAPS_API_KEY
    if not api_key:
        return None, []
    place_id = target.get("place_id")
    try:
        async with httpx.AsyncClient(timeout=config.PLACES_TIMEOUT) as c:
            if not place_id and target.get("name"):
                body: dict = {"textQuery": target["name"], "pageSize": 5}
                if target.get("lat") is not None and target.get("lng") is not None:
                    body["locationBias"] = {"circle": {
                        "center": {"latitude": target["lat"], "longitude": target["lng"]},
                        "radius": 2000.0}}
                resp = await c.post(_PLACES_SEARCH_URL, json=body, headers={
                    "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _SEARCH_FIELD_MASK,
                    "Content-Type": "application/json"})
                if resp.status_code < 400:
                    places = resp.json().get("places") or []
                    if places:
                        wanted = (target["name"] or "").lower()
                        exact = [p for p in places
                                 if wanted and wanted in ((p.get("displayName") or {}).get("text") or "").lower()]
                        place_id = ((exact or places)[0]).get("id")
            if not place_id:
                return None, []
            resp = await c.get(f"{_PLACES_DETAILS_URL}{place_id}", headers={
                "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _DETAILS_FIELD_MASK})
            if resp.status_code >= 400:
                print(f"SALES.research: place details HTTP {resp.status_code}: {resp.text[:200]}")
                return None, []
            raw = resp.json()
            return _normalize_details(raw), _normalize_reviews(raw)
    except Exception as e:
        print(f"SALES.research: places_profile failed: {e}")
        return None, []


# ── 4. web intel ─────────────────────────────────────────────────────────────────
async def web_intel(name: str, city: str | None) -> list[dict]:
    """A few reputation/presence searches. Each returns the numbered text block the
    shared web_search helper produces (Brave first, DDG fallback)."""
    where = f" {city}" if city else ""
    queries = [f'"{name}"{where} reviews', f'"{name}"{where}', f"{name}{where} instagram facebook"]
    out = []
    for q in queries[:config.MAX_SEARCHES]:
        try:
            text = await web_search(q)
            if text and "No results" not in text[:40]:
                out.append({"query": q, "results": text[:2500]})
        except Exception as e:
            print(f"SALES.research: web_intel '{q}' failed: {e}")
    return out


# ── 5. deterministic digital-presence audit ──────────────────────────────────────
_SIGNS = {
    "online_booking": r"calendly|book\s*(now|online|an?\s*appointment)|opentable|resy|mindbody|vagaro|fresha|squareup\.com/appointments|setmore|acuity",
    "online_ordering": r"ubereats|doordash|skipthedishes|grubhub|order\s*online|ritual\.co",
    "chat_widget": r"intercom|drift\.com|tawk\.to|crisp\.chat|livechat|tidio|zendesk",
}
_SOCIALS = ("instagram.com", "facebook.com", "tiktok.com", "linkedin.com", "youtube.com")


def _is_weak_site(url: str | None) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return any(h in host for h in WEAK_WEBSITE_HOSTS)


def audit_digital_presence(profile: dict | None, site: dict | None) -> list[dict]:
    """Boolean/found-style checks the pitch can cite as hard evidence. Each item:
    {check, status: 'hit'|'miss'|'unknown', detail}. 'miss' = a gap MG&CO can sell into."""
    website = (profile or {}).get("website")
    items: list[dict] = []

    if not website:
        items.append({"check": "website", "status": "miss",
                      "detail": "No website on the Google listing — invisible to anyone who Googles them."})
    elif _is_weak_site(website):
        items.append({"check": "website", "status": "miss",
                      "detail": f"'Website' is only a social/aggregator page ({website}) — no real owned presence."})
    else:
        items.append({"check": "website", "status": "hit", "detail": website})
        if website.lower().startswith("http://"):
            items.append({"check": "https", "status": "miss",
                          "detail": "Site is served over plain HTTP — browsers flag it 'Not secure'."})

    corpus = ""
    if site and site.get("text"):
        corpus = (site.get("text") or "") + "\n" + "\n".join(site.get("links") or [])
        low = corpus.lower()
        for check, pattern in _SIGNS.items():
            found = re.search(pattern, low) is not None
            items.append({"check": check, "status": "hit" if found else "miss",
                          "detail": "found on site" if found else "not found anywhere on the site"})
        socials = sorted({s.split(".")[0] for s in _SOCIALS if s in low})
        items.append({"check": "social_links", "status": "hit" if socials else "miss",
                      "detail": ", ".join(socials) if socials else "no social profiles linked from the site"})
        years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(20\d{2})", low)]
        this_year = datetime.now(timezone.utc).year
        if years and max(years) < this_year - 1:
            items.append({"check": "stale_copyright", "status": "miss",
                          "detail": f"Footer copyright says {max(years)} — the site looks abandoned."})
    elif website and not _is_weak_site(website):
        items.append({"check": "site_reachable", "status": "miss",
                      "detail": f"Listed website could not be read ({(site or {}).get('error') or 'unreachable'})."})

    if profile:
        if not profile.get("hours"):
            items.append({"check": "listing_hours", "status": "miss",
                          "detail": "No opening hours on the Google listing — customers can't tell when to call."})
        if not profile.get("phone"):
            items.append({"check": "listing_phone", "status": "miss",
                          "detail": "No phone number on the Google listing."})
    return items


# ── orchestration ────────────────────────────────────────────────────────────────
def _city_of(profile: dict | None) -> str | None:
    address = (profile or {}).get("address")
    if not address:
        return None
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return parts[1] if len(parts) >= 2 else None


async def run_research(maps_url: str | None, business_name: str | None,
                       notes: str | None, progress=None) -> dict:
    """The full pipeline. `progress` is an async callable(str) for stage updates."""
    async def _stage(msg: str):
        if progress:
            try:
                await progress(msg)
            except Exception:
                pass

    target = await resolve_target(maps_url, business_name)
    if not target.get("name") and not target.get("place_id"):
        raise ValueError("Couldn't identify the business — give me a Google Maps link or the business name.")

    await _stage("Pulling the Google Maps profile and reviews…")
    profile, reviews = await places_profile(target)
    name = (profile or {}).get("name") or target.get("name") or "this business"
    city = _city_of(profile)

    await _stage("Scraping their website…")
    site = None
    website = (profile or {}).get("website")
    if website:
        try:
            site = await scrape(website, max_pages=config.MAX_SITE_PAGES)
        except Exception as e:
            site = {"url": website, "text": "", "links": [], "error": f"{type(e).__name__}: {e}"}

    await _stage("Scanning the web for reputation and presence…")
    intel = await web_intel(name, city)

    await _stage("Auditing their digital presence…")
    audit = audit_digital_presence(profile, site)

    return {"target": target, "profile": profile, "reviews": reviews,
            "website": {"url": (site or {}).get("url") or website,
                        "text": (site or {}).get("text") or "",
                        "error": (site or {}).get("error")} if (site or website) else None,
            "web_intel": intel, "audit": audit, "notes": (notes or "").strip() or None,
            "researched_at": datetime.now(timezone.utc).isoformat()}


def research_text(research: dict) -> str:
    """Render the bundle into the labeled, size-capped block the pitch LLM consumes."""
    parts: list[str] = []
    profile = research.get("profile")
    if profile:
        hours = "; ".join(profile.get("hours") or []) or "not listed"
        parts.append(
            "## GOOGLE MAPS PROFILE (official Places data)\n"
            f"Name: {profile.get('name')}\nCategory: {profile.get('category')}\n"
            f"Address: {profile.get('address')}\nPhone: {profile.get('phone') or 'NOT LISTED'}\n"
            f"Website: {profile.get('website') or 'NONE — no website on the listing'}\n"
            f"Rating: {profile.get('rating')} stars from {profile.get('review_count')} reviews\n"
            f"Price level: {profile.get('price_level') or 'unknown'}\nStatus: {profile.get('business_status')}\n"
            f"Hours: {hours}\nGoogle's summary: {profile.get('summary') or '—'}")
    else:
        t = research.get("target") or {}
        parts.append("## TARGET (no Places profile available)\n"
                     f"Name: {t.get('name')}\nMaps URL: {t.get('maps_url') or '—'}")

    reviews = research.get("reviews") or []
    if reviews:
        lines = [f"- {r.get('rating')}★ ({r.get('when')}) {r.get('author')}: \"{r.get('text')}\"" for r in reviews]
        parts.append("## RECENT GOOGLE REVIEWS (verbatim customer voice)\n" + "\n".join(lines))

    audit = research.get("audit") or []
    if audit:
        lines = [f"- [{a['status'].upper()}] {a['check']}: {a['detail']}" for a in audit]
        parts.append("## DIGITAL PRESENCE AUDIT (deterministic checks — cite these as evidence)\n" + "\n".join(lines))

    website = research.get("website")
    if website and website.get("text"):
        parts.append(f"## WEBSITE CONTENT ({website.get('url')})\n{website['text']}")
    elif website and website.get("error"):
        parts.append(f"## WEBSITE\nListed site {website.get('url')} could not be read: {website['error']}")

    for block in research.get("web_intel") or []:
        parts.append(f"## WEB SEARCH: {block['query']}\n{block['results']}")

    if research.get("notes"):
        parts.append("## OWNER-PROVIDED INTEL (from Mohamed — treat as ground truth)\n" + research["notes"])

    text = "\n\n".join(parts)
    if len(text) > config.MAX_RESEARCH_CHARS:
        text = text[:config.MAX_RESEARCH_CHARS] + "\n\n[research truncated]"
    return text
