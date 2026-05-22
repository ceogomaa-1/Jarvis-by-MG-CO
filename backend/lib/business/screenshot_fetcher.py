import os

import httpx

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")


async def find_screenshot(query: str) -> str | None:
    """Search Brave image search for a relevant screenshot. Returns URL or None."""
    if not BRAVE_API_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/images/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                params={
                    "q": f"{query} screenshot tutorial UI",
                    "count": 5,
                    "safesearch": "moderate",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])
        for r in results:
            url = r.get("url") or r.get("thumbnail", {}).get("src", "")
            if url and any(ext in url.lower() for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                return url
        return None
    except Exception as e:
        print(f"SCREENSHOT: Search failed: {e}")
        return None
