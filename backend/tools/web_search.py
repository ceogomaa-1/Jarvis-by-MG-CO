import os

import httpx

from backend.tools.registry import register_tool

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")


@register_tool(
    name="web_search",
    description="Search the web for current information, news, facts, prices, or anything requiring real-time data.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> str:
    # Brave Search (best results)
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
            results = data.get("web", {}).get("results", [])
            if results:
                lines = [
                    f"{r.get('title', '')}: {r.get('description', '')}"
                    for r in results[:3]
                ]
                return "\n\n".join(lines)
        except Exception:
            pass

    # Fallback: DuckDuckGo instant answer
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10.0,
        )
    data = resp.json()
    abstract = data.get("AbstractText", "")
    answer = data.get("Answer", "")
    related = [
        r.get("Text", "")
        for r in data.get("RelatedTopics", [])[:3]
        if isinstance(r, dict) and r.get("Text")
    ]

    parts = []
    if answer:
        parts.append(answer)
    if abstract:
        parts.append(abstract)
    parts.extend(related)

    if parts:
        return "\n\n".join(parts[:3])
    return f"No results found for: {query}"
