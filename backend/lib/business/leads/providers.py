"""Maps-data provider adapter — thin + swappable.

Part 0 decision: use the OFFICIAL Google Places API (v1 Text Search), NOT raw Google Maps
HTML scraping (ToS violation + fragile + ban risk). The key Mohamed supplies (LEADS_MAPS_API_KEY,
an AIza… key) is a Google API key, so Places is the natural fit. Cost (as of build): Text
Search is billed per request (each page of up to 20 results = 1 request) on Google's
"Text Search (Advanced/Enterprise)" SKU, roughly $30-40 / 1000 requests with our field mask;
we cap results + cache repeat queries (see config) to keep spend low.

Swap providers (Outscraper / Apify Google Maps / SerpAPI) by implementing BaseProvider.search
and pointing LEADS_PROVIDER at it — nothing downstream (scoring, store, tools) changes, because
everyone consumes the normalized lead dict this module returns:

    {place_id, name, category, address, phone, website|None, rating|None, review_count,
     price_level|None, business_status, has_hours, types[], raw{}}
"""
import asyncio

import httpx

from backend.lib.business.leads import config

_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber", "places.websiteUri",
    "places.rating", "places.userRatingCount", "places.businessStatus",
    "places.regularOpeningHours.weekdayDescriptions", "places.priceLevel",
    "places.primaryType", "places.primaryTypeDisplayName", "places.types",
    "nextPageToken",
])
_PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


class ProviderError(Exception):
    """A provider call failed in a way worth surfacing to the user."""


class BaseProvider:
    name = "base"

    async def search(self, query: str, max_results: int) -> tuple[list[dict], int]:
        raise NotImplementedError


class GooglePlacesProvider(BaseProvider):
    name = "google_places"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @staticmethod
    def _normalize(p: dict) -> dict:
        price = _PRICE_LEVELS.get(p.get("priceLevel")) if p.get("priceLevel") else None
        hours = (p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
        cat = (p.get("primaryTypeDisplayName") or {}).get("text") or p.get("primaryType") or ""
        return {
            "place_id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text") or "",
            "category": cat,
            "address": p.get("formattedAddress"),
            "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber"),
            "website": p.get("websiteUri") or None,
            "rating": p.get("rating"),
            "review_count": int(p.get("userRatingCount") or 0),
            "price_level": price,
            "business_status": p.get("businessStatus"),
            "has_hours": bool(hours),
            "types": p.get("types") or ([p["primaryType"]] if p.get("primaryType") else []),
            "raw": p,
        }

    async def search(self, query: str, max_results: int) -> tuple[list[dict], int]:
        if not self.api_key:
            raise ProviderError("LEADS_MAPS_API_KEY is not set.")
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        out: list[dict] = []
        seen: set[str] = set()
        api_calls = 0
        page_token = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Google Places returns up to 20/page, ~60 max; cap by max_results + page count.
            for _ in range(5):
                body: dict = {"textQuery": query, "pageSize": config.PAGE_SIZE}
                if page_token:
                    body["pageToken"] = page_token
                resp = await client.post(_PLACES_URL, headers=headers, json=body)
                api_calls += 1
                if resp.status_code >= 400:
                    detail = resp.text.strip()[:300]
                    raise ProviderError(f"Google Places HTTP {resp.status_code}: {detail}")
                data = resp.json()
                for p in data.get("places", []):
                    pid = p.get("id")
                    if pid and pid in seen:        # dedupe by place_id within the run
                        continue
                    if pid:
                        seen.add(pid)
                    out.append(self._normalize(p))
                    if len(out) >= max_results:
                        return out, api_calls
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                await asyncio.sleep(1.0)            # token settle (and gentle rate limiting)
        return out, api_calls


def get_provider() -> BaseProvider:
    """Resolve the configured provider. Today only Google Places; others are swap-in points."""
    if config.LEADS_PROVIDER == "google_places":
        return GooglePlacesProvider(config.LEADS_MAPS_API_KEY)
    raise ProviderError(
        f"Unknown LEADS_PROVIDER '{config.LEADS_PROVIDER}'. Implement BaseProvider.search "
        "for it (Outscraper / Apify / SerpAPI) and return the normalized lead dict."
    )
