import os

import httpx

from backend.tools.registry import register_tool
from backend.tools.citation_context import add_source

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")


@register_tool(
    name="web_search",
    description="Search the web for current information. Use when the user asks about recent events, current facts, news, prices, weather, or anything that requires real-time information beyond your training data. Each result is numbered — cite them inline using [1], [2], etc. Do NOT use for things you already know.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Keep it short and specific, 2-6 words.",
            }
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> str:
    print(f"WEB_SEARCH: query={query!r}")
    results = []

    if BRAVE_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": BRAVE_API_KEY,
                    },
                    params={"q": query, "count": 5},
                    timeout=10.0,
                )
            data = resp.json()
            for r in data.get("web", {}).get("results", [])[:5]:
                url = r.get("url", "")
                title = r.get("title", "")
                desc = r.get("description", "")
                if url:
                    results.append({"url": url, "title": title, "snippet": desc})
        except Exception as e:
            print(f"WEB_SEARCH: Brave failed: {e}")

    if not results:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    timeout=10.0,
                )
            data = resp.json()
            for r in data.get("RelatedTopics", [])[:5]:
                if isinstance(r, dict) and r.get("FirstURL") and r.get("Text"):
                    results.append({
                        "url": r["FirstURL"],
                        "title": r["Text"].split(" - ")[0][:120],
                        "snippet": r["Text"],
                    })
        except Exception as e:
            print(f"WEB_SEARCH: DuckDuckGo failed: {e}")

    if not results:
        return f"No results found for: {query}"

    lines = []
    for r in results:
        idx = add_source(
            url=r["url"],
            title=r["title"],
            snippet=r["snippet"],
            source_type="web_search",
        )
        lines.append(f"[{idx}] {r['title']}\nURL: {r['url']}\n{r['snippet']}")
    return "\n\n".join(lines)
